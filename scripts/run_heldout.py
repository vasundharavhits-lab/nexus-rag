# scripts/run_heldout.py
import json
from app import db, versions, answering
from app.config import ROOT, MIN_VECTOR_SCORE
from scripts.run_benchmark import first_rank

WS = "demo-workspace"
K = 4

def run_one(con, q):
    pool = K * 2 if versions.intent(q)[0] == "none" else 30
    raw, gate, route, _ = answering.retrieve(con, WS, q, "auto", pool)
    raw = [r for r in raw if not answering.is_metadata_only(r["text"])]
    rows, _ = versions.apply(con, WS, q, answering.dedupe(raw))
    rows = rows[:K]
    if route == "vector":
        gate = rows[0]["score"] if rows else None
    return rows, gate, route, answering.enough_evidence("auto", rows, gate)

def fmt(g):
    return f"{g:.3f}" if g is not None else "none"

def main():
    data = json.loads((ROOT / "eval" / "heldout_questions.json").read_text(encoding="utf-8"))
    con = db.connect()
    print(f"Gate threshold: {MIN_VECTOR_SCORE}\n\nANSWERABLE")
    ranks, kept = [], 0
    for it in data["answerable"]:
        rows, gate, route, passed = run_one(con, it["q"])
        r = first_rank(rows, it["relevant"])
        ranks.append(r)
        kept += passed
        print(f"  rank={str(r):<5}gate={fmt(gate):<7}{'pass' if passed else 'REFUSED':<8}{route:<7}{it['q']}")
    n = len(ranks)
    print(f"  Recall@1 {sum(1 for r in ranks if r == 1) / n:.2f}   "
          f"Recall@{K} {sum(1 for r in ranks if r) / n:.2f}   "
          f"MRR {sum(1 / r for r in ranks if r) / n:.3f}")
    print(f"  passed the gate: {kept}/{n}\n\nUNANSWERABLE")
    refused = 0
    for q in data["unanswerable"]:
        rows, gate, route, passed = run_one(con, q)
        refused += (not passed)
        print(f"  gate={fmt(gate):<7}{'REFUSED' if not passed else 'PASSED (wrong)':<16}{route:<7}{q}")
    print(f"  refused by the gate: {refused}/{len(data['unanswerable'])}")

if __name__ == "__main__":
    main()
