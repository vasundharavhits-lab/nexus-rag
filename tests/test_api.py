import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

GOOD_MD = b"# T\nStatus: Approved\nDate: 2026-01-01\nHello world of tests right here."

@pytest.fixture()
def client():
    with TestClient(app) as c:      # 'with' runs startup, which creates the tables
        yield c

def hdr(user=None):
    return {"X-User-Id": user or f"user-{uuid.uuid4()}"}

def new_ws(client, h):
    r = client.post("/api/v1/workspaces", json={"name": "t"}, headers=h)
    assert r.status_code == 201
    return r.json()["workspace_id"]

def upload(client, ws, h, name, data):
    return client.post(f"/api/v1/documents/upload?workspace_id={ws}",
                       files={"file": (name, data)}, headers=h)

def test_missing_user_header_is_401(client):
    assert client.post("/api/v1/workspaces", json={"name": "x"}).status_code == 401

def test_upload_and_inspect(client):
    h = hdr(); ws = new_ws(client, h)
    r = upload(client, ws, h, "arch_v2.md", GOOD_MD)
    assert r.status_code == 201
    g = client.get(f"/api/v1/documents/{r.json()['version_id']}", headers=h)
    assert g.status_code == 200
    body = g.json()
    assert body["status"] == "ok" and body["label"] == "v2"
    assert "source_uri" not in body

def test_corrupted_pdf_is_recorded_not_crash(client):
    h = hdr(); ws = new_ws(client, h)
    r = upload(client, ws, h, "broken.pdf", b"not a pdf \x00")
    assert r.status_code == 201 and r.json()["status"] == "failed"

def test_other_user_cannot_access_workspace_or_document(client):
    alice, bob = hdr(), hdr()
    ws = new_ws(client, alice)
    vid = upload(client, ws, alice, "a.md", GOOD_MD).json()["version_id"]
    assert upload(client, ws, bob, "b.md", GOOD_MD).status_code == 404
    assert client.get(f"/api/v1/documents/{vid}", headers=bob).status_code == 404
    assert client.get(f"/api/v1/analytics/corpus?workspace_id={ws}", headers=bob).status_code == 404

def test_unsupported_type_is_415(client):
    h = hdr(); ws = new_ws(client, h)
    assert upload(client, ws, h, "virus.exe", b"x").status_code == 415

def test_corpus_analytics_counts(client):
    h = hdr(); ws = new_ws(client, h)
    upload(client, ws, h, "a.md", GOOD_MD)
    upload(client, ws, h, "empty.md", b"")
    rep = client.get(f"/api/v1/analytics/corpus?workspace_id={ws}", headers=h).json()
    assert rep["by_status"] == {"ok": 1, "empty": 1}