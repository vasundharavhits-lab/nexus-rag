# scripts/verify_one.py
from app.verify import verify_answer

SOURCES = {
    1: "The system adds a reranking stage after hybrid retrieval. "
       "Ingestion runs asynchronously through Celery workers.",
}
ANSWER = "The system uses asynchronous ingestion through Celery workers [1]."

for r in verify_answer(ANSWER, SOURCES):
    print(r["verdict"], r["scores"])
    print(" ", r["claim"])