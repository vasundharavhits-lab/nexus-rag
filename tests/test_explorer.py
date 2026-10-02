# tests/test_explorer.py
from fastapi.testclient import TestClient
from app.main import app

def test_explorer_page_is_served():
    with TestClient(app) as c:
        r = c.get("/explorer")
    assert r.status_code == 200 and "NEXUS RAG Explorer" in r.text
