# scripts/trace_summary.py
import statistics
from collections import Counter
from app import db

def med(xs):
    return f"{statistics.median(xs):.0f}" if xs else "n/a"

def main():
    con = db.connect()
    runs = con.execute(
        "SELECT query, mode, status, model, timings, created_at FROM query_runs "
        "WHERE workspace_id='demo-workspace' ORDER BY created_at").fetchall()
    if not runs:
        print("No runs yet. Ask some questions through /api/v1/query first.")
        return

    print(f"{len(runs)} runs in demo-workspace\n")
    print("Status:", dict(Counter(r["status"] for r in runs)))
    traced = [r for r in runs if "route" in (r["timings"] or {})]
    print(f"Runs with a route trace: {len(traced)} of {len(runs)}\n")

    print("Route (traced runs):")
    for route, n in Counter(r["timings"]["route"] for r in traced).items():
        sub = [r for r in traced if r["timings"]["route"] == route]
        st = dict(Counter(r["status"] for r in sub))
        print(f"  {route:<8}{n:>3} runs  {st}")

    def ms(r, new, old):
        t = r["timings"] or {}
        return t.get(new, t.get(old))

    retr = [ms(r, "retrieve_ms", "retrieve") for r in runs if ms(r, "retrieve_ms", "retrieve") is not None]
    called = [r for r in runs if r["model"]]
    gen = [ms(r, "generate_ms", "generate") for r in called if ms(r, "generate_ms", "generate") is not None]
    skipped = [ms(r, "total_ms", "total") for r in runs if not r["model"] and ms(r, "total_ms", "total") is not None]

    print("\nTime per stage (ms):")
    print(f"  retrieve   median {med(retr)}   max {max(retr):.0f}")
    print(f"  generate   median {med(gen)}   max {max(gen):.0f}   ({len(called)} runs called the model)")
    print(f"  no model call   median {med(skipped)}   ({len(skipped)} runs answered by the gate)")

    print("\nGate score on traced runs:")
    for label, sub in (("answered", [r for r in traced if r["status"] == "answered"]),
                       ("refused", [r for r in traced if r["status"] == "insufficient_evidence"]),
                       ("uncited", [r for r in traced if r["status"] == "uncited"])):
        s = [r["timings"]["gate_vector_score"] for r in sub if r["timings"].get("gate_vector_score") is not None]
        print(f"  {label:<9}n={len(s)}  scores {sorted(round(x, 3) for x in s)}")

    print("\nModel refused although the gate passed:")
    for r in runs:
        if r["status"] == "insufficient_evidence" and r["model"]:
            print("  -", r["query"])

if __name__ == "__main__":
    main()