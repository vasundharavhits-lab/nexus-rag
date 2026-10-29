# app/quote_check.py
"""Removes quotations that the sources do not contain.

A language model can write a sentence in quotation marks, cite a passage, and still make the sentence
up. This check takes every quoted segment in the answer, in any script and any quotation-mark style,
and looks for it in the passages the model was shown. Matching ignores case, punctuation, and the
spacing differences OCR introduces, and allows a few words to differ, so real quotes from OCR text
still match. A quotation that cannot be found is removed from the answer, together with the quote
marks. Nothing is checked by a language model, so it is fast and works offline.
"""
import re, unicodedata

# Quotation-mark pairs for many languages: "..." “...” ‘...’ «...» „...“ 「...」 „...” ‚...‘
_PAIRS = re.compile(r'"([^"\n]{8,})"|“([^”\n]{8,})”|«([^»\n]{8,})»|„([^“”\n]{8,})[“”]|「([^」\n]{4,})」')
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
MIN_WORDS = 3            # quotes shorter than this are not checked (single words are often fine)
COVERAGE = 0.8           # share of quoted words that must appear in the sources


def _norm(text):
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join(_WORD.findall(text))


def _quoted(answer):
    for m in _PAIRS.finditer(answer):
        seg = next(g for g in m.groups() if g is not None)
        yield m.group(0), seg


def supported(quote, source_norms):
    """True when the quote's words appear, in order-free fashion, in some source passage."""
    words = _norm(quote).split()
    if len(words) < MIN_WORDS:
        return True
    for src in source_norms:
        if " ".join(words) in src:                      # exact
            return True
        src_words = set(src.split())
        if sum(w in src_words for w in words) / len(words) >= COVERAGE:
            return True
    return False


def strip_unsupported(answer, passage_texts):
    """Returns (cleaned_answer, removed_quotes). passage_texts: list of passage strings."""
    norms = [_norm(t) for t in passage_texts if t]
    removed = []
    out = answer
    for whole, seg in _quoted(answer):
        if not supported(seg, norms):
            removed.append(seg)
            out = out.replace(whole, "", 1)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([.,;:।])", r"\1", out).strip()
    return out, removed


def copies_source(answer, passage_texts, n=8):
    """True when the answer repeats a run of n or more words that appears in a passage.
    A plain-language answer should never reproduce a verse or a source line word for word."""
    src = _norm(" ".join(t for t in passage_texts if t)).split()
    if len(src) < n:
        return False
    grams = {tuple(src[i:i + n]) for i in range(len(src) - n + 1)}
    words = _norm(answer).split()
    return any(tuple(words[i:i + n]) in grams for i in range(len(words) - n + 1))
