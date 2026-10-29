# scripts/gate_real.py
import json
from app import db, versions
from app.answering import retrieve, is_metadata_only, dedupe
from app.config import ROOT, MIN_VECTOR_SCORE

WS = "demo-workspace"
VERSION_QS = [
    "What is the currently approved architecture?",
    "What is the latest architecture for storing embeddings?",
    "Which architecture design is the most recent?",
    "How does the current architecture handle ingestion?",
    "In v1, what was used for retrieval?",
    "In version 2, how are embeddings stored?",
    "What does version 3 add to the architecture?",
]

def real_gate(con, q, k=4):
    pool = 30 if versions.intent(q)[0] != "none" else k * 2
    rows, _, _, _ = retrieve(con, WS, q, "vector", pool)
    rows = [r for r in rows if not is_metadata_only(r["text"])]
    rows, _ = versions.apply(con, WS, q, dedupe(rows))
    rows = rows[:k]
    return rows[0]["score"] if rows else 0.0

con = db.connect()
data = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))

print("Version questions:")
for q in VERSION_QS:
    s = real_gate(con, q)
    print(f"  {s:.3f}  {'REFUSED' if s < MIN_VECTOR_SCORE else 'ok':<8}{q}")

print("\nUnanswerable (top-1 on the real path):")
u = sorted(real_gate(con, q) for q in data["unanswerable"])
print("  ", [round(x, 3) for x in u])