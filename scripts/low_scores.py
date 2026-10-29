# scripts/low_scores.py
import json
from app import db
from app.config import ROOT, MIN_VECTOR_SCORE
from scripts.run_benchmark import top_scores

con = db.connect()
data = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
qs = [it["q"] for it in data["answerable"]]
scores = top_scores(con, qs)

low = sorted((s, q) for s, q in zip(scores, qs) if s < MIN_VECTOR_SCORE)
print(f"Answerable questions below {MIN_VECTOR_SCORE}:")
for s, q in low:
    print(f"  {s:.3f}  {q}")