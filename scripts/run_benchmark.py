# scripts/run_benchmark.py
import json, statistics, time
from app import db, search, hybrid, rerank
from app.config import ROOT, REPORT_DIR, MIN_VECTOR_SCORE

WS = "demo-workspace"
KS = (1, 3, 5)

def is_relevant(row, rel):
    return any(row["filename"] in r["files"] and r["contains"].lower() in row["text"].lower()
               for r in rel)

def first_rank(rows, rel):
    for i, row in enumerate(rows, 1):
        if is_relevant(row, rel):
            return i
    return None

def evaluate(con, items, mode, strategy):
    fn = {"keyword": search.keyword_search, "vector": search.vector_search,
          "hybrid": hybrid.hybrid_search, "rerank": rerank.rerank_search}[mode]
    ranks = [first_rank(fn(con, WS, it["q"], max(KS), strategy), it["relevant"]) for it in items]
    out = {f"recall@{k}": round(sum(1 for r in ranks if r and r <= k) / len(ranks), 3) for k in KS}
    out["mrr"] = round(sum(1 / r for r in ranks if r) / len(ranks), 3)
    out["missed"] = [it["q"] for it, r in zip(items, ranks) if r is None]
    return out

def top_scores(con, questions):
    scores = []
    for q in questions:
        rows = search.vector_search(con, WS, q, 1, "structure")
        scores.append(rows[0]["score"] if rows else 0.0)
    return scores

def main():
    data = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    ans, unans = data["answerable"], data["unanswerable"]
    con = db.connect()
    rerank.get_model()   # load once so timing excludes model loading

    results = {}
    print(f"{'config':<20}{'R@1':>7}{'R@3':>7}{'R@5':>7}{'MRR':>7}{'ms/q':>8}")
    for mode in ("keyword", "vector", "hybrid", "rerank"):
        for strat in ("structure", "fixed"):
            t0 = time.perf_counter()
            r = evaluate(con, ans, mode, strat)
            ms = (time.perf_counter() - t0) * 1000 / len(ans)
            r["ms_per_query"] = round(ms, 1)
            results[f"{mode}/{strat}"] = r
            print(f"{mode + '/' + strat:<20}{r['recall@1']:>7}{r['recall@3']:>7}"
                  f"{r['recall@5']:>7}{r['mrr']:>7}{ms:>8.0f}")
    for name, r in results.items():
        if r["missed"]:
            print(f"\nMissed by {name} (top 5):")
            for q in r["missed"]:
                print("  -", q)

    a = top_scores(con, [it["q"] for it in ans])
    u = top_scores(con, unans)
    print("\nTop-1 vector score, answerable:   "
          f"min {min(a):.3f}  median {statistics.median(a):.3f}")
    print("Top-1 vector score, unanswerable: "
          f"median {statistics.median(u):.3f}  max {max(u):.3f}")
    answered = sum(s >= MIN_VECTOR_SCORE for s in a) / len(a)
    abstained = sum(s < MIN_VECTOR_SCORE for s in u) / len(u)
    print(f"At MIN_VECTOR_SCORE={MIN_VECTOR_SCORE}: answerable kept {answered:.0%}, "
          f"unanswerable rejected {abstained:.0%}")
    if max(u) >= min(a):
        print("Scores overlap, so no threshold separates them perfectly. Expect trade-offs.")

    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "benchmark.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()