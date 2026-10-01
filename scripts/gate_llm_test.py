# scripts/gate_llm_test.py
import json
from app import db, search, llm
from app.answering import SYSTEM, build_prompt, dedupe, parse_citations
from app.config import ROOT, MIN_VECTOR_SCORE

WS = "demo-workspace"
FILES = ("questions.json", "exact_questions.json", "stress_questions.json")

def evidence_for(con, q):
    rows = dedupe(search.vector_search(con, WS, q, 8, "structure"))[:4]
    ev = [{**r, "n": i} for i, r in enumerate(rows, 1)]
    return ev, (float(rows[0]["score"]) if rows else 0.0)

def ask(con, q):
    ev, top = evidence_for(con, q)
    raw = llm.generate(SYSTEM, build_prompt(q, ev))
    refused = "INSUFFICIENT_EVIDENCE" in raw
    valid, _ = parse_citations(raw, len(ev))
    return top, refused, bool(valid), raw

def main():
    con = db.connect()
    ans, unans = [], []
    for f in FILES:
        d = json.loads((ROOT / "eval" / f).read_text(encoding="utf-8"))
        ans += [it["q"] for it in d["answerable"]]
        unans += d.get("unanswerable", [])
    low = [q for q in ans if evidence_for(con, q)[1] < MIN_VECTOR_SCORE]

    print("UNANSWERABLE: the model should refuse")
    n_ref = 0
    for q in unans:
        top, refused, cited, raw = ask(con, q)
        n_ref += refused
        print(f"  {top:.3f}  {'REFUSED ' if refused else 'ANSWERED'}  {q}")
        if not refused:
            print("         ->", raw[:160].replace("\n", " "))
    print(f"  refused {n_ref} of {len(unans)}")

    print("\nANSWERABLE BUT BELOW THE GATE: the model should answer with a citation")
    n_ok = 0
    for q in low:
        top, refused, cited, raw = ask(con, q)
        ok = (not refused) and cited
        n_ok += ok
        print(f"  {top:.3f}  {'OK     ' if ok else 'PROBLEM'}  {q}")
        print("         ->", raw[:160].replace("\n", " "))
    print(f"  answered with citation {n_ok} of {len(low)}")

if __name__ == "__main__":
    main()