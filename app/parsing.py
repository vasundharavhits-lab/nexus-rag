# app/parsing.py
import re
from docx import Document as DocxDocument
from pypdf import PdfReader

def parse_markdown_text(text: str) -> list[dict]:
    """Split text into sections; track heading hierarchy as 'A > B'."""
    sections, stack, buf = [], [], []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            path = " > ".join(h for _, h in stack) or "(root)"
            sections.append({"heading_path": path, "page": None, "text": body})
        buf.clear()

    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            flush()
            level = len(m.group(1))
            stack[:] = [(l, h) for l, h in stack if l < level]  # drop same/deeper headings
            stack.append((level, m.group(2).strip()))
        else:
            buf.append(line)
    flush()
    return sections

def docx_to_markdown(path) -> str:
    doc = DocxDocument(str(path))
    lines = []
    for p in doc.paragraphs:
        style = p.style.name
        if style.startswith("Heading "):
            lines.append("#" * int(style.split()[-1]) + " " + p.text)
        elif style == "Title":
            lines.append("# " + p.text)
        else:
            lines.append(p.text)
    return "\n".join(lines)

def parse_pdf(path) -> tuple[list[dict], int]:
    reader = PdfReader(str(path))       # raises on corrupted files; caller handles it
    sections = []
    for i, page in enumerate(reader.pages, start=1):
        t = (page.extract_text() or "").strip()
        if t:
            sections.append({"heading_path": f"page {i}", "page": i, "text": t})
    return sections, len(reader.pages)