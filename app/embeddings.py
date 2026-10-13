# app/embeddings.py
# The model comes from EMBED_MODEL (.env), so any language can be used. Prefixes are chosen
# per model family: e5 models want "query: " / "passage: ", bge English models want a query prefix.
import threading
from app.config import EMBED_MODEL

_lock = threading.Lock()
_loaded = None


def _prefixes(model: str):
    """(query_prefix, passage_prefix) for the model family."""
    m = model.lower()
    if "e5" in m:
        return "query: ", "passage: "
    if "bge" in m:
        return "Represent this sentence for searching relevant passages: ", ""
    return "", ""


QUERY_PREFIX, PASSAGE_PREFIX = _prefixes(EMBED_MODEL)


def _model():
    """Load the embedding model once (also safe if the background warm-up and a request race)."""
    global _loaded
    with _lock:
        if _loaded is None:
            from fastembed import TextEmbedding      # imported here so it loads only when needed
            _loaded = TextEmbedding(model_name=EMBED_MODEL)
        return _loaded


EMBED_BATCH = 16     # fastembed defaults to 256, which needs multi-GB buffers on big files


def _embed(texts):
    return [v.tolist() for v in _model().embed(texts, batch_size=EMBED_BATCH)]


def embed_texts(texts):
    """Passages (used when indexing)."""
    return _embed([PASSAGE_PREFIX + t for t in texts] if PASSAGE_PREFIX else list(texts))


def embed_query(query):
    return _embed([QUERY_PREFIX + query])[0]
