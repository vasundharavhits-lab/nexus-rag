# scripts/time_verifier.py
# Usage: python -m scripts.time_verifier data\raw
import sys, json, uuid, pathlib, statistics
from fastapi.testclient import TestClient
from app.main import app

folder = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
questions = json.load(open("eval/stress_questions.json", encoding="utf-8"))["answerable"]
h = {"X-User-Id": f"time-{uuid.uuid4()}"}

with TestClient(app) as c:
    ws = c.post("/api/v1/workspaces", json={"name": "timing"}, headers=h).json()["workspace_id"]
    for p in folder.rglob("*"):
        if p.suffix.lower() in (".md", ".pdf", ".docx"):
            c.post(f"/api/v1/documents/upload?workspace_id={ws}",
                   files={"file": (p.name, p.read_bytes())}, headers=h)
    c.post(f"/api/v1/workspaces/{ws}/index", headers=h)

    rows = []
    for item in questions:
        res = c.post("/api/v1/query", headers=h, json={
            "workspace_id": ws, "question": item["q"], "mode": "auto"}).json()
        if res["status"] != "answered":
            continue
        t = res["trace"]
        v, g = t.get("verify_ms"), t["generate_ms"]
        if v is None:
            print("verify_ms is missing from the trace: the edit in answering.py did not land.")
            raise SystemExit
        rows.append((item["q"], g, v))
        print(f"generate_total={g:8.1f} ms | verifier={v:8.1f} ms | {item['q']}")

    warm = rows[1:]   # the first answered question loads the models, so it is skipped
    print(f"\nAnswered questions timed: {len(warm)} (first one skipped as warm-up)")
    print("First call verifier (model loading):", rows[0][2], "ms")
    print("Median verifier time:", round(statistics.median(r[2] for r in warm), 1), "ms")
    print("Median generation time without verifier:",
          round(statistics.median(r[1] - r[2] for r in warm), 1), "ms")