# app/embeddings.py
"""Text embeddings for search. The model is chosen in .env (EMBED_MODEL), so Nexus can search documents
in any language the model knows, and a question in one language can find a passage in another.

    EMBED_MODEL=intfloat/multilingual-e5-large     (default: ~100 languages, 1024 dims, ~2.2 GB download)

Other models that work with this file (fastembed names): sentence-transformers/paraphrase-multilingual-
mpnet-base-v2, sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, jinaai/jina-embeddings-v3,
BAAI/bge-small-en-v1.5 (English only). After changing the model, run `python reindex_embeddings.py`:
vectors from different models cannot be compared.
"""
import os
import threading


DEFAULT_MODEL = "intfloat/multilingual-e5-large"
EMBED_MODEL = (os.getenv("EMBED_MODEL") or "").strip() or DEFAULT_MODEL
EMBED_BATCH = 16     # fastembed defaults to 256, which needs multi-GB buffers on big files

_lock = threading.Lock()
_loaded = None


def prefixes(model_name=None):
    """(query_prefix, passage_prefix). Some model families were trained with fixed prefixes and
    search much worse without them."""
    n = (model_name or EMBED_MODEL).lower()
    if "e5" in n:                                                   # intfloat/multilingual-e5-*, e5-*
        return "query: ", "passage: "
    if n.startswith("baai/bge") and (n.endswith("-en") or "-en-" in n):    # English bge: query instruction only
        return "Represent this sentence for searching relevant passages: ", ""
    return "", ""


def _model():
    """Load the embedding model once (also safe if the background warm-up and a request race)."""
    global _loaded
    with _lock:
        if _loaded is None:
            from fastembed import TextEmbedding      # imported here so it loads only when needed
            _loaded = TextEmbedding(model_name=EMBED_MODEL)
        return _loaded


def _embed(texts):
    return [v.tolist() for v in _model().embed(texts, batch_size=EMBED_BATCH)]


def embed_texts(texts):
    """Passages (document chunks)."""
    p = prefixes()[1]
    return _embed([p + t for t in texts])


def embed_query(query):
    """A user question."""
    return _embed([prefixes()[0] + query])[0]


def dimension():
    return len(embed_query("test"))
