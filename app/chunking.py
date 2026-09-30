# app/chunking.py
import re, uuid
from app.config import CHUNK_MAX_WORDS, CHUNK_OVERLAP_WORDS
from app.ingest import NS

def _split_long(words, max_words, overlap):
    step = max(1, max_words - overlap)
    pieces = []
    for start in range(0, len(words), step):
        pieces.append(" ".join(words[start:start + max_words]))
        if start + max_words >= len(words):
            break
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
            w = len(p.split())
            if w > max_words:                       # one huge paragraph: split it
                if buf:
                    emit("\n\n".join(buf)); buf, n = [], 0
                for piece in _split_long(p.split(), max_words, overlap):
                    emit(piece)
                continue
            if buf and n + w > max_words:           # buffer full: start a new chunk
                emit("\n\n".join(buf)); buf, n = [], 0
            buf.append(p); n += w
        if buf:
            emit("\n\n".join(buf))
    return out

def chunk_fixed(sections, max_words=CHUNK_MAX_WORDS, overlap=CHUNK_OVERLAP_WORDS):
    words = " ".join(s["text"] for s in sections).split()
    return [{"heading_path": "(fixed)", "page": None, "text": t}
            for t in _split_long(words, max_words, overlap)]

STRATEGIES = {"structure": chunk_structure, "fixed": chunk_fixed}

def build_chunks(version_id, sections, strategy="structure"):
    rows = []
    for i, c in enumerate(STRATEGIES[strategy](sections)):
        rows.append({
            "chunk_id": str(uuid.uuid5(NS, f"{version_id}:{strategy}:{i}")),  # deterministic
            "idx": i, **c, "word_count": len(c["text"].split()),
        })
    return rows