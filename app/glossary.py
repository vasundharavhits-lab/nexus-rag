# app/glossary.py
"""Word-level bridge between Roman Hindi (Hinglish), Devanagari Hindi/Sanskrit and English.

The language model is not needed for this: when a question contains a known term, its English
keywords are added to the search, so 'karma aur phal' also searches for 'karma fruit action
reward'. Terms live in data/glossary.json (one line per term) and can be extended for any document
without changing code. Format:  {"term": ["keyword", "keyword"], ...}   Keys are lowercase; Devanagari
and Roman spellings are both listed.
"""
import json, re
from pathlib import Path
from app.config import ROOT

GLOSSARY_FILE = ROOT / "data" / "glossary.json"

# No built-in terms: the glossary is empty unless you add terms in data/glossary.json.
# That keeps the system the same for every document, not only one book.
SEED = {}

_SPLIT = re.compile(r"[\s\.,;:!?'\"()\[\]{}\-|/\\।॥]+")   # whitespace and punctuation; Devanagari matras stay in the word
_cache = None


def _load():
    global _cache
    if _cache is not None:
        return _cache
    data = {k.lower(): v for k, v in SEED.items()}
    try:
        if GLOSSARY_FILE.exists():
            user = json.loads(GLOSSARY_FILE.read_text(encoding="utf-8"))
            data.update({k.lower(): v for k, v in user.items()})
    except (ValueError, OSError):
        pass                                  # a broken file must not stop search; the seed still works
    _cache = data
    return data


def reload():
    global _cache
    _cache = None


def expand(question):
    """English keywords for the known terms in a question. Returns '' when nothing matches.
    Multi-word terms (e.g. 'kaat sakte') are matched first, then single words."""
    text = " ".join(t for t in _SPLIT.split(question.lower()) if t)
    table = _load()
    found = []
    for term in sorted((t for t in table if " " in t), key=len, reverse=True):
        if term in text:
            found += table[term]
            text = text.replace(term, " ")
    for w in _SPLIT.split(text):
        if w in table:
            found += table[w]
    seen, out = set(), []
    for w in found:
        if w.lower() not in seen:
            seen.add(w.lower()); out.append(w)
    return " ".join(out)
