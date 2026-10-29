# scripts/eval_abstain.py
# Usage: python -m scripts.eval_abstain <folder with your test documents>
import sys, json, uuid, pathlib
from fastapi.testclient import TestClient
from app.main import app

folder = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "data")
questions = json.load(open("eval/stress_questions.json", encoding="utf-8"))
h = {"X-User-Id": f"eval-{uuid.uuid4()}"}

with TestClient(app) as c:
    ws = c.post("/api/v1/workspaces", json={"name": "eval-abstain"}, headers=h).json()["workspace_id"]
    files = [p for p in folder.rglob("*") if p.suffix.lower() in (".md", ".pdf", ".docx")]
    print(f"Uploading {len(files)} files from {folder} ...")
    for p in files:
        c.post(f"/api/v1/documents/upload?workspace_id={ws}",
               files={"file": (p.name, p.read_bytes())}, headers=h)
    r = c.post(f"/api/v1/workspaces/{ws}/index", headers=h)
    print("Index status:", r.status_code)

    def ask(q):
        return c.post("/api/v1/query", headers=h,
                      json={"workspace_id": ws, "question": q, "mode": "auto"}).json()

    ok_abstain = 0
    print("\n--- Unanswerable questions (should abstain) ---")
    for item in questions["unanswerable"]:
        res = ask(item["q"])
        good = res["status"] == "insufficient_evidence"
        ok_abstain += good
        score = res["trace"]["gate_vector_score"]
        print(("OK   " if good else "FAIL ") + f'[{res["status"]}] score={score} | {item["q"]}')

    wrong_abstain = 0
    print("\n--- Answerable questions (should NOT abstain) ---")
    for item in questions["answerable"]:
        res = ask(item["q"])
        bad = res["status"] == "insufficient_evidence"
        wrong_abstain += bad
        score = res["trace"]["gate_vector_score"]
        print(("FAIL " if bad else "OK   ") + f'[{res["status"]}] score={score} | {item["q"]}')

    n_u, n_a = len(questions["unanswerable"]), len(questions["answerable"])
    print(f"\nCorrect abstentions: {ok_abstain}/{n_u}")
    print(f"Wrong abstentions on answerable questions: {wrong_abstain}/{n_a}")