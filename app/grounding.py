# app/grounding.py
"""Language-agnostic helpers for building and checking answers. Pure functions: no database, no model
(the model and the embedder are passed in where they are needed).

Nothing here knows about any one language, script, book or domain:
  * sentences are split on the end marks of every major script (. ! ? and the Devanagari danda, CJK, Arabic ...)
  * the size of a text is estimated in tokens per script, so Hindi, Chinese or English all fit the same budget
  * a poor answer (too short, looping) is recognised from its shape, not from word lists
  * an extractive fallback picks the document's own sentences by rare-word overlap (+ optional embeddings)
"""
import math
import re
import unicodedata

CITE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_END_SPACED = r"(?<=[.!?])\s+(?=\S)"                                   # Latin-style: needs a space after the mark
_END_BARE = r"(?<=[\u0964\u0965\u3002\uff01\uff1f\u061f\u06d4\u1362\u104b\u17d4])\s*(?=\S)"   # danda, CJK, Arabic ...
SENT_SPLIT = re.compile(f"{_END_SPACED}|{_END_BARE}")
TERMINATORS = ".!?\u0964\u0965\u3002\uff01\uff1f\u061f\u06d4\u1362\u104b\u17d4"


# ------------------------------------------------------------------ text basics
def strip_cites(text):
    return CITE.sub("", text or "")


def body(text):
    """The answer without its [n] markers, trimmed."""
    return re.sub(r"\s+", " ", strip_cites(text)).strip()


def split_sentences(text):
    """Sentences of any script. Line breaks that end a line without a mark also end a sentence."""
    out = []
    for block in re.split(r"\n\s*\n|\n(?=\S)", text or ""):
        block = " ".join(block.split())
        out.extend(s.strip() for s in SENT_SPLIT.split(block) if s.strip())
    return out


def _char_tokens(ch):
    """Estimated tokens per character, by script. Slightly high on purpose: an over-estimate only
    means a little less evidence is sent, an under-estimate means the prompt gets cut."""
    o = ord(ch)
    if ch.isspace():
        return 0.1
    if o < 0x250:
        return 0.27                                  # Latin, digits, punctuation
    if o < 0x590:
        return 0.45                                  # Greek, Cyrillic, Armenian
    if o < 0x900:
        return 0.55                                  # Hebrew, Arabic, Syriac, Thaana
    if o < 0x0E00:
        return 0.65                                  # Indic scripts
    if o < 0x1100:
        return 0.65                                  # Thai, Lao, Tibetan, Myanmar
    if 0x3000 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF:
        return 0.95                                  # CJK, Hiragana/Katakana, Hangul
    return 0.7


def estimate_tokens(text):
    return int(math.ceil(sum(_char_tokens(c) for c in text or "")))


def units(text):
    """Size of a text in 'words'. Scripts written without spaces (Chinese, Japanese, Thai) have almost
    no spaces, so there one 'word' is about two characters."""
    t = text or ""
    n = len(t.split())
    chars = len(t) - t.count(" ")
    if n and chars / n > 14:
        return max(n, -(-chars // 2))                  # rounded up: a size is never under-estimated
    return n


def cut_to_tokens(text, limit):
    """The start of `text` that fits in `limit` tokens, cut at a sentence end when possible."""
    if estimate_tokens(text) <= limit:
        return text
    acc, cut = 0.0, 0
    for i, ch in enumerate(text):
        acc += _char_tokens(ch)
        if acc > limit:
            break
        cut = i + 1
    piece = text[:cut]
    end = max(piece.rfind(c) for c in TERMINATORS)
    return (piece[:end + 1] if end > len(piece) * 0.4 else piece).strip()


# ------------------------------------------------------------------ evidence budget
def select_evidence(rows, k, budget_tokens, reserve=900):
    """Up to `k` passages in order, as many as fit in the token budget (minus `reserve` for the instructions,
    the question and the answer). The first passage is always kept, shortened if it alone is too long."""
    room = max(budget_tokens - reserve, 400)
    out, used = [], 0
    for r in rows:
        if len(out) >= k:
            break
        tok = estimate_tokens(r["text"])
        if not out and tok > room:
            r = dict(r, text=cut_to_tokens(r["text"], room))
            tok = estimate_tokens(r["text"])
        elif used + tok > room:
            continue                                  # a smaller, lower-ranked passage may still fit
        out.append(r)
        used += tok
    return out


# ------------------------------------------------------------------ answer clean-up
_LEAD = re.compile(r"^\s*(\[\d+(?:\s*,\s*\d+)*\])\s+(\S.*)$", re.S)
_ECHO = re.compile(r"^\s*\(?\s*english meaning of the question.*$", re.I | re.M)
_SRC_TAG = re.compile(r"[\[(]\s*source\s*(?:id)?\s*=?\s*(\d+(?:\s*,\s*\d+)*)\s*[\])]", re.I)


def tidy(raw):
    """Conservative repair of typical small-model output: leaked tags, citation in the wrong place,
    repeated sentences, a sentence cut off by the token limit. A good answer comes back unchanged."""
    t = _ECHO.sub("", (raw or "")).strip()
    t = _SRC_TAG.sub(r"[\1]", t)
    t = re.sub(r"\[(\d+)\]\s*\[(\d+)\]", r"[\1, \2]", t)
    t = re.sub(r"(?<!\S)(\S+)(?:\s+\1)+(?!\S)", r"\1", t)              # "word word" -> "word"
    first_style = bool(_LEAD.match(t))                                  # "[1] A. [2] B." -> "A. [1] B. [2]"
    parts = [p for p in SENT_SPLIT.split(t) if p.strip()]
    sents = []
    for part in parts:
        m = re.match(r"^((?:\[\d+(?:\s*,\s*\d+)*\]\s*)+)(.*)$", part, re.S)
        if not m:
            sents.append(part.strip())
            continue
        cites, rest = m.group(1).strip(), m.group(2).strip()
        if first_style:
            sents.append((rest + " " + cites) if rest else cites)
        elif sents:                                                     # "A. [1] B." -> the [1] ends sentence A
            sents[-1] += " " + cites
            if rest:
                sents.append(rest)
        else:
            sents.append(part.strip())
    out, seen = [], set()
    for s in sents:
        key = re.sub(r"\W+", " ", strip_cites(s).lower()).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(s)
    if len(out) > 1 and not re.search(f"[{re.escape(TERMINATORS)}]\\s*(\\[[\\d,\\s]+\\])*\\s*$", out[-1]):
        out.pop()                                                       # cut off by the token limit
    return " ".join(out).strip()


def degenerate(text):
    """True when the text loops on the same words (few distinct pieces for its length)."""
    b = body(text).lower()
    words = b.split()
    if len(words) >= 12:
        return len(set(words)) / len(words) < 0.5
    if len(b) >= 40 and len(words) < 6:                                 # unspaced script: compare 4-char pieces
        pieces = [b[i:i + 4] for i in range(0, len(b) - 3)]
        return len(set(pieces)) / len(pieces) < 0.4
    return False


def too_short(text):
    b = body(text)
    return len(b.split()) < 3 and sum(c.isalnum() for c in b) < 6


def is_poor(answer):
    """Not a real answer: nothing but a citation, a few characters, or text that loops."""
    return too_short(answer) or degenerate(answer)


# ------------------------------------------------------------------ script helpers
def script_of(ch):
    if not ch.isalpha():
        return None
    try:
        return unicodedata.name(ch).split()[0]
    except ValueError:
        return None


def latin_ratio(text):
    letters = [c for c in text or "" if c.isalpha()]
    if not letters:
        return 0.0
    return sum(script_of(c) == "LATIN" for c in letters) / len(letters)


def is_latin(text, threshold=0.85):
    return latin_ratio(text) >= threshold


# ------------------------------------------------------------------ extractive fallback
_STRIP = ".,;:!?()[]\"'\u0964\u0965\u3002\uff01\uff1f\u061f\u2018\u2019\u201c\u201d-"


def terms(text):
    """Searchable pieces of a text in any script: lower-cased words (letters, marks and digits together, so
    Indic words stay whole) and, for Chinese/Japanese, overlapping character pairs."""
    t = unicodedata.normalize("NFKC", text or "").casefold()
    out, cur, cjk = [], [], []

    def flush():
        if cur:
            out.append("".join(cur))
            cur.clear()

    def flush_cjk():
        if len(cjk) == 1:
            out.append(cjk[0])
        out.extend(cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1))
        cjk.clear()

    for ch in t:
        o = ord(ch)
        if 0x3040 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF:
            flush()
            cjk.append(ch)
            continue
        flush_cjk()
        if unicodedata.category(ch)[0] in "LMN":
            cur.append(ch)
        else:
            flush()
    flush()
    flush_cjk()
    return out


def stem(w, n=5):
    return w[:n]


def _cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def score_sentences(cands, queries, embed_query=None, embed_texts=None):
    """Relevance of each candidate sentence `(n, text)` to the question(s), 0..1, in any script.
    Rare-word overlap (words that occur in many sentences count less), blended 50/50 with embedding
    similarity when an embedder is given. Returns (lexical, semantic, final) lists."""
    n_docs = len(cands)
    sent_terms = [set(stem(t) for t in terms(s)) for _, s in cands]
    df = {}
    for ts in sent_terms:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(1 + n_docs / (1 + c)) for t, c in df.items()}
    q_sets = [set(stem(t) for t in terms(q)) for q in queries]
    lex = []
    for ts in sent_terms:
        best = 0.0
        for qs in q_sets:
            tot = sum(idf.get(t, math.log(1 + n_docs)) for t in qs) or 1.0
            best = max(best, sum(idf[t] for t in qs if t in ts) / tot)
        lex.append(best)
    sem = [0.0] * n_docs
    if embed_query and embed_texts and n_docs:
        try:
            qv = [embed_query(q) for q in queries[:3]]
            sv = embed_texts([s for _, s in cands])
            sem = [max(_cos(q, v) for q in qv) for v in sv]
            lo = min(sem)
            span = (max(sem) - lo) or 1.0
            sem = [(x - lo) / span for x in sem]          # embedding scores are bunched: spread them over 0..1
        except Exception:
            sem = [0.0] * n_docs
    use_sem = any(sem)
    final = [(0.5 * l + 0.5 * m) if use_sem else l for l, m in zip(lex, sem)]
    return lex, sem, final


def candidate_sentences(evidence):
    """[(passage n, sentence)] for every sentence of every passage that has some real text in it."""
    return [(e["n"], s) for e in evidence for s in split_sentences(e["text"]) if sum(c.isalnum() for c in s) >= 6]


def extractive_answer(queries, evidence, embed_query=None, embed_texts=None, max_sentences=2, min_score=0.12):
    """The passage sentences that best match the question, as {'n', 'sentences', 'score'}, or None.
    Sentences are returned unchanged, so the result is exactly what the document says."""
    cands = candidate_sentences(evidence)
    if not cands or not queries:
        return None
    lex, sem, score = score_sentences(cands, queries, embed_query, embed_texts)
    n_docs, use_sem = len(cands), any(sem)
    i = max(range(n_docs), key=score.__getitem__)
    if score[i] < min_score or (use_sem and lex[i] == 0 and score[i] < 0.5):
        return None
    n = cands[i][0]
    # the best sentence, plus the other sentences of that passage that also match (in reading order);
    # the question often names the subject in one sentence and the answer sits in the next
    chosen = {i}
    for j in sorted((j for j in range(n_docs) if cands[j][0] == n and j != i), key=score.__getitem__, reverse=True):
        if len(chosen) >= max_sentences:
            break
        if score[j] >= 0.2 * score[i] and score[j] > 0:
            chosen.add(j)
    picked = [cands[j][1] for j in sorted(chosen)]
    return {"n": n, "sentences": picked, "score": round(score[i], 3)}


def render_extractive(res):
    return " ".join(res["sentences"]).strip() + f" [{res['n']}]"


# ------------------------------------------------------------------ messages in the user's language
_loc_cache = {}


def localize(text_en, exemplar, cache_key, generate):
    """Translate a fixed English message into the language and script of `exemplar` (the user's question).
    Cached per `cache_key` when the key is reliable. Falls back to the English text if the model fails."""
    if cache_key and (cache_key, text_en) in _loc_cache:
        return _loc_cache[(cache_key, text_en)]
    try:
        out = (generate("You translate short messages. Output only the translation.",
                        f"Translate this message into the same language and script as the question below. "
                        f"Keep the meaning, do not add anything.\n\nMessage: {text_en}\n\nQuestion: {exemplar}",
                        max_tokens=120) or "").strip().strip('"')
    except Exception:
        return text_en
    if not 6 <= len(out) <= 600:
        return text_en
    if cache_key:
        _loc_cache[(cache_key, text_en)] = out
    return out
