# scripts/verify_try3.py
from app.verify import _entailment

SRC = ("The system adds a reranking stage after hybrid retrieval. "
       "Ingestion runs asynchronously through Celery workers.")
CLAIMS = [
    "The system adds a reranking stage.",
    "The system adds a reranking stage .",
    "The system uses a reranking stage.",
    "The system uses a reranking stage .",
]

for c, s in zip(CLAIMS, _entailment([(SRC, c) for c in CLAIMS])):
    print(f"{s:.2f}  {c}")