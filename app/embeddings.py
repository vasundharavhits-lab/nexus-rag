# app/embeddings.py
from functools import lru_cache
from app.config import EMBED_MODEL

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding      # imported here so it loads only when needed
    return TextEmbedding(model_name=EMBED_MODEL)

EMBED_BATCH = 16     # fastembed defaults to 256, which needs multi-GB buffers on big files


def embed_texts(texts):
    return [v.tolist() for v in _model().embed(texts, batch_size=EMBED_BATCH)]

def embed_query(query):
    return embed_texts([QUERY_PREFIX + query])[0]