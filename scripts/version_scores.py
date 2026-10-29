# scripts/version_scores.py
from app import db
from app.config import MIN_VECTOR_SCORE
from scripts.run_benchmark import top_scores

QS = [
    "What is the currently approved architecture?",
    "What is the latest architecture for storing embeddings?",
    "Which architecture design is the most recent?",
    "How does the current architecture handle ingestion?",
    "In v1, what was used for retrieval?",
    "In version 2, how are embeddings stored?",
    "What does version 3 add to the architecture?",
]

con = db.connect()
for s, q in zip(top_scores(con, QS), QS):
    flag = "REFUSED" if s < MIN_VECTOR_SCORE else "ok"
    print(f"  {s:.3f}  {flag:<8}{q}")