# app/ai_steps.py
"""Language-agnostic, model-driven steps used by answering.py. No word lists for any one language.

  doc_profile      which languages and scripts the workspace's documents are really written in (sampled from the passages)
  rewrite_reason   decides when the question needs a rewrite: its language/script does not fit the documents, or the first search was weak
  rewrite_queries  the LLM rewrites the question into English and the documents' own language(s), also when it was typed in Latin letters
  judge_relevance  the LLM says which retrieved passages really answer the question (so look-alike passages do not produce an answer)

Settings (.env, all optional):  WEAK_MARGIN (default 0.03), STRONG_MARGIN (0.06), RELEVANCE_JUDGE (on|off, default on)
"""
import collections, os, re, statistics, time, unicodedata
from langdetect import detect_langs, DetectorFactory
DetectorFactory.seed = 0

WEAK_MARGIN = float(os.getenv("WEAK_MARGIN", "0.03"))        # below this the first search is not trusted
STRONG_MARGIN = float(os.getenv("STRONG_MARGIN", "0.06"))    # above this the search is trusted without asking the model
RELEVANCE_JUDGE = os.getenv("RELEVANCE_JUDGE", "off").strip().lower() == "on"
PROFILE_TTL_S = 300
SAMPLE_CHUNKS = 60

LANG_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu",
              "gu": "Gujarati", "pa": "Punjabi", "ur": "Urdu", "kn": "Kannada", "ml": "Malayalam", "ne": "Nepali",
              "fr": "French", "de": "German", "es": "Spanish", "pt": "Portuguese", "it": "Italian", "ru": "Russian",
              "ar": "Arabic", "ja": "Japanese", "ko": "Korean", "zh-cn": "Chinese", "zh-tw": "Chinese",
              "tr": "Turkish", "id": "Indonesian", "vi": "Vietnamese", "th": "Thai", "fa": "Persian", "nl": "Dutch",
              "pl": "Polish", "uk": "Ukrainian", "sv": "Swedish", "el": "Greek", "he": "Hebrew"}


def lang_name(code):
    return LANG_NAMES.get(code, code)


# ---------------------------------------------------------------- scripts and languages
def script_of(ch):
    if not ch.isalpha():
        return None
    try:
        return unicodedata.name(ch).split()[0]            # LATIN, DEVANAGARI, ARABIC, CJK, HANGUL, CYRILLIC ...
    except ValueError:
        return None


def script_shares(text):
    c = collections.Counter(s for s in map(script_of, text or "") if s)
    total = sum(c.values())
    return {k: v / total for k, v in c.items()} if total else {}


def dominant_script(text):
    sh = script_shares(text)
    return max(sh, key=sh.get) if sh else None


def detect_language(text):
    """(code, probability) or (None, 0.0)."""
    try:
        best = detect_langs((text or "")[:1000])[0]
        return best.lang, float(best.prob)
    except Exception:
        return None, 0.0


_cache = {}


def doc_profile(con, workspace_id, now=None):
    """{'languages': [(code, share), ...], 'scripts': {script: share}} for the workspace, from a sample of
    its passages. Cached for a few minutes. Returns an empty profile if nothing can be read."""
    now = time.monotonic() if now is None else now
    hit = _cache.get(workspace_id)
    if hit and now - hit[0] < PROFILE_TTL_S:
        return hit[1]
    prof = {"languages": [], "scripts": {}}
    try:
        rows = con.execute(
            "SELECT c.text FROM chunks c JOIN document_versions v ON v.version_id=c.version_id "
            "JOIN documents d ON d.document_id=v.document_id "
            "WHERE d.workspace_id=%s AND c.strategy='structure' AND v.status='ok' "
            "ORDER BY md5(c.chunk_id) LIMIT %s", (workspace_id, SAMPLE_CHUNKS)).fetchall()
        texts = [r["text"] for r in rows if r.get("text")]
        scripts, langs = collections.Counter(), collections.Counter()
        for t in texts:
            for s, share in script_shares(t).items():
                scripts[s] += share
            code, p = detect_language(t)
            if code and p >= 0.5:
                langs[code] += 1
        if texts:
            prof["scripts"] = {s: v / len(texts) for s, v in scripts.items()}
            n = sum(langs.values()) or 1
            prof["languages"] = [(c, v / n) for c, v in langs.most_common(4) if v / n >= 0.1]
    except Exception:
        try:
            con.rollback()                                   # a failed query must not leave the transaction aborted
        except Exception:
            pass
    if prof["languages"] or prof["scripts"]:
        _cache[workspace_id] = (now, prof)
    return prof


# ---------------------------------------------------------------- when to rewrite
def margin(rows):
    """How far the best passage stands out from the rest of the top results (vector scores). None if unknown."""
    scores = sorted((float(r["score"]) for r in rows), reverse=True)[:10]
    return scores[0] - statistics.median(scores[1:]) if len(scores) >= 4 else None


def rewrite_reason(question, prof, first_margin):
    """Why the question should be rewritten, or None when searching with it as typed is fine."""
    if first_margin is not None and first_margin < WEAK_MARGIN:
        return "weak_retrieval"
    if first_margin is not None and first_margin >= STRONG_MARGIN:
        return None                                       # the search is already confident: no rewrite needed
    doc_scripts = {s for s, v in (prof.get("scripts") or {}).items() if v >= 0.05}
    q_script = dominant_script(question)
    if not q_script:
        return None
    if q_script != "LATIN":
        return None if (q_script in doc_scripts or not doc_scripts) else "script_not_in_documents"
    code, prob = detect_language(question)
    doc_codes = {c for c, _ in prof.get("languages", [])}
    if "LATIN" in doc_scripts and code in doc_codes and prob >= 0.9:
        return None                                       # same language as the documents
    if not doc_codes and prob >= 0.9:
        return None
    return "language_unsure"                              # e.g. a language written in Latin letters, or a short text


# ---------------------------------------------------------------- the model-driven steps
def rewrite_system(prof):
    # Two English versions: the question, and the same question in the words a book might use
    # (synonyms, names, related terms). Books often say "chariot" or "Krishna" instead of "charioteer".
    targets = ["English", "English, using other words a book on this topic might use"]
    for code, _ in prof.get("languages", []):
        if code != "en" and len(targets) < 3:
            targets.append(f"{lang_name(code)}, in its native script")
    lines = "\n".join(f"Line {i + 1}: the question in {t}" for i, t in enumerate(targets))
    return ("You rewrite a search question. The question may be in any language, or in a language typed with Latin "
            "letters (romanized). Work out what it asks and rewrite it faithfully: keep every noun and verb, do not "
            "summarize, do not add words, and do not answer it. "
            f"Output exactly {len(targets)} lines and nothing else:\n{lines}"), len(targets)


def rewrite_queries(question, prof, generate):
    """Versions of the question in English and the documents' language(s). [] if the model fails."""
    system, n = rewrite_system(prof)
    try:
        raw = generate(system, question, max_tokens=140)
    except Exception:
        return []
    out = []
    for ln in raw.splitlines():
        ln = re.sub(r"^\s*(line\s*\d+\s*[:.)-]|\d+\s*[.)])\s*", "", ln, flags=re.I).strip().strip('"')
        if 3 <= len(ln) <= 300 and ln.casefold() != question.casefold() and ln not in out:
            out.append(ln)
    return out[:n]


JUDGE_SYSTEM = ("You check search results. For the question, decide which numbered passages contain information that "
                "answers it. The passages may be in a different language than the question. Reply with only the "
                "numbers of the passages that answer it, separated by commas, or NONE if no passage answers it. "
                "Do not explain.")


def judge_relevance(question, english, evidence, generate):
    """Numbers (the evidence 'n') the model judges relevant; [] when it says NONE; None when it gave no usable reply."""
    body = "\n\n".join(f"Passage {e['n']}: " + " ".join(e["text"].split())[:350] for e in evidence)
    ask = f"Question: {question}\n" + (f"(English: {english})\n" if english else "") + "\n" + body
    try:
        raw = generate(JUDGE_SYSTEM, ask, max_tokens=12)
    except Exception:
        return None
    nums = [int(x) for x in re.findall(r"\d+", raw)]
    valid = {e["n"] for e in evidence}
    picked = []
    for x in nums:
        if x in valid and x not in picked:
            picked.append(x)
    if picked:
        return picked
    return [] if re.search(r"\bnone\b", raw, re.I) else None
