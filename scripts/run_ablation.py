# scripts/run_ablation.py
import json, random, time
from app import db, search, hybrid, rerank, router
from app.config import ROOT, REPORT_DIR
from scripts.run_benchmark import first_rank

WS = "demo-workspace"
FILES = ("questions.json", "exact_questions.json", "stress_questions.json")

def auto(con, ws, q, k, strat):
    return router.routed_search(con, ws, q, k, strat)[0]

CONFIGS = {   # name -> (function, chunking strategy)
    "A vector/structure (baseline)": (search.vector_search, "structure"),
    "A2 vector/fixed":               (search.vector_search, "fixed"),
    "keyword only":                  (search.keyword_search, "structure"),
    "B hybrid (RRF)":                (hybrid.hybrid_search, "structure"),
    "C hybrid + rerank":             (rerank.rerank_search, "structure"),
    "E auto router":                 (auto, "structure"),
}

def load_items():
    items = []
    for f in FILES:
        for it in json.loads((ROOT / "eval" / f).read_text(encoding="utf-8"))["answerable"]:
            items.append({**it, "set": f})
    return items

def boot_ci(values, n=2000, seed=7):
    rng = random.Random(seed)
    m = len(values)
    means = sorted(sum(values[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]

def main():
    items = load_items()
    con = db.connect()
    rerank.get_model()                      # load once so timing excludes model loading
    rr, ms_per_q, hits = {}, {}, {}
    for name, (fn, strat) in CONFIGS.items():
        t0 = time.perf_counter()
        ranks = [first_rank(fn(con, WS, it["q"], 5, strat), it["relevant"]) for it in items]
        ms_per_q[name] = (time.perf_counter() - t0) * 1000 / len(items)
        rr[name] = [1 / r if r else 0.0 for r in ranks]
        hits[name] = [r is not None and r <= 1 for r in ranks], [r is not None and r <= 5 for r in ranks]

    base = rr["A vector/structure (baseline)"]
    print(f"{len(items)} questions pooled from {len(FILES)} sets\n")
    print(f"{'config':<32}{'R@1':>6}{'R@5':>6}{'MRR':>7}  {'95% CI':<15}{'diff vs A (95% CI)':<26}{'ms/q':>6}")
    out = {}
    for name in CONFIGS:
        r1, r5 = (sum(h) / len(items) for h in hits[name])
        mrr = sum(rr[name]) / len(items)
        lo, hi = boot_ci(rr[name])
        diffs = [a - b for a, b in zip(rr[name], base)]
        dlo, dhi = boot_ci(diffs)
        dm = sum(diffs) / len(diffs)
        flag = "" if dlo <= 0 <= dhi else "  *"
        print(f"{name:<32}{r1:>6.2f}{r5:>6.2f}{mrr:>7.3f}  [{lo:.2f}, {hi:.2f}]    "
              f"{dm:+.3f} [{dlo:+.2f}, {dhi:+.2f}]{flag:<4}{ms_per_q[name]:>6.0f}")
        out[name] = {"r@1": r1, "r@5": r5, "mrr": mrr, "mrr_ci": [lo, hi],
                     "diff_vs_baseline": dm, "diff_ci": [dlo, dhi], "ms_per_q": ms_per_q[name]}
    print("\n* = the 95% interval of the difference excludes 0")
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "ablation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()