# tests/test_analytics.py
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

DOC = (b"# Storage\nStatus: Approved\nDate: 2026-01-01\n\n"
       b"The pgvector extension stores embeddings for semantic retrieval.\n\n"
       b"## Cache\nRedis caches job queues for workers.")

@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c

def hdr():
    return {"X-User-Id": f"user-{uuid.uuid4()}"}

def new_ws(client, h):
    return client.post("/api/v1/workspaces", json={"name": "t"}, headers=h).json()["workspace_id"]

def test_empty_workspace_has_zero_runs(client):
    h = hdr(); ws = new_ws(client, h)
    r = client.get(f"/api/v1/analytics/retrieval?workspace_id={ws}", headers=h)
    assert r.status_code == 200 and r.json() == {"total_runs": 0}

def test_summary_counts_runs_and_feedback(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "It stores embeddings [1].")
    h = hdr(); ws = new_ws(client, h)
    client.post(f"/api/v1/documents/upload?workspace_id={ws}",
                files={"file": ("storage.md", DOC)}, headers=h)
    client.post(f"/api/v1/workspaces/{ws}/index?embed=false", headers=h)
    rid = client.post("/api/v1/query", headers=h, json={
        "workspace_id": ws, "question": "pgvector", "mode": "keyword"}).json()["run_id"]
    client.post("/api/v1/feedback", headers=h, json={"run_id": rid, "rating": 1})
    client.post("/api/v1/feedback", headers=h, json={
        "run_id": rid, "rating": -1, "issue_type": "bad_citation"})
    r = client.get(f"/api/v1/analytics/retrieval?workspace_id={ws}", headers=h).json()
    assert r["total_runs"] == 1 and r["by_status"] == {"answered": 1}
    assert r["answered_rate"] == 1.0 and r["model_calls"] == 1
    assert r["median_ms"]["retrieve"] is not None
    assert r["feedback"]["thumbs_up"] == 1 and r["feedback"]["thumbs_down"] == 1
    assert r["feedback"]["issues"] == {"bad_citation": 1}

def test_other_user_cannot_read_analytics(client):
    alice = hdr(); ws = new_ws(client, alice)
    r = client.get(f"/api/v1/analytics/retrieval?workspace_id={ws}", headers=hdr())
    assert r.status_code == 404
