# app/chatting.py
"""Nexus as a normal chatbot that also knows your documents.

scope="documents"  only answer from the workspace (strict: cited, claim-checked, refuses)
scope="general"    ordinary assistant, any topic; the documents are not used
scope="auto"       try the documents first; when they do not cover the question, answer from
                   the model's general knowledge and say so

General answers are never presented as document-backed: no citations, no claim check, and the
response carries source="general" plus a note the UI shows next to the answer.
"""
import collections, threading, time, uuid
from app import answering, db, llm
from app.config import (CHAT_MODEL, CHAT_HISTORY_MESSAGES, CHAT_HISTORY_CHARS,
                        CHAT_RATE_LIMIT_PER_MIN)

GENERAL_SYSTEM = (
    "You are Nexus, a friendly and knowledgeable assistant. Answer questions on any topic "
    "helpfully and accurately, in clear plain language. Be concise by default; use short lists "
    "or code blocks when they make the answer easier to follow. "
    "If you are not sure, or the question needs current information you do not have, say so "
    "instead of guessing. "
    "You cannot see the user's uploaded documents in this reply. If a question seems to be about "
    "the user's own files, company or system, say you cannot see it rather than inventing details."
)

NOTE_FALLBACK = ("Nothing in your documents answers this, so this reply comes from the model's "
                 "general knowledge. It is not checked against your files.")
NOTE_NO_DOCS = ("No indexed documents are connected, so this reply comes from the model's "
                "general knowledge.")
NOTE_GENERAL = "General answer from the model's own knowledge. It is not checked against your files."


class WorkspaceNotFound(Exception):
    pass


class RateLimited(Exception):
    pass


RATE_LIMIT = CHAT_RATE_LIMIT_PER_MIN
_hits = collections.deque()
_lock = threading.Lock()


def check_rate(now=None):
    """Sliding one-minute window over all chat requests. Raises RateLimited when full."""
    if RATE_LIMIT <= 0:
        return
    now = time.monotonic() if now is None else now
    with _lock:
        while _hits and now - _hits[0] > 60:
            _hits.popleft()
        if len(_hits) >= RATE_LIMIT:
            raise RateLimited()
        _hits.append(now)


def clean_history(history):
    """Keep the last few well-formed turns, newest last, within a character budget."""
    msgs = []
    for m in history or []:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
        text = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
        if role in ("user", "assistant") and isinstance(text, str) and text.strip():
            msgs.append({"role": role, "content": text.strip()[:4000]})
    msgs = msgs[-CHAT_HISTORY_MESSAGES:]
    while msgs and sum(len(m["content"]) for m in msgs) > CHAT_HISTORY_CHARS:
        msgs.pop(0)
    while msgs and msgs[0]["role"] == "assistant":      # a conversation starts with the user
        msgs.pop(0)
    return msgs


def owns_workspace(con, workspace_id, user_id):
    if not workspace_id:
        return False
    return con.execute("SELECT 1 FROM workspaces WHERE workspace_id=%s AND owner=%s",
                       (workspace_id, user_id)).fetchone() is not None


def has_documents(con, workspace_id):
    return con.execute(
        "SELECT 1 FROM chunks c JOIN document_versions v ON v.version_id=c.version_id "
        "JOIN documents d ON d.document_id=v.document_id "
        "WHERE d.workspace_id=%s AND v.status='ok' LIMIT 1", (workspace_id,)).fetchone() is not None


def _general(con, workspace_id, user_id, message, history, scope, note, extra_trace=None):
    t0 = time.perf_counter()
    msgs = [{"role": "system", "content": GENERAL_SYSTEM}] + clean_history(history) \
        + [{"role": "user", "content": message}]
    text = llm.chat(msgs)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    trace = {"mode": "general", "route": "general", "reason": scope, "scope": scope,
             "history_messages": len(msgs) - 2, "retrieve_ms": 0.0, "generate_ms": ms,
             "verify_ms": 0.0, "total_ms": ms, **(extra_trace or {})}
    result = {"run_id": str(uuid.uuid4()), "status": "general_answer", "source": "general",
              "answer": text, "note": note, "citations": [], "evidence": [],
              "invalid_citations": [], "model": CHAT_MODEL, "verification": None,
              "saved": False, "trace": trace,
              "timings_ms": {"retrieve": 0.0, "generate": ms, "total": ms}}
    if workspace_id and owns_workspace(con, workspace_id, user_id):
        db.save_run(con, {"run_id": result["run_id"], "workspace_id": workspace_id,
                          "user_id": user_id, "query": message, "mode": "general", "k": 0,
                          "status": "general_answer", "answer": text, "model": CHAT_MODEL,
                          "evidence": [], "timings": trace})
        result["saved"] = True
    return result


def reply(con, workspace_id, user_id, message, history=None, scope="auto", mode="auto", k=4):
    check_rate()
    history = history or []
    if scope == "general":
        return _general(con, workspace_id, user_id, message, history, scope, NOTE_GENERAL)

    ok = owns_workspace(con, workspace_id, user_id)
    if scope == "documents":
        if not ok:
            raise WorkspaceNotFound()
        res = answering.answer_question(con, workspace_id, user_id, message, mode, k)
        res["source"], res["saved"] = "documents", True
        return res

    # scope == "auto". A missing or foreign workspace is treated as "no documents": it must
    # not reveal whether that workspace exists, and a chatbot should still answer.
    if not ok:
        return _general(con, workspace_id, user_id, message, history, scope, NOTE_NO_DOCS)
    if not has_documents(con, workspace_id):
        return _general(con, workspace_id, user_id, message, history, scope, NOTE_NO_DOCS)

    res = answering.answer_question(con, workspace_id, user_id, message, mode, k)
    if res["status"] != "insufficient_evidence":
        res["source"], res["saved"] = "documents", True
        return res
    # The documents do not cover it: keep the refusal run (it is a coverage-gap signal) and
    # answer from general knowledge, linking the two runs.
    gate = res["trace"].get("gate_vector_score")
    return _general(con, workspace_id, user_id, message, history, scope, NOTE_FALLBACK,
                    {"doc_attempt_run": res["run_id"], "doc_gate_score": gate})
