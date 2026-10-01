# scripts/verify_two.py
from app.verify import verify_answer, split_claims

SOURCES = {
    1: "PostgreSQL stores metadata and full-text indexes. "
       "The pgvector extension stores embeddings for semantic retrieval.",
}
ANSWER = ("PostgreSQL stores metadata and full-text indexes, while the pgvector "
          "extension stores embeddings for semantic retrieval. [1]")

print("claims found:", len(split_claims(ANSWER)))
for r in verify_answer(ANSWER, SOURCES):
    print(r["verdict"], r["cited"], r["scores"])
    print(" ", r["claim"])