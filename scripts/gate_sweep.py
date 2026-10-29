# scripts/gate_sweep.py
import json
from app import db, search
from app.config import ROOT, MIN_VECTOR_SCORE

WS = "demo-workspace"
FILES = ("questions.json", "exact_questions.json", "stress_questions.json")

def top(con, q):
    rows = search.vector_search(con, WS, q, 1, "structure")
    return float(rows[0]["score"]) if rows else 0.0

def main():
    con = db.connect()
    ans, unans = [], []
    for f in FILES:
        d = json.loads((ROOT / "eval" / f).read_text(encoding="utf-8"))
        ans += [(it["q"], top(con, it["q"])) for it in d["answerable"]]
        unans += [(q, top(con, q)) for q in d.get("unanswerable", [])]

    print(f"{len(ans)} answerable, {len(unans)} unanswerable\n")
    print(f"Answerable questions below the current gate ({MIN_VECTOR_SCORE}):")
    for q, s in sorted(ans, key=lambda x: x[1]):
        if s < MIN_VECTOR_SCORE:
            print(f"  {s:.3f}  {q}")
    print("\nHighest-scoring unanswerable questions:")
    for q, s in sorted(unans, key=lambda x: -x[1])[:4]:
        print(f"  {s:.3f}  {q}")

    print(f"\n{'gate':>6}{'answerable kept':>18}{'unanswerable rejected':>24}")
    for t in (0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.62):
        kept = sum(s >= t for _, s in ans) / len(ans)
        rej = sum(s < t for _, s in unans) / len(unans)
        print(f"{t:>6.2f}{kept:>18.0%}{rej:>24.0%}")

if __name__ == "__main__":
    main()