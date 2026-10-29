# scripts/diagnose_router.py
import json
from app import db, search, hybrid, router
from app.config import ROOT
from scripts.run_benchmark import first_rank

WS = "demo-workspace"

def main():
    con = db.connect()
    path = ROOT / "eval" / "stress_questions.json"
    items = json.loads(path.read_text(encoding="utf-8"))["answerable"]
    print(f"{'question':<52}{'route':<8}{'vec':>4}{'hyb':>4}{'kw':>4}")
    for it in items:
        route, _ = router.classify(it["q"])
        fns = (search.vector_search, hybrid.hybrid_search, search.keyword_search)
        ranks = [first_rank(fn(con, WS, it["q"], 5, "structure"), it["relevant"]) for fn in fns]
        print(f"{it['q']:<52}{route:<8}" + "".join(f"{str(r):>4}" for r in ranks))
        if route == "hybrid" and ranks[1] != 1:
            top = hybrid.hybrid_search(con, WS, it["q"], 1, "structure")
            if top:
                print("    hybrid top-1:", top[0]["filename"], ">", top[0]["heading_path"])

if __name__ == "__main__":
    main()