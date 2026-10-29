# app/chunking.py
import re, uuid
from app.config import CHUNK_MAX_WORDS, CHUNK_OVERLAP_WORDS
from app.ingest import NS
from app import grounding as gr

# "Size" of a text is counted in words, but scripts written without spaces (Chinese, Japanese, Thai) have almost
# none, so gr.units() treats about two characters as one word there. Sentences end at the marks of every script.


def _split_chars(text, max_units, overlap):
    """Cut a long unspaced text into pieces of at most `max_units` 'words' (two characters each)."""
    size, ov = max(2, max_units * 2), max(0, overlap * 2)
    step = max(1, size - ov)
    pieces = []
    for start in range(0, len(text), step):
        pieces.append(text[start:start + size])
        if start + size >= len(text):
            break
    return pieces


def _split_long(words, max_words, overlap):
    step = max(1, max_words - overlap)
    pieces = []
    for start in range(0, len(words), step):
        pieces.append(" ".join(words[start:start + max_words]))
        if start + max_words >= len(words):
            break
    return pieces


def _cut_sentence(s, max_words, overlap):
    """One sentence longer than the limit: cut by words (or by characters for unspaced scripts)."""
    if len(s.split()) < gr.units(s):                     # unspaced script
        return _split_chars(s, max_words, overlap)
    return _split_long(s.split(), max_words, overlap)


def _split_long_text(text, max_words, overlap):
    """Split one long block into pieces of at most `max_words`, cutting only at sentence ends.
    Consecutive pieces share whole trailing sentences (up to `overlap` words). A single
    sentence longer than `max_words` is cut by words, as before."""
    sents = [s for s in gr.SENT_SPLIT.split(text) if s]
    pieces, cur, n = [], [], 0
    for s in sents:
        w = gr.units(s)
        if w > max_words:                              # one giant "sentence"
            if cur:
                pieces.append(" ".join(cur)); cur, n = [], 0
            pieces += _cut_sentence(s, max_words, overlap)
            continue
        if cur and n + w > max_words:
            pieces.append(" ".join(cur))
            carry, m = [], 0
            for t in reversed(cur):
                tw = gr.units(t)
                if m + tw > overlap:
                    break
                carry.insert(0, t); m += tw
            if m + w > max_words:
                carry, m = [], 0
            cur, n = carry, m
        cur.append(s); n += w
    if cur:
        pieces.append(" ".join(cur))
    return pieces

def chunk_structure(sections, max_words=CHUNK_MAX_WORDS, overlap=CHUNK_OVERLAP_WORDS):
    out = []
    for s in sections:
        buf, n = [], 0

        def emit(text):
            out.append({"heading_path": s["heading_path"], "page": s["page"], "text": text})

        for p in re.split(r"\n\s*\n", s["text"]):
            p = p.strip()
            if not p:
                continue
            w = gr.units(p)
            if w > max_words:                       # one huge paragraph: split it
                if buf:
                    emit("\n\n".join(buf)); buf, n = [], 0
                for piece in _split_long_text(p, max_words, overlap):
                    emit(piece)
                continue
            if buf and n + w > max_words:           # buffer full: start a new chunk
                emit("\n\n".join(buf)); buf, n = [], 0
            buf.append(p); n += w
        if buf:
            emit("\n\n".join(buf))
    return out

def chunk_fixed(sections, max_words=CHUNK_MAX_WORDS, overlap=CHUNK_OVERLAP_WORDS):
    text = " ".join(s["text"] for s in sections)
    pieces = _cut_sentence(text, max_words, overlap) if text.split() else []
    return [{"heading_path": "(fixed)", "page": None, "text": t} for t in pieces]

STRATEGIES = {"structure": chunk_structure, "fixed": chunk_fixed}

def build_chunks(version_id, sections, strategy="structure"):
    rows = []
    for i, c in enumerate(STRATEGIES[strategy](sections)):
        rows.append({
            "chunk_id": str(uuid.uuid5(NS, f"{version_id}:{strategy}:{i}")),  # deterministic
            "idx": i, **c, "word_count": gr.units(c["text"]),
        })
    return rows
