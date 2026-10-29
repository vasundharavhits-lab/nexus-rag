# tests/test_pdf_structure.py
from app.parsing import pdf_sections
from app.chunking import chunk_structure

PAGE1 = """Data Governance Policy
Status: Approved    Date: 2026-05-01
Author: Governance Office
Purpose and Scope
This policy defines how documents are classified. It applies to all internal policies.
Retention and Deletion
Retention periods depend on category. Owners decide what is archived.
Removal from active retrieval is tracked separately from deletion."""
PAGE2 = """It also covers training materials.
Quality Reviews
High impact documents are reviewed on a schedule."""


def test_headings_become_section_names():
    secs = pdf_sections([PAGE1])
    assert [s["heading_path"] for s in secs] == [
        "Data Governance Policy", "Purpose and Scope", "Retention and Deletion"]
    assert all(s["page"] == 1 for s in secs)


def test_metadata_lines_are_not_headings():
    secs = pdf_sections([PAGE1])
    assert "Status" not in " ".join(s["heading_path"] for s in secs)


def test_section_continuing_on_next_page_keeps_its_heading():
    secs = pdf_sections([PAGE1, PAGE2])
    cont = [s for s in secs if s["page"] == 2]
    assert [s["heading_path"] for s in cont] == ["Retention and Deletion", "Quality Reviews"]


def test_pdf_without_headings_falls_back_to_pages():
    flat = "this is just prose with no real headings at all.\nit goes on and on."
    secs = pdf_sections([flat, flat])
    assert [s["heading_path"] for s in secs] == ["page 1", "page 2"]


def test_single_odd_line_is_not_enough_to_split():
    one = "Intro text here.\nSummary\nSome more body text follows on this line."
    assert pdf_sections([one])[0]["heading_path"] == "page 1"


def test_long_block_is_cut_only_at_sentence_ends():
    sents = [f"Sentence number {i} says something about topic {i}." for i in range(60)]
    chunks = chunk_structure([{"heading_path": "A", "page": 1, "text": " ".join(sents)}],
                             max_words=50, overlap=10)
    assert len(chunks) > 3
    for c in chunks:
        assert c["text"].endswith(".") and c["text"].startswith("Sentence")
        assert len(c["text"].split()) <= 50


def test_sentence_chunks_overlap_by_whole_sentences():
    sents = [f"Sentence number {i} says something here." for i in range(30)]
    chunks = chunk_structure([{"heading_path": "A", "page": 1, "text": " ".join(sents)}],
                             max_words=30, overlap=12)
    a, b = chunks[0]["text"], chunks[1]["text"]
    last_sentence_of_a = a.split(". ")[-1]
    assert last_sentence_of_a.rstrip(".") in b
