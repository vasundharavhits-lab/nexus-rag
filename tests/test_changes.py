# tests/test_changes.py
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import changes

V1 = (b"# Architecture\nStatus: Draft\nDate: 2026-01-10\n\n## Overview\n"
      b"The system is a monolithic service. Retrieval uses keyword search only.\n\n"
      b"## Storage\nAll data is stored in PostgreSQL.\n")
V2 = (b"# Architecture\nStatus: Approved\nDate: 2026-02-15\n\n## Overview\n"
      b"The system is a monolithic service. Retrieval combines keyword and vector search.\n\n"
      b"## Storage\nAll data is stored in PostgreSQL. Redis is used for caching.\n\n"
      b"## Security\nAccess is checked on every request.\n")
V3 = V2.replace(b"2026-02-15", b"2026-03-20").replace(b"Redis is used for caching.",
                                                      b"Redis is used for caching and queues.")


# ---- understanding the question ------------------------------------------------------
@pytest.mark.parametrize("q,expected", [
    ("What changed from v1 to v3?", ("pair", "v1", "v3")),
    ("What changed between version 1 and version 3?", ("pair", "v1", "v3")),
    ("What are the differences between versions 1 and 3?", ("pair", "v1", "v3")),
    ("Compare v2 with v3", ("pair", "v2", "v3")),
    ("v1 vs v3 architecture", ("pair", "v1", "v3")),
    ("How did retrieval evolve from v1 to v2?", ("pair", "v1", "v2")),
    ("What changed in v3?", ("single", None, "v3")),
    ("What's new in version 2?", ("single", None, "v2")),
    ("What changed since v1?", ("since", "v1", None)),
])
def test_comparison_questions_are_recognised(q, expected):
    s = changes.parse_compare(q)
    assert (s["kind"], s["from"], s["to"]) == expected


@pytest.mark.parametrize("q", [
    "What does version 3 add to the architecture?",
    "In v1, what was used for retrieval?",
    "What is the currently approved architecture?",
    "Why was pgvector chosen?",
    "Does v1 and v3 use redis?",
    "What changed in the system?",
])
def test_ordinary_questions_are_not_comparisons(q):
    assert changes.parse_compare(q) is None


# ---- diffing -----------------------------------------------------------------------
def test_reworded_sentence_is_paired_and_unrelated_ones_are_not():
    ch = changes.diff_sentences("Retrieval uses keyword search only. Alpha beta.",
                                "Retrieval combines keyword and vector search. Gamma delta epsilon.")
    kinds = sorted(c["type"] for c in ch)
    assert kinds == ["added", "removed", "reworded"]


def test_identical_text_has_no_changes():
    assert changes.diff_sentences("One fact here. Another fact.", "One fact here. Another fact.") == []


def test_metadata_lines_are_ignored_in_text_diff():
    assert changes.diff_sentences("Status: Draft\nSame sentence here.",
                                  "Status: Approved\nSame sentence here.") == []


# ---- end to end (real database, no model needed) ---------------------------------------
@pytest.fixture()
def env(monkeypatch):
    calls = []
    monkeypatch.setattr("app.llm.generate", lambda s, u: calls.append(u) or "It stores data [1].")
    with TestClient(app) as c:
        h = {"X-User-Id": f"user-{uuid.uuid4()}"}
        ws = c.post("/api/v1/workspaces", json={"name": "t"}, headers=h).json()["workspace_id"]
        for name, body in (("architecture_v1.md", V1), ("architecture_v2.md", V2),
                           ("architecture_v3.md", V3)):
            c.post(f"/api/v1/documents/upload?workspace_id={ws}",
                   files={"file": (name, body)}, headers=h)
        c.post(f"/api/v1/workspaces/{ws}/index?embed=false", headers=h)
        yield c, h, ws, calls


def ask(c, h, ws, q):
    return c.post("/api/v1/query", headers=h,
                  json={"workspace_id": ws, "question": q, "mode": "keyword"}).json()


def test_compare_answers_from_the_diff_without_calling_the_llm(env):
    c, h, ws, calls = env
    r = ask(c, h, ws, "What changed from v1 to v2?")
    assert r["status"] == "answered" and r["model"] is None and calls == []
    assert r["trace"]["route"] == "version_diff"
    assert "Status changed from Draft to Approved" in r["answer"]
    assert "Retrieval combines keyword and vector search" in r["answer"]
    assert "Security added" in r["answer"]
    assert all(e["chunk_id"] for e in r["citations"])      # every citation can be opened


def test_every_citation_in_the_answer_exists(env):
    c, h, ws, _ = env
    r = ask(c, h, ws, "What changed from v1 to v3?")
    import re
    nums = {int(x) for x in re.findall(r"\[(\d+)\]", r["answer"])}
    assert nums == {e["n"] for e in r["evidence"]} == {e["n"] for e in r["citations"]}


def test_single_version_compares_with_the_previous_one(env):
    c, h, ws, _ = env
    r = ask(c, h, ws, "What changed in v3?")
    assert r["trace"]["from"] == "v2" and r["trace"]["to"] == "v3"
    assert "Redis is used for caching and queues" in r["answer"]


def test_missing_version_is_reported_not_invented(env):
    c, h, ws, calls = env
    r = ask(c, h, ws, "What changed in v9?")
    assert r["status"] == "insufficient_evidence" and calls == []
    assert "v1, v2, v3" in r["answer"]


def test_ordinary_question_still_goes_to_rag(env):
    c, h, ws, calls = env
    r = ask(c, h, ws, "What does version 3 add to the architecture?")
    assert len(calls) == 1 and r["trace"].get("route") != "version_diff"


def test_comparison_run_is_saved_and_visible_in_analytics(env):
    c, h, ws, _ = env
    rid = ask(c, h, ws, "What changed from v1 to v2?")["run_id"]
    assert c.get(f"/api/v1/runs/{rid}", headers=h).status_code == 200
    a = c.get(f"/api/v1/analytics/retrieval?workspace_id={ws}", headers=h).json()
    assert a["total_runs"] == 1 and a["by_status"] == {"answered": 1}


def test_changes_endpoint_and_permissions(env):
    c, h, ws, _ = env
    url = f"/api/v1/changes?workspace_id={ws}&document=architecture&from_label=v1&to_label=v2"
    d = c.get(url, headers=h).json()
    assert d["counts"]["modified"] >= 1 and d["counts"]["added"] == 1
    assert {"field": "status", "old": "Draft", "new": "Approved"} in d["metadata_changes"]
    assert c.get(url, headers={"X-User-Id": "someone-else"}).status_code == 404
    bad = url.replace("to_label=v2", "to_label=v9")
    assert c.get(bad, headers=h).status_code == 404


def test_workspace_with_one_version_falls_back_to_rag(monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda s, u: "It stores data [1].")
    with TestClient(app) as c:
        h = {"X-User-Id": f"user-{uuid.uuid4()}"}
        ws = c.post("/api/v1/workspaces", json={"name": "t"}, headers=h).json()["workspace_id"]
        c.post(f"/api/v1/documents/upload?workspace_id={ws}",
               files={"file": ("architecture_v1.md", V1)}, headers=h)
        c.post(f"/api/v1/workspaces/{ws}/index?embed=false", headers=h)
        r = ask(c, h, ws, "What changed in v1?")
        assert r["trace"].get("route") != "version_diff"


# ---- balanced output (regression: removals must not crowd out additions) ---------------
def _items(**counts):
    return [("Sec", {"type": t, "old": f"o{i}", "new": f"n{i}"})
            for t, n in counts.items() for i in range(n)]


def test_additions_are_not_crowded_out_by_many_removals():
    shown, hidden = changes.select_balanced(_items(removed=12, added=3), max_lines=8)
    kinds = [c["type"] for _, c in shown]
    assert kinds.count("added") == 3 and kinds.count("removed") == 5
    assert hidden == {"removed": 7}


def test_all_kinds_appear_when_space_is_short():
    shown, _ = changes.select_balanced(_items(reworded=5, added=5, removed=5), max_lines=6)
    kinds = [c["type"] for _, c in shown]
    assert {k: kinds.count(k) for k in set(kinds)} == {"reworded": 2, "added": 2, "removed": 2}


def test_nothing_is_hidden_when_under_the_cap():
    shown, hidden = changes.select_balanced(_items(added=2, removed=3), max_lines=10)
    assert len(shown) == 5 and hidden == {}


def test_summary_reports_true_totals():
    s = changes.summarize_counts(_items(removed=12, added=3))
    assert "3 added" in s and "12 removed" in s and "reworded" not in s


# ---- PDF line wraps must not create fake changes ----------------------------------------
def test_wrapped_pdf_lines_are_rejoined_into_one_sentence():
    old = ("Documents are parsed, split into chunks, and indexed using\n"
           "keyword search and PostgreSQL full-text search.\nAnother fact here.")
    assert changes._sentences(old) == [
        "Documents are parsed, split into chunks, and indexed using "
        "keyword search and PostgreSQL full-text search.", "Another fact here."]


def test_wrapped_and_unwrapped_text_produce_no_diff():
    wrapped = "Retrieval uses keyword\nsearch only."
    flat = "Retrieval uses keyword search only."
    assert changes.diff_sentences(wrapped, flat) == []


def test_list_items_stay_separate_and_lose_leading_marker():
    ch = changes._sentences("- What does reranking do?\n- Why are Celery workers used?")
    assert ch == ["What does reranking do?", "Why are Celery workers used?"]
    assert changes._sentences("Items:\n- first item\n- second item") == ["Items:", "first item", "second item"]


def test_invisible_pdf_bullet_glyphs_are_stripped():
    txt = "\uf0b7 What does reranking do?\n\u2022\u00a0Why are Celery workers used?\n\u200b Which metrics?"
    assert changes._sentences(txt) == ["What does reranking do?",
                                       "Why are Celery workers used?", "Which metrics?"]
