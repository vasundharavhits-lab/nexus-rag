# scripts/verify_try2.py
from app.verify import verify_answer

SOURCES = {
    3: "The system adds a reranking stage after hybrid retrieval. Ingestion runs asynchronously through Celery workers.",
}

ANSWERS = [
    "It adds a reranking stage [3].",
    "The system adds a reranking stage [3].",
    "The system adds a reranking stage and uses Celery workers [3].",
    "The system adds a reranking stage, and ingestion runs through Celery workers [3].",
]

for a in ANSWERS:
    r = verify_answer(a, SOURCES)[0]
    print(f"{r['scores'][3]:.2f}  {a}")