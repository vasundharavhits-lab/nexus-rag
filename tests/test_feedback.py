# tests/test_feedback.py
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

def make_run(client, monkeypatch, h):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "It stores embeddings [1].")
    ws = client.post("/api/v1/workspaces", json={"name": "t"}, headers=h).json()["workspace_id"]
    client.post(f"/api/v1/documents/upload?workspace_id={ws}",
                files={"file": ("storage.md", DOC)}, headers=h)
    client.post(f"/api/v1/workspaces/{ws}/index?embed=false", headers=h)
    return client.post("/api/v1/query", headers=h, json={
        "workspace_id": ws, "question": "pgvector", "mode": "keyword"}).json()["run_id"]

def test_feedback_is_saved(client, monkeypatch):
    h = hdr(); rid = make_run(client, monkeypatch, h)
    r = client.post("/api/v1/feedback", headers=h, json={
        "run_id": rid, "rating": -1, "issue_type": "bad_citation", "comment": "wrong source"})
    assert r.status_code == 201 and r.json()["run_id"] == rid

def test_feedback_on_someone_elses_run_is_404(client, monkeypatch):
    alice = hdr(); rid = make_run(client, monkeypatch, alice)
    r = client.post("/api/v1/feedback", headers=hdr(), json={"run_id": rid, "rating": 1})
    assert r.status_code == 404

def test_invalid_rating_is_422(client, monkeypatch):
    h = hdr(); rid = make_run(client, monkeypatch, h)
    r = client.post("/api/v1/feedback", headers=h, json={"run_id": rid, "rating": 0})
    assert r.status_code == 422
