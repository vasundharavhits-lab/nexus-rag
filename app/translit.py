"""Devanagari -> Roman (Hinglish) spelling. Rule based, works for any Hindi text, no model needed.
Final inherent 'a' is dropped (yuddh, arjun, mein), except after 'r' (kurukshetra)."""
import json
import re
from pathlib import Path

CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
}
INDEP = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "ऋ": "ri",
}
MATRA = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri",
}
VIRAMA, NUKTA = "\u094d", "\u093c"
MARKS = {"ं": "n", "ँ": "n", "ः": "h", "।": ".", "॥": "."}
WORD = re.compile(r"[\u0900-\u0963\u0966-\u097F]+")   # the danda (\u0964, \u0965) ends a word, it is not part of it


def _word(w):
    out = []                       # list of (text, inherent_a)
    i = 0
    while i < len(w):
        c = w[i]
        nxt = w[i + 1] if i + 1 < len(w) else ""
        if c == NUKTA:
            i += 1
            continue
        if c in CONS:
            base = CONS[c]
            # skip a nukta that belongs to this consonant
            j = i + 1
            if j < len(w) and w[j] == NUKTA:
                j += 1
            nxt = w[j] if j < len(w) else ""
            if nxt == VIRAMA:
                out.append((base, False)); i = j + 1
            elif nxt == "े" and j + 1 < len(w) and w[j + 1] == "ं":
                out.append((base + "ein", False)); i = j + 2     # में -> mein
            elif nxt in MATRA:
                out.append((base + MATRA[nxt], False)); i = j + 1
            else:
                out.append((base + "a", True)); i = j
        elif c in INDEP:
            out.append((INDEP[c], False)); i += 1
        elif c in MATRA:           # a vowel sign with no consonant before it
            out.append((MATRA[c], False)); i += 1
        else:
            out.append((MARKS.get(c, ""), False)); i += 1
    # drop the final inherent 'a' (yuddh, mein), but keep it after 'r' (kurukshetra)
    if out and out[-1][1]:
        text = out[-1][0]
        if not text[:-1].endswith("r"):
            out[-1] = (text[:-1], False)
    return "".join(t for t, _ in out)


# Optional spelling overrides, edited by you in data/hinglish_words.json (no code change needed).
# Example: {"और": "aur"}. The file may be missing or empty; the rules above then do all the work.
OVERRIDE_FILE = Path(__file__).resolve().parent.parent / "data" / "hinglish_words.json"


def _overrides():
    try:
        return {k: v for k, v in json.loads(OVERRIDE_FILE.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        return {}


def _one(w):
    overrides = _overrides()
    if w in overrides:
        return overrides[w]
    r = _word(w)
    if r.endswith("aa") and len(r) > 2:      # huaa -> hua, kahaa -> kaha, poochhaa -> poochha
        r = r[:-1]
    return r


def dev_to_roman(text):
    text = text.replace("\u0964", ".").replace("\u0965", ".")   # danda -> full stop
    return WORD.sub(lambda m: _one(m.group(0)), text)
