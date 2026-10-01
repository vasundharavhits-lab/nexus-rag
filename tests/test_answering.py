import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.answering import parse_citations, dedupe

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
    assert client.post(f"/api/v1/workspaces/{ws}/index?embed=false", headers=h).status_code == 200
    return ws

def ask(client, ws, h, q):
    return client.post("/api/v1/query",
                       json={"workspace_id": ws, "question": q, "mode": "keyword"}, headers=h)

def test_parse_citations():
    valid, invalid = parse_citations("A [1] and B [2, 3] but also [9].", 3)
    assert valid == [1, 2, 3] and invalid == [9]

def test_dedupe_removes_identical_text():
    rows = [{"text": "Same  text"}, {"text": "same text"}, {"text": "other"}]
    assert len(dedupe(rows)) == 2

def test_no_evidence_abstains_without_calling_llm(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("LLM must not be called without evidence")
    monkeypatch.setattr("app.llm.generate", boom)
    h = hdr(); ws = setup_ws(client, h)
    r = ask(client, ws, h, "zzzunknownterm").json()
    assert r["status"] == "insufficient_evidence" and r["citations"] == []

def test_answer_with_valid_citation(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate",
                        lambda s, u: "The pgvector extension stores embeddings [1].")
    h = hdr(); ws = setup_ws(client, h)
    r = ask(client, ws, h, "pgvector").json()
    assert r["status"] == "answered"
    assert r["citations"][0]["filename"] == "storage.md"

def test_answer_without_citation_is_flagged(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "pgvector stores embeddings.")
    h = hdr(); ws = setup_ws(client, h)
    assert ask(client, ws, h, "pgvector").json()["status"] == "uncited"

def test_model_can_declare_insufficient_evidence(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "INSUFFICIENT_EVIDENCE")
    h = hdr(); ws = setup_ws(client, h)
    assert ask(client, ws, h, "pgvector").json()["status"] == "insufficient_evidence"

def test_chunk_endpoint_respects_ownership(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "It stores embeddings [1].")
    alice = hdr(); ws = setup_ws(client, alice)
    cid = ask(client, ws, alice, "pgvector").json()["citations"][0]["chunk_id"]
    ok = client.get(f"/api/v1/chunks/{cid}", headers=alice)
    assert ok.status_code == 200 and "pgvector" in ok.json()["text"]
    assert client.get(f"/api/v1/chunks/{cid}", headers=hdr()).status_code == 404

def test_run_is_stored_and_private(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "It stores embeddings [1].")
    alice = hdr(); ws = setup_ws(client, alice)
    rid = ask(client, ws, alice, "pgvector").json()["run_id"]
    got = client.get(f"/api/v1/runs/{rid}", headers=alice)
    assert got.status_code == 200 and got.json()["status"] == "answered"
    assert client.get(f"/api/v1/runs/{rid}", headers=hdr()).status_code == 404

def test_auto_mode_records_route_and_abstains_without_evidence(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("LLM must not be called without evidence")
    monkeypatch.setattr("app.llm.generate", boom)
    h = hdr(); ws = setup_ws(client, h)
    r = client.post("/api/v1/query", headers=h, json={
        "workspace_id": ws, "mode": "auto",
        "question": "Why did the team adopt this approach for storing data?"}).json()
    assert r["status"] == "insufficient_evidence"
    assert r["trace"]["route"] == "vector" and r["trace"]["mode"] == "auto"

def test_run_stores_trace(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "It stores embeddings [1].")
    h = hdr(); ws = setup_ws(client, h)
    rid = ask(client, ws, h, "pgvector").json()["run_id"]
    got = client.get(f"/api/v1/runs/{rid}", headers=h).json()
    assert "retrieve_ms" in got["timings"]

def test_bare_citation_is_not_an_answer(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "[1]")
    h = hdr(); ws = setup_ws(client, h)
    assert ask(client, ws, h, "pgvector").json()["status"] == "uncited"

def test_refusal_message_mentions_the_question(client, monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "INSUFFICIENT_EVIDENCE")
    h = hdr(); ws = setup_ws(client, h)
    r = ask(client, ws, h, "pgvector").json()
    assert r["status"] == "insufficient_evidence"
    assert "pgvector" in r["answer"] and "storage.md" in r["answer"]