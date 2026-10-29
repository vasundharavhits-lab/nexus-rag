# tests/test_chat_http.py - the language-model layer against a real local HTTP server
import json, threading, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import chatting, llm

SEEN = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if self.path == "/api/chat":                                  # Ollama
            out = {"message": {"content": f"ollama:{body['model']}"}}
        elif self.path == "/v1/chat/completions":                      # OpenAI-compatible
            if self.headers.get("Authorization") != "Bearer sk-good":
                self.send_response(401); self.end_headers(); return
            out = {"choices": [{"message": {"content": f"openai:{body['model']}"}}]}
        else:
            self.send_response(404); self.end_headers(); return
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture(autouse=True)
def clear(monkeypatch):
    SEEN.clear()
    monkeypatch.setattr(chatting, "RATE_LIMIT", 0)
    chatting._hits.clear()


MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]


def test_ollama_over_real_http(server, monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm, "OLLAMA_URL", server)
    monkeypatch.setattr(llm, "CHAT_MODEL", "llama3.2")
    assert llm.chat(MSGS) == "ollama:llama3.2"
    assert SEEN[0]["body"]["messages"] == MSGS and SEEN[0]["body"]["stream"] is False
    assert SEEN[0]["body"]["options"]["temperature"] == llm.CHAT_TEMPERATURE


def test_openai_compatible_over_real_http(server, monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "LLM_BASE_URL", server + "/v1")
    monkeypatch.setattr(llm, "LLM_API_KEY", "sk-good")
    monkeypatch.setattr(llm, "CHAT_MODEL", "gpt-x")
    monkeypatch.setattr(llm, "LLM_MODEL", "small-rag")
    assert llm.chat(MSGS) == "openai:gpt-x"
    assert llm.generate("sys", "question") == "openai:small-rag"        # RAG keeps its own model
    assert SEEN[0]["auth"] == "Bearer sk-good"
    assert SEEN[1]["body"]["temperature"] == 0 and SEEN[1]["body"]["max_tokens"] == llm.LLM_MAX_TOKENS


def test_wrong_key_is_a_clear_503_through_the_api(server, monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "LLM_BASE_URL", server + "/v1")
    monkeypatch.setattr(llm, "LLM_API_KEY", "sk-wrong")
    with TestClient(app) as c:
        r = c.post("/api/v1/chat", headers={"X-User-Id": f"u-{uuid.uuid4()}"},
                   json={"message": "hi", "scope": "general"})
    assert r.status_code == 503
    assert "API key was rejected" in r.json()["detail"] and "sk-wrong" not in r.text


def test_full_chat_request_over_real_http(server, monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "LLM_BASE_URL", server + "/v1")
    monkeypatch.setattr(llm, "LLM_API_KEY", "sk-good")
    monkeypatch.setattr(llm, "CHAT_MODEL", "gpt-x")
    with TestClient(app) as c:
        r = c.post("/api/v1/chat", headers={"X-User-Id": f"u-{uuid.uuid4()}"},
                   json={"message": "Capital of France?", "scope": "general",
                         "history": [{"role": "user", "content": "Hello"},
                                     {"role": "assistant", "content": "Hi!"}]})
    assert r.status_code == 200 and r.json()["answer"] == "openai:gpt-x"
    sent = SEEN[0]["body"]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[-1]["content"] == "Capital of France?"
