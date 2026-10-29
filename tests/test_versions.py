from app import versions

VERSIONS = [
    {"logical_name": "architecture", "version_id": "a1", "label": "v1",
     "doc_status": "Draft", "effective_at": "2026-01-10"},
    {"logical_name": "architecture", "version_id": "a2", "label": "v2",
     "doc_status": "Approved", "effective_at": "2026-02-15"},
    {"logical_name": "architecture", "version_id": "a3", "label": "v3",
     "doc_status": "Approved", "effective_at": "2026-03-20"},
    {"logical_name": "incident_log", "version_id": "i1", "label": "v1",
     "doc_status": None, "effective_at": "2026-04-02"},
]

class FakeCon:
    def execute(self, *a, **k):
        return self
    def fetchall(self):
        return VERSIONS

def row(name, vid, fname):
    return {"logical_name": name, "version_id": vid, "filename": fname, "text": "x"}

def test_intent_current_named_and_none():
    assert versions.intent("What is the currently approved architecture?") == ("current", None)
    assert versions.intent("What did version 1 of the architecture use?") == ("named", "v1")
    assert versions.intent("In v2, how are embeddings stored?") == ("named", "v2")
    assert versions.intent("Why was pgvector chosen?") == ("none", None)
    assert versions.intent("What step reorders results after the first retrieval pass?") == ("none", None)

def test_currency_prefers_approved_then_newest():
    by_id = {x["version_id"]: x for x in VERSIONS}
    best = max([by_id["a1"], by_id["a2"], by_id["a3"]], key=versions.currency_key)
    assert best["version_id"] == "a3"
    newer_draft = {"label": "v4", "doc_status": "Draft", "effective_at": "2026-05-01"}
    assert versions.currency_key(by_id["a3"]) > versions.currency_key(newer_draft)

def test_current_drops_older_versions_of_same_document():
    rows = [row("architecture", "a2", "architecture_v2.md"),
            row("architecture", "a3", "architecture_v3.md"),
            row("incident_log", "i1", "incident_log.md")]
    out, info = versions.apply(FakeCon(), "ws", "What is the current architecture?", rows)
    assert [r["filename"] for r in out] == ["architecture_v3.md", "incident_log.md"]
    assert info["dropped"] == ["architecture_v2.md"]

def test_current_keeps_rows_when_current_version_not_retrieved():
    rows = [row("architecture", "a1", "architecture_v1.md"),
            row("architecture", "a2", "architecture_v2.md")]
    out, info = versions.apply(FakeCon(), "ws", "What is the latest architecture?", rows)
    assert out == rows and info["dropped"] == [] and info["notes"]

def test_named_version_keeps_only_that_version():
    rows = [row("architecture", "a1", "architecture_v1.md"),
            row("architecture", "a3", "architecture_v3.md")]
    out, info = versions.apply(FakeCon(), "ws", "In v1, what was used for retrieval?", rows)
    assert [r["filename"] for r in out] == ["architecture_v1.md"]

def test_no_version_words_changes_nothing():
    rows = [row("architecture", "a1", "architecture_v1.md"),
            row("architecture", "a3", "architecture_v3.md")]
    out, info = versions.apply(FakeCon(), "ws", "Why was pgvector chosen?", rows)
    assert out == rows and info["intent"] == "none"