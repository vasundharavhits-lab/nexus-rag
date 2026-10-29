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

def setup_ws(client, h):
    ws = client.post("/api/v1/workspaces", json={"name": "t"}, headers=h).json()["workspace_id"]
    client.post(f"/api/v1/documents/upload?workspace_id={ws}",
                files={"file": ("storage.md", DOC)}, headers=h)
    r = client.post(f"/api/v1/workspaces/{ws}/index?embed=false", headers=h)
    assert r.status_code == 200
    return ws

def search(client, ws, h, q):
    return client.post("/api/v1/search",
                       json={"workspace_id": ws, "query": q, "mode": "keyword"}, headers=h)

def test_keyword_search_finds_exact_term(client):
    h = hdr(); ws = setup_ws(client, h)
    r = search(client, ws, h, "pgvector").json()
    assert r["results"] and "pgvector" in r["results"][0]["text"]
    assert r["results"][0]["filename"] == "storage.md"

def test_keyword_search_no_match_returns_empty(client):
    h = hdr(); ws = setup_ws(client, h)
    assert search(client, ws, h, "zzzunknownterm").json()["results"] == []

def test_other_user_cannot_search_workspace(client):
    alice = hdr(); ws = setup_ws(client, alice)
    assert search(client, ws, hdr(), "pgvector").status_code == 404

def test_reindex_is_idempotent(client):
    h = hdr(); ws = setup_ws(client, h)
    a = client.post(f"/api/v1/workspaces/{ws}/index?embed=false", headers=h).json()
    b = client.post(f"/api/v1/workspaces/{ws}/index?embed=false", headers=h).json()
    assert a["chunks"] == b["chunks"]