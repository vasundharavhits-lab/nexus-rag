# scripts/nli_try.py
import numpy as np
from sentence_transformers import CrossEncoder

LABELS = ["contradiction", "entailment", "neutral"]   # label order of this model

SRC3 = ("The system adds a reranking stage after hybrid retrieval. "
        "Ingestion runs asynchronously through Celery workers.")
SRC2 = ("PostgreSQL with pgvector remains the primary store. "
        "Redis is used for caching and job queues.")

CLAIMS = [
    "The system uses a reranking stage.",
    "Ingestion runs through Celery workers.",
    "The system uses PostgreSQL with pgvector.",
    "The system uses Redis.",
]

model = CrossEncoder("cross-encoder/nli-deberta-v3-small")

for name, src in (("[3] Overview", SRC3), ("[2] Storage", SRC2)):
    print(name)
    logits = model.predict([(src, c) for c in CLAIMS])
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    for claim, p in zip(CLAIMS, probs):
        print(f"  entailment {p[1]:.2f}  {claim}")