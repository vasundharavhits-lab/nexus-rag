# scripts/threshold_sweep.py
import json
from app import db
from app.config import ROOT
from scripts.run_benchmark import top_scores

def main():
    data = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    con = db.connect()
    a = top_scores(con, [it["q"] for it in data["answerable"]])
    u = top_scores(con, data["unanswerable"])
    print(f"{'threshold':>9} {'answerable kept':>16} {'unanswerable rejected':>22}")
    for t in (0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.62):
        kept = sum(s >= t for s in a)
        rej = sum(s < t for s in u)
        print(f"{t:>9.2f} {kept:>12}/{len(a)} {rej:>18}/{len(u)}")
    print("\nunanswerable top-1 scores:", sorted(round(s, 3) for s in u))

if __name__ == "__main__":
    main()