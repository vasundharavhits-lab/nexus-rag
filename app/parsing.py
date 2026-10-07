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

HEADING_MAX_WORDS = 8
MIN_PDF_HEADINGS = 2    # fewer than this and the document is treated as having no headings

def _is_pdf_heading(line, prev):
    """A heading is a short capitalised line without end punctuation that follows a finished
    sentence (or starts the document). Metadata lines ('Status: ...', dates) never qualify."""
    words = line.split()
    if not (1 <= len(words) <= HEADING_MAX_WORDS):
        return False
    if line[-1] in ".,;:!?" or ":" in line or re.search(r"\d{4}-\d{2}-\d{2}", line):
        return False
    if not line[0].isupper():
        return False
    if prev is None or prev[-1] in ".!?":
        return True
    return bool(re.match(r"(?:status|date|author)\s*:", prev, re.I))   # header block above it

def pdf_sections(page_texts):
    """page_texts: [text of page 1, page 2, ...] -> sections named after the headings found,
    each carrying its page. A section that continues onto the next page keeps its heading.
    Falls back to one 'page N' section per page when the PDF has no usable headings."""
    pages = [[ln.strip() for ln in (t or "").splitlines() if ln.strip()] for t in page_texts]
    flagged, n_headings, prev = [], 0, None
    for lines in pages:
        row = []
        for ln in lines:
            h = _is_pdf_heading(ln, prev)
            n_headings += h
            row.append((ln, h))
            prev = ln
        flagged.append(row)
    sections = []
    if n_headings < MIN_PDF_HEADINGS:
        for i, lines in enumerate(pages, start=1):
            if lines:
                sections.append({"heading_path": f"page {i}", "page": i, "text": "\n".join(lines)})
        return sections
    current = None
    for i, row in enumerate(flagged, start=1):
        path, buf = current or f"page {i}", []
        def flush():
            if buf:
                sections.append({"heading_path": path, "page": i, "text": "\n".join(buf)})
        for ln, is_h in row:
            if is_h:
                flush(); buf = []
                path = current = ln
            else:
                buf.append(ln)
        flush()
    return sections

def parse_pdf(path) -> tuple[list[dict], int]:
    reader = PdfReader(str(path))       # raises on corrupted files; caller handles it
    texts = [(page.extract_text() or "").strip() for page in reader.pages]
    return pdf_sections(texts), len(reader.pages)