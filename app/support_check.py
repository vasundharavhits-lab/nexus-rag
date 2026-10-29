# app/support_check.py
"""Checks that a document answer is about what its cited passages say.

No language model is used. The answer's known terms (from data/glossary.json and the built-in list)
are turned into concept groups, e.g. 'फल' -> {fruit, result, reward, outcome}. A concept is supported
when one of its English keywords appears in the cited passages. If too few concepts are supported,
the answer is refused instead of shown with a citation.

Grammar words (is, says, why...) are ignored. Answers with fewer than MIN_CONCEPTS known concepts
cannot be judged, so they are let through; the result says so in the trace.
"""
import re
from app import glossary

MIN_CONCEPTS = 2        # below this there is nothing to compare
SUPPORT_SHARE = 0.75    # share of concepts that must be found in the passages

# Words that carry grammar, not meaning. They are never treated as concepts.
FUNCTION = {
    "kya", "kaun", "kyon", "kyu", "kaise", "kab", "kahan", "kehta", "kehti", "kehte", "hai", "hain",
    "nahi", "nahin", "ki", "ke", "ka", "ko", "se", "mein", "men", "aur", "par", "to", "ye", "yeh", "vah",
    "woh", "wo", "ek", "the", "is", "are", "what", "says", "states", "why", "how", "not", "to", "of",
    "and", "in", "by", "for", "on", "with", "from", "this", "that", "it", "its", "a", "an",
    "को", "के", "का", "की", "में", "है", "हैं", "और", "से", "पर", "नहीं", "यह", "वह", "भी", "तो",
}


def concept_groups(text):
    """Known concepts in the text, each as a tuple of English keywords. Duplicates removed."""
    table = glossary._load()
    tokens = [t for t in glossary._SPLIT.split((text or "").lower()) if t]
    found, seen = [], set()
    i = 0
    while i < len(tokens):
        hit = None
        if i + 1 < len(tokens) and f"{tokens[i]} {tokens[i + 1]}" in table:
            hit, step = f"{tokens[i]} {tokens[i + 1]}", 2
        elif tokens[i] in table:
            hit, step = tokens[i], 1
        if hit and hit not in FUNCTION:
            key = tuple(sorted(k.lower() for k in table[hit]))
            if key not in seen:
                seen.add(key)
                found.append(key)
            i += step
        else:
            i += 1
    return found


def check(answer, passages):
    """Returns (supported, detail). supported is True/False, or None when there is too little to judge."""
    groups = concept_groups(answer)
    if len(groups) < MIN_CONCEPTS:
        return None, {"concepts": len(groups), "note": "too few known terms to compare"}
    source = " ".join(passages).lower()
    hit = [g for g in groups if any(k in source for k in g)]
    share = len(hit) / len(groups)
    missing = [g[0] for g in groups if g not in hit]
    return share >= SUPPORT_SHARE, {"concepts": len(groups), "found": len(hit),
                                    "share": round(share, 2), "missing": missing}
