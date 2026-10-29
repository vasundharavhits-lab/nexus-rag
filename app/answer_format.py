# app/answer_format.py
"""Answer clean-up and repair, used by answering.py.

The small local model often fails on Hindi / Hinglish questions: it copies one verse line,
or returns only a citation such as "[2]". This module
  * tidies the model's text (citation placement, stray echoes),
  * detects a poor answer (too short, or a copied verse line),
  * and, as a last resort, builds a plain answer from the English translation that sits next
    to the Hindi text in the passage, but only if that sentence clearly matches the question.
Pure functions: no database, no model.
"""
import re
from app import extractive as ex

CITE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
PUNCT = re.compile(r"[\[\]()|\u0964\u0965.,;:!?\"'\u201c\u201d\u2018\u2019\-\u2013\u2014]")
LEAD_CITE = re.compile(r"^\s*(\[\d+(?:\s*,\s*\d+)*\])\s+(\S.*)$", re.S)
ECHO = re.compile(r"^\s*\(?\s*english meaning of the question.*$", re.I | re.M)
ANSWER_LABEL = re.compile(r"^\s*(answer|uttar|उत्तर)\s*[:\-]\s*", re.I)
DEVANAGARI = re.compile(r"[\u0900-\u097F]")

STOP = set("""a an the is are was were be been do does did can could would will shall should may might
why what who whom how when where which that this these those it its they them their he she his her we
you your i me my to of in on at by for from with as and or not no nor so than then there here into out
up about over under again further once only own same too very s t just don now""".split())
STOP |= set("""happens happen say said tell told mean means about after before according kind type give gives because due""".split())
# words that appear in almost every passage of the corpus: a match on them alone proves nothing
# Generic English words that carry no topic on their own. Names and topic words are NOT listed here,
# so every document is scored the same way.
GENERIC = {"the", "and", "of", "to", "in", "is", "are", "was", "were", "be", "it", "that", "this", "with",
           "for", "as", "on", "by", "at", "from", "or", "an", "a", "all", "one", "said", "what", "who",
           "how", "why", "where", "when", "which", "does", "do", "did", "can", "about"}
# Hindi-English glossary words that the translation uses differently
SYNONYMS = {
    "kill": ["slain", "slay", "killed", "destroy", "destroyed"],
    "cut": ["cut", "cuts", "pierce", "weapons", "weapon", "sword"],
    "weapon": ["weapons", "weapon", "sword", "cut"],
    "weapons": ["weapons", "weapon", "sword", "cut"],
    "burn": ["burn", "burns", "burnt", "fire"],
    "fire": ["fire", "burn", "burns"],
    "wet": ["wet", "water", "wets"],
    "water": ["water", "wet", "wets"],
    "dry": ["dry", "wind", "dries"],
    "wind": ["wind", "dry", "dries"],
    "atma": ["soul", "self"],
    "death": ["death", "die", "dies", "born"],
    "body": ["body", "bodies"],
    "anger": ["anger", "angry", "wrath", "wrathful"],
    "angry": ["anger", "angry", "wrath"],
    "grieve": ["grieve", "grief", "sorrow", "sad", "sadness", "compassion", "dejected"],
    "sorrow": ["grieve", "grief", "sorrow", "sad", "sadness", "compassion"],
    "action": ["action", "actions", "karma", "duty", "work"],
    "karm": ["action", "actions", "karma", "duty", "work"],
    "karma": ["action", "actions", "karma", "duty", "work"],
    "war": ["war", "battle", "fight", "battlefield"],
    "battle": ["war", "battle", "fight", "battlefield"],
}
GENERIC_HI = {"आत्मा", "अर्जुन", "कृष्ण", "भगवान", "भगवान्", "श्रीभगवान", "श्लोक", "अध्याय"}
QWORDS_HI = {"क्यों", "क्या", "कैसे", "कौन", "कब", "कहाँ", "कहां", "कितना", "कितने", "सकते", "सकता", "सकती",
             "होता", "होती", "होते", "बारे", "बताओ", "बताइए"}


def strip_cites(text):
    return CITE.sub("", text or "")


def body(text):
    """The answer without its [n] markers, trimmed."""
    return re.sub(r"\s+", " ", strip_cites(text)).strip()


def tidy(raw):
    """Conservative clean-up. English answers that are already fine come back unchanged."""
    t = (raw or "").strip()
    t = ECHO.sub("", t).strip()
    t = ANSWER_LABEL.sub("", t)
    t = re.sub(r"\[(\d+)\]\s*\[(\d+)\]", r"[\1, \2]", t)           # [1][2] -> [1, 2]
    m = LEAD_CITE.match(t)
    if m and not CITE.search(m.group(2)):                           # "[1] text" -> "text [1]"
        t = m.group(2).strip() + " " + m.group(1)
    return t


def norm(text):
    return re.sub(r"\s+", " ", PUNCT.sub(" ", (text or "").lower())).strip()


def degenerate(text):
    """True when the text loops on the same words (few distinct words for its length)."""
    words = body(text).lower().split()
    return len(words) >= 12 and len(set(words)) / len(words) < 0.5


def looks_sanskrit(text):
    """Devanagari text with no Hindi function words: a verse line, not an explanation."""
    toks = re.findall(r"[\u0900-\u097F]+", text or "")
    return bool(toks) and not any(t in HINDI_MARKERS for t in toks)


def is_poor(answer, source_texts):
    """True when the answer is not a real answer: too short, looping, or a copied verse line."""
    b = body(answer)
    words = b.split()
    if len(words) < 4 or degenerate(b):
        return True
    n = norm(b)
    copied = any(n and n in norm(t) for t in source_texts)
    return copied and (looks_sanskrit(b) or len(words) <= 8)


def clean_generated(raw):
    """Repair typical small-model output: leaked tags, echoed instructions, repeated or cut-off sentences."""
    t = tidy(raw)
    t = re.sub(r"\[\s*source\s*id\s*=\s*(\d+(?:\s*,\s*\d+)*)\s*\]", r"[\1]", t, flags=re.I)
    t = re.sub(r"\(\s*source\s*id\s*=\s*(\d+(?:\s*,\s*\d+)*)\s*\)", r"[\1]", t, flags=re.I)
    t = re.sub(r"\b(?:the\s+)?direct answer(?:\s+is)?(?:\s+that)?\s*[:,]?\s*", "", t, flags=re.I)
    t = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    parts = [p for p in re.split(r"(?<=[.!?\u0964\u0965])\s+", t.strip()) if p.strip()]
    first_style = bool(re.match(r"\s*\[\d", t))
    sents = []
    for part in parts:
        if first_style:
            m = LEAD_CITE.match(part)
            sents.append((m.group(2).strip() + " " + m.group(1)) if m else part.strip())
        else:
            m = re.match(r"^((?:\[\d+(?:\s*,\s*\d+)*\]\s*)+)(.*)$", part, re.S)
            if m and sents:
                sents[-1] += " " + m.group(1).strip()
                if m.group(2).strip():
                    sents.append(m.group(2).strip())
            else:
                sents.append(part.strip())
    out, seen = [], set()
    for sent in sents:
        sent = re.sub(r"(?<!\S)(\S+)(?:\s+\1)+(?!\S)", r"\1", sent)      # "yahan yahan" -> "yahan"
        key = norm(strip_cites(sent))
        if key and key not in seen:
            seen.add(key)
            out.append(sent)
    if len(out) > 1 and not re.search(r"[.!?\u0964\u0965]\s*(\[[\d,\s]+\])*\s*$", out[-1]):
        out.pop()                                                          # cut off by the token limit
    return " ".join(out).strip()


def covers_topic(queries, evidence):
    """False when none of the passages mentions what the question is about.

    Looks for the question's specific words (English version, with synonyms) in the passages'
    English text, or its Devanagari content words in the Hindi text. If the question gave
    nothing to check, returns True so it never blocks on missing information.
    """
    texts = " ".join(e["text"] for e in evidence)
    checked = False
    eng = pick_english(queries)
    if eng:
        specific, _ = question_terms(eng)
        if specific:
            checked = True
            if specific & _stems(re.findall(r"[a-z]+", texts.lower())):
                return True
    for q in queries:
        if latin_ratio(q) > 0.85:
            continue
        for tok in re.findall(r"[\u0900-\u097F]+", q):
            if len(tok) < 3 or tok in HINDI_MARKERS or tok in QWORDS_HI or tok in GENERIC_HI:
                continue
            checked = True
            if tok[:max(3, len(tok) - 2)] in texts:
                return True
    return not checked


def is_hindi_question(question, is_hinglish):
    """True for questions the small local model handles badly: Hinglish, or any script other than
    Latin (Hindi, Marathi, Tamil, Arabic, Chinese ...). The name is kept for older callers."""
    return any(c.isalpha() and ord(c) > 0x24F for c in question) or bool(is_hinglish(question))


def latin_ratio(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(("a" <= c.lower() <= "z") for c in letters) / len(letters)


def pick_english(queries):
    """The English version of the question among the search queries, or None."""
    for q in queries:
        if latin_ratio(q) > 0.85:
            return q
    return None


def english_sentences(text):
    """Sentences of the English translation that sits among the Hindi text of a passage."""
    out = []
    for run in re.findall(r"[A-Za-z][A-Za-z0-9 ,;:'\u2019\"()\-.!?]{15,}", text or ""):
        run = re.sub(r"^(?:[IVXl|]+\s+)+(?=[A-Z])", "", run.strip())
        for s in re.split(r"(?<=[.!?])\s+", run):
            s = s.strip()
            if len(s.split()) >= 4 and latin_ratio(s) > 0.85:
                out.append(s)
    return out


def _stems(words):
    return {w[:4] for w in words if len(w) > 2}


def question_terms(english_question):
    """(specific, generic) stem sets that a matching sentence must contain."""
    words = [w for w in re.findall(r"[a-z]+", english_question.lower()) if w not in STOP]
    expanded = set(words)
    for w in words:
        expanded.update(SYNONYMS.get(w, []))
    specific = _stems(w for w in expanded if w not in GENERIC)
    generic = _stems(w for w in expanded if w in GENERIC)
    return specific, generic


HINDI_MARKERS = set("""है हैं के की का को में से यह इस इन तू हे नहीं लिये लिए पर ही भी तो था थी थे हो होता होते
वह वे जो जिस उस और कि तुम तेरे मैं मेरे हम सब कोई उन""".split())
SEGMENT_SPLIT = re.compile(r"[\u0964\u0965|]+")


def shorten(text, limit=450):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    m = max(cut.rfind(". "), cut.rfind("\u0964"))
    return (cut[:m + 1] if m > limit * 0.4 else cut).strip()


def meaning_parts(text):
    """Split a passage into (hindi_meaning, english_translation); the Sanskrit verse is dropped."""
    hindi, english = [], []
    for seg in SEGMENT_SPLIT.split(text or ""):
        seg = seg.strip()
        if not seg:
            continue
        m = re.search(r"[A-Za-z]{3,}", seg)
        dev = len(DEVANAGARI.findall(seg))
        if m and len(re.findall(r"[A-Za-z]", seg)) >= dev:             # English translation
            english.append(seg[m.start():].strip())
        elif any(tok in HINDI_MARKERS for tok in re.findall(r"[\u0900-\u097F]+", seg)):   # Hindi meaning
            seg = re.sub(r"^[\d\u0966-\u096F()\s.]+", "", seg).strip()
            if seg:
                hindi.append(seg + " \u0964")
        # otherwise: a Sanskrit verse line or a verse number, left out
    return " ".join(hindi).strip(), " ".join(english).strip()


def meaning_text(text):
    """A passage without its Sanskrit verse (Hindi meaning + English translation); the full text if nothing is left."""
    hindi, english = meaning_parts(text)
    out = (hindi + " " + english).strip()
    return out if len(out) >= 20 else (text or "").strip()


def best_passage(queries, evidence, semantic=None):
    """The passage that best answers the question, or None. Works on any text: words are matched by
    prefix and weighted by how rare they are in the retrieved passages; `semantic(query, sentences)`
    (optional) adds meaning-based matching. The sentences chosen are attached as `_selected`."""
    res = ex.extract(queries, evidence, semantic, markers=HINDI_MARKERS)
    if not res:
        return None
    e = next(x for x in evidence if x["n"] == res["n"])
    return dict(e, _selected=res["sentences"])


def book_answer(e, devanagari=False, queries=None, lang=None, semantic=None):
    """A readable answer made only of the document's own sentences, with the citation. `lang` is
    'devanagari', 'hinglish' or 'en' and only chooses the one-line header."""
    lang = lang or ("devanagari" if devanagari else "hinglish")
    sents = e.get("_selected")
    if not sents:
        res = ex.extract(queries, [e], semantic, markers=HINDI_MARKERS) if queries else None
        sents = res["sentences"] if res else \
            ex.drop_verse_lines(ex.sentences(e["text"]), HINDI_MARKERS)[:3]
    if not sents:
        sents = [shorten(re.sub(r"\s+", " ", e["text"]).strip(), 450)]
    return ex.render(e["n"], sents, ex.HEADERS.get(lang, ex.HEADERS["en"]))


def strip_question_echo(text, *questions):
    """Remove the question if the model repeated it at the start of its answer."""
    t = (text or "").strip()
    low = t.lower()
    for q in questions:
        core = (q or "").strip().rstrip("?").strip().lower()
        i = low.find(core) if core else -1
        if 0 <= i <= 40:
            t = (t[:i] + t[i + len(core):]).lstrip(" ?.:,-")
            break
    return t


def extract_answer(english_question, evidence):
    """Best matching English sentence from the passages as {'n', 'text'}, or None.

    A sentence qualifies only if it shares at least one specific word with the question
    (not just 'soul' or 'self') and two words in total. Otherwise the passage is not about
    the question and nothing is returned.
    """
    if not english_question:
        return None
    specific, generic = question_terms(english_question)
    best, best_score = None, 0
    for e in evidence:
        sents = english_sentences(e["text"])
        for i, s in enumerate(sents):
            st = _stems(re.findall(r"[a-z]+", s.lower()))
            hit_specific, hit_generic = len(st & specific), len(st & generic)
            if hit_specific < 1 or hit_specific + hit_generic < 2:
                continue
            score = hit_specific * 2 + hit_generic
            if score > best_score:
                text = s
                if len(s.split()) < 8 and i + 1 < len(sents):      # very short: add the next sentence
                    text = s + " " + sents[i + 1]
                best, best_score = {"n": e["n"], "text": text, "meaning": shorten(meaning_text(e["text"]))}, score
    return best


# --- answer in the language the user asks for ---------------------------------------------------
WANT_HINDI = re.compile(
    r"\b(?:ans(?:wer)?|reply|jawab|uttar)\s+(?:me|mein|in)\s+hindi\b|\bin\s+hindi\b|"
    r"\bhindi\s+(?:me|mein|mai)\b|\bhindi\s+(?:ans(?:wer)?|jawab|uttar)\b|"
    r"\u0939\u093f\u0902\u0926\u0940\s*(?:\u092e\u0947\u0902|\u092e\u0947)?|"
    r"\u0939\u093f\u0928\u094d\u0926\u0940\s*(?:\u092e\u0947\u0902|\u092e\u0947)?", re.I)


def wants_hindi(question):
    """True when the question is written in Devanagari or asks for the answer in Hindi."""
    return bool(DEVANAGARI.search(question or "")) or bool(WANT_HINDI.search(question or ""))


def strip_language_request(question):
    """Remove an instruction such as "ans in hindi" so it is not searched for as a topic.
    The question is returned unchanged when nothing meaningful would be left."""
    cleaned = re.sub(r"\s+", " ", WANT_HINDI.sub(" ", question or "")).strip(" ,.;:-")
    return cleaned if len(cleaned.split()) >= 2 else question


def hindi_pick(queries, evidence, semantic=None):
    """Like best_passage, but only the Hindi meaning of each passage is considered (the Sanskrit
    verse and the English translation are left out). None when no passage has a matching Hindi sentence."""
    hindi_only = []
    for e in evidence:
        hindi, _english = meaning_parts(e["text"])
        if hindi:
            hindi_only.append(dict(e, text=hindi))
    res = ex.extract(queries, hindi_only, semantic, markers=HINDI_MARKERS) if hindi_only else None
    if not res:
        return None
    e = next(x for x in evidence if x["n"] == res["n"])
    return dict(e, _selected=res["sentences"])
