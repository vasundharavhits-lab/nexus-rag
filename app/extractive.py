# app/extractive.py
"""Generic extractive answering: pick the sentences of a retrieved passage that answer the
question and show them cleanly, with the citation. Nothing here is specific to one book, one
language or one layout:

  * words are matched by prefix (so 'weapons' finds 'weapon', and Indic word endings work),
  * word importance is measured on the retrieved text itself (inverse document frequency), so
    words that appear everywhere are ignored automatically,
  * an optional `semantic(query, sentences)` function (the embedding model) adds meaning-based
    matching, which handles synonyms in any language the model understands,
  * scan noise (stray symbols, broken lines, hyphenated line ends) is cleaned generically.

Pure functions: no database and no language model. `semantic` is passed in by the caller.
"""
import math, re, unicodedata

_SEP = r"\s\-\u2013\u2014,;:!?()\[\]{}\"'\u201c\u201d\u2018\u2019|\u0964\u0965./\\<>=+*#@~_`"
_TOKEN = re.compile(r"[^" + _SEP + r"]+")
_JUNK = re.compile(r"[\u00a9\u00ae\u00a6~_^\u00a7\u00b6\u2022\u25a0\u25a1\u25aa\u25cf=<>]+")
_SENT_END = re.compile(r"(?<=[.!?\u0964\u0965\u3002\u061f\uff01\uff1f])\s+|\s*\|\s*")
_NUM_TAIL = re.compile(r"\s*\(\d{1,3}(?:\s*[&,\-\u2013]\s*\d{1,3})*\)\s*$")
_NUM_END = re.compile(r"(?<=\))\s+(?=[^\W\d_])")            # "... dry it. (23) For this soul" -> split
_LEAD_NOISE = re.compile(r"^[\d\u0966-\u096F\sIVXl|()\-]+(?=[^\W\d_])")
_SHORT_OK = frozenset("a i o of to in is it he we me be by or on at as an if no so do up us my".split())

STOP = frozenset("""a an the is are was were be been being do does did can could would will shall should may
might must why what who whom whose how when where which that this these those it its they them their he
she his her we you your i me my to of in on at by for from with as and or not no nor so than then there
here into out up about over under again further once only own same too very s t just don now also any
each other some such if but because while during after before between through""".split())


# --- text helpers ---------------------------------------------------------------------
def script_of(text):
    """'latin', 'devanagari' or 'other': the dominant script of the letters in text."""
    lat = dev = oth = 0
    for c in text or "":
        if not c.isalpha():
            continue
        o = ord(c)
        if o <= 0x24F or 0x1E00 <= o <= 0x1EFF:
            lat += 1
        elif 0x0900 <= o <= 0x097F:
            dev += 1
        else:
            oth += 1
    if not (lat or dev or oth):
        return "latin"
    return max((("latin", lat), ("devanagari", dev), ("other", oth)), key=lambda x: x[1])[0]


def tokens(text):
    return [t.lower() for t in _TOKEN.findall(text or "")]


def stem(tok):
    n = len(tok)
    return tok if n <= 4 else tok[:max(4, math.ceil(n * 0.8))]


def query_stems(queries):
    out = set()
    for q in queries or []:
        for t in tokens(q):
            if len(t) > 2 and t not in STOP and not t.isdigit():
                out.add(stem(t))
    return out


def clean_text(text):
    """Generic scan clean-up that keeps paragraph breaks."""
    t = _JUNK.sub(" ", text or "")
    t = re.sub(r"(?<=\w)-\n(?=\w)", "", t)                       # hyphenated line end
    paras = []
    for para in re.split(r"\n\s*\n", t):
        lines = [ln.strip() for ln in para.splitlines() if sum(c.isalnum() for c in ln) >= 2]
        if lines:
            paras.append(" ".join(lines))
    return "\n\n".join(paras)


def _denoise(s):
    """Scans often put one or two stray characters of another script inside a sentence ('... wind dry
    एव च For this soul ...'). In a Latin sentence of reasonable length, such short foreign runs are removed."""
    toks = s.split()
    if len(toks) < 6 or script_of(s) != "latin":
        return s
    keep, run = [], []
    def flush():
        if len(run) > 2:
            keep.extend(run)                        # a longer foreign run is real text: keep it
        run.clear()
    for t in toks:
        if any(ord(c) > 0x24F and (c.isalnum() or unicodedata.category(c).startswith('M')) for c in t):
            run.append(t)
        else:
            flush(); keep.append(t)
    flush()
    return " ".join(keep)


def sentences(text):
    """Split into sentences in any common script; tiny fragments are joined to the next sentence."""
    out = []
    for para in clean_text(text).split("\n\n"):
        para = _NUM_END.sub("\n", para)
        for part in re.split(r"\n+", para):
            for s in _SENT_END.split(part):
                s = _LEAD_NOISE.sub("", s.strip()).strip()
                s = re.sub(r"(?<=[A-Za-z])\d(?=[a-z]{3,})", "", s)        # "2verlasting"
                s = _denoise(s)
                s = re.sub(r"[\u0964\u0965][\s\u0964\u0965|]*$", "\u0964", s)  # "।।" -> "।"
                if sum(c.isalpha() for c in s) >= 2:
                    out.append(s)
    merged, carry = [], ""
    for s in out:
        s = (carry + " " + s).strip() if carry else s
        carry = ""
        if len(tokens(s)) < 3:
            carry = s                                         # too short on its own: prepend to the next
            continue
        merged.append(s)
    if carry and merged:
        merged[-1] += " " + carry
    return merged


def drop_verse_lines(sents, markers):
    """Mixed passages that hold an unexplained verse line next to its explanation (Sanskrit next to
    Hindi, Latin next to English, ...): when some sentences in a script contain ordinary function
    words (`markers`) and others do not, the others are verse lines and are dropped. Nothing is
    dropped when all of them look alike, so a document in any other language is left untouched."""
    if not markers:
        return sents
    dev = [s for s in sents if script_of(s) == "devanagari"]
    has = [s for s in dev if any(t in markers for t in tokens(s))]
    if has and len(has) < len(dev):
        return [s for s in sents if s not in dev or s in has]
    return sents


# --- scoring --------------------------------------------------------------------------
def _matches(toks, qstem):
    return any(t.startswith(qstem) for t in toks)


def score_sentences(queries, sents, semantic=None):
    """Returns (scores, lex, sem): `scores` in [0, 1] per sentence = weighted query-word coverage,
    blended with meaning-based similarity when `semantic` is given; `lex` and `sem` are the parts."""
    qs = query_stems(queries)
    toks = [tokens(s) for s in sents]
    n = max(1, len(sents))
    weights = {}
    for q in qs:
        df = sum(_matches(t, q) for t in toks)
        if df:
            w = math.log(1 + n / df)
            weights[q] = w * (0.3 if df / n > 0.5 and n >= 4 else 1.0)     # appears everywhere: weak signal
    total = sum(weights.values())
    lex = [(sum(w for q, w in weights.items() if _matches(t, q)) / total) if total else 0.0 for t in toks]
    sem = None
    if semantic and sents:
        try:
            raw = semantic(queries[0] if queries else "", sents)
        except Exception:
            raw = None
        if raw and len(raw) == len(sents):
            sem = raw
    if sem is None:
        return lex, lex, None
    lo, hi = min(sem), max(sem)
    norm = [(x - lo) / (hi - lo) if hi > lo else 0.0 for x in sem]
    return [0.65 * a + 0.35 * b for a, b in zip(lex, norm)], lex, sem


def extract(queries, evidence, semantic=None, max_sent=2, markers=None, min_sem=0.55):
    """Best passage and its best sentences: {'n', 'sentences', 'score'} or None when no passage is
    about the question. `evidence` = [{'n': 1, 'text': ...}, ...] in rank order."""
    best = None
    for rank, e in enumerate(evidence):
        sents = drop_verse_lines(sentences(e["text"]), markers)
        if not sents:
            continue
        scores, lex, sem = score_sentences(queries, sents, semantic)
        top = max(scores)
        if not (any(x > 0 for x in lex) or (sem and max(sem) >= min_sem)):
            continue                                   # no shared word and not close in meaning
        if top <= 0:
            continue
        key = (round(top, 6), -rank)
        if best is None or key > best[0]:
            best = (key, e, sents, scores)
    if best is None:
        return None
    _, e, sents, scores = best
    order = sorted(range(len(sents)), key=lambda k: (-scores[k], k))
    cut = max(scores) * 0.5
    chosen = [k for k in order if scores[k] >= cut and scores[k] > 0][:max_sent]
    first = chosen[0]
    if (len(tokens(sents[first])) < 6 or sents[first].rstrip()[-1:] in ",;:") and first + 1 < len(sents) \
            and first + 1 not in chosen:
        chosen.append(first + 1)                                    # short or cut-off: add the next sentence
    chosen = sorted(chosen)
    return {"n": e["n"], "sentences": [_NUM_TAIL.sub("", sents[k]).strip() for k in chosen],
            "score": round(max(scores), 4)}


# --- display --------------------------------------------------------------------------
HEADERS = {"devanagari": "\u0906\u092a\u0915\u0947 \u0926\u0938\u094d\u0924\u093e\u0935\u0947\u091c\u093c \u092e\u0947\u0902 \u092f\u0939 \u0932\u093f\u0916\u093e \u0939\u0948:",
           "hinglish": "Aapke document mein yeh likha hai:",
           "en": "From your document:"}


def render(n, sents, header):
    """Header, then the sentences grouped by script (a bilingual passage shows each language on its own
    line), each line ending with the citation."""
    groups, cur, cur_script = [], [], None
    for s in sents:
        sc = script_of(s)
        if cur and sc != cur_script:
            groups.append(" ".join(cur)); cur = []
        cur.append(s); cur_script = sc
    if cur:
        groups.append(" ".join(cur))
    return "\n\n".join([header] + [f"{g} [{n}]" for g in groups])
