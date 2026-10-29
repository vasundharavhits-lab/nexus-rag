# tests/test_ingest.py
from app.ingest import ingest_file, extract_metadata

def test_corrupted_pdf_is_failed_not_crash(tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"not a pdf \x00")
    rec, _ = ingest_file(p)
    assert rec["status"] == "failed" and rec["error"]

def test_empty_markdown_is_marked_empty(tmp_path):
    p = tmp_path / "empty.md"
    p.write_text("")
    rec, _ = ingest_file(p)
    assert rec["status"] == "empty"

def test_ids_are_deterministic(tmp_path):
    p = tmp_path / "doc_v2.md"
    p.write_text("# T\nDate: 2026-01-01\nHello world of tests here.")
    a, _ = ingest_file(p)
    b, _ = ingest_file(p)
    assert a["version_id"] == b["version_id"]
    assert a["logical_name"] == "doc" and a["label"] == "v2"

def test_metadata_extraction():
    meta = extract_metadata("Status: Approved\nDate: 2026-02-15")
    assert meta["status"] == "Approved" and meta["date"] == "2026-02-15"
    assert meta["author"] is None