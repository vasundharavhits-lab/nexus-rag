# scripts/run_router_eval.py
import json, time
from app import db, search, hybrid, router
from app.config import ROOT
from scripts.run_benchmark import first_rank

WS = "demo-workspace"
KS = (1, 3, 5)

def auto(con, ws, q, k, strat):
    return router.routed_search(con, ws, q, k, strat)[0]

MODES = {"keyword": search.keyword_search, "vector": search.vector_search,
         "hybrid": hybrid.hybrid_search, "auto": auto}

def run(con, items, label):
    print(f"\n{label} ({len(items)} questions)")
    print(f"{'mode':<10}{'R@1':>7}{'R@3':>7}{'R@5':>7}{'MRR':>7}{'ms/q':>8}")
    for name, fn in MODES.items():
        t0 = time.perf_counter()
        ranks = [first_rank(fn(con, WS, it["q"], max(KS), "structure"), it["relevant"])
                 for it in items]
        ms = (time.perf_counter() - t0) * 1000 / len(items)
        rec = [round(sum(1 for r in ranks if r and r <= k) / len(ranks), 3) for k in KS]
        mrr = round(sum(1 / r for r in ranks if r) / len(ranks), 3)
        print(f"{name:<10}{rec[0]:>7}{rec[1]:>7}{rec[2]:>7}{mrr:>7}{ms:>8.0f}")
        missed = [it["q"] for it, r in zip(items, ranks) if r is None]
        if missed:
            print("   missed:", "; ".join(missed))

def main():
    con = db.connect()
    for fname, label in (("questions.json", "Paraphrased questions"),
                         ("exact_questions.json", "Exact-term questions"),
                         ("stress_questions.json", "Stress questions")):
        data = json.loads((ROOT / "eval" / fname).read_text(encoding="utf-8"))
        run(con, data["answerable"], label)
    for fname in ("exact_questions.json", "stress_questions.json"):
        print(f"\nRoutes chosen for {fname}:")
        data = json.loads((ROOT / "eval" / fname).read_text(encoding="utf-8"))
        for it in data["answerable"]:
            route, why = router.classify(it["q"])
            print(f"  {it['q']:<52} -> {route:<7} ({why})")

if __name__ == "__main__":
    main()