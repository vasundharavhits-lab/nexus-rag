# scripts/verify_try.py
from app.verify import verify_answer

SOURCES = {
    1: "Requirements. The system must support PDF, DOCX and Markdown uploads.",
    2: "PostgreSQL with pgvector remains the primary store. Redis is used for caching and job queues.",
    3: "The system adds a reranking stage after hybrid retrieval. Ingestion runs asynchronously through Celery workers.",
}

ANSWERS = [
    "The architecture uses PostgreSQL with pgvector, Redis, a reranking stage, and Celery workers [3].",
    "The system uses PostgreSQL with pgvector and Redis [2]. It adds a reranking stage and Celery workers [3].",
    "The system uses MongoDB for storage [2].",
]

for a in ANSWERS:
    print(a)
    for r in verify_answer(a, SOURCES):
        print(f"  {r['verdict']:<13} cited {r['cited']} better {r['better_sources']} {r['scores']}")
        print(f"    {r['claim']}")
    print()