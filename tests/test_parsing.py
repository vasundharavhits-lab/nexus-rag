# tests/test_parsing.py
from app.parsing import parse_markdown_text

def test_heading_path_is_hierarchical():
    text = "# A\n## B\nbody\n## C\nother"
    paths = [s["heading_path"] for s in parse_markdown_text(text)]
    assert paths == ["A > B", "A > C"]

def test_text_without_headings_goes_to_root():
    secs = parse_markdown_text("just some text")
    assert secs[0]["heading_path"] == "(root)"