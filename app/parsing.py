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

def _table_lines(table):
    """A Word table as sentences, one per row: 'Plan: Team; Price: $40; Users: 10.' The header row
    names every value, so a question about one row finds it. Merged cells are not repeated."""
    rows = []
    for row in table.rows:
        cells, last = [], None
        for c in row.cells:
            t = " ".join(c.text.split())
            if c._tc is not last:
                cells.append(t)
            last = c._tc
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        return ["; ".join(c for c in r if c) + "." for r in rows]
    head = [h or f"column {i + 1}" for i, h in enumerate(rows[0])]
    return ["; ".join(f"{h}: {v}" for h, v in zip(head, r) if v) + "." for r in rows[1:]]

def docx_to_markdown(path) -> str:
    """Paragraphs AND tables, in the order they appear in the document."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = DocxDocument(str(path))
    lines = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            style = p.style.name if p.style is not None else ""
            if style.startswith("Heading ") and style.split()[-1].isdigit():
                lines.append("#" * int(style.split()[-1]) + " " + p.text)
            elif style == "Title":
                lines.append("# " + p.text)
            else:
                lines.append(p.text)
        elif tag == "tbl":
            lines.append("")
            for ln in _table_lines(Table(child, doc)):
                lines += [ln, ""]
    return "\n".join(lines)

def decode_bytes(raw: bytes) -> str:
    """Text in whatever encoding it was saved in: BOMs, UTF-8, UTF-16, then automatic detection
    (Hindi, Arabic, Chinese, Cyrillic... legacy encodings), and finally cp1252."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None:
            return str(best)
    except Exception:
        pass
    for enc in ("utf-16", "cp1252"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")

def read_text_file(path) -> str:
    with open(path, "rb") as f:
        return decode_bytes(f.read())

CSV_ROWS_PER_SECTION = 25

def parse_csv(path) -> list[dict]:
    """A table as sentences ('Region: North; Q1: 120') in groups of rows, so a question about one
    row finds it and the header names travel with every value."""
    import csv, io
    text = read_text_file(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not rows:
        return []
    head, body = [h.strip() or f"column {i + 1}" for i, h in enumerate(rows[0])], rows[1:]
    sections = []
    for start in range(0, len(body), CSV_ROWS_PER_SECTION):
        part = body[start:start + CSV_ROWS_PER_SECTION]
        lines = ["; ".join(f"{h}: {v.strip()}" for h, v in zip(head, r) if v.strip()) + "."
                 for r in part]
        sections.append({"heading_path": f"rows {start + 1}-{start + len(part)}", "page": None,
                         "text": "\n\n".join(lines)})
    return sections

def parse_image(path) -> list[dict]:
    """A photo or scan of a page: OCR it. Raises RuntimeError (with the reason) if OCR is unavailable."""
    from app import ocr
    text = ocr.ocr_image(path)
    return [{"heading_path": "page 1", "page": 1, "text": text}] if text.strip() else []

def looks_garbled(text):
    """True when a PDF page has a text layer that is not real text (missing font map: '(cid:12)',
    replacement characters, private-use symbols). Such pages are read with OCR instead."""
    t = text or ""
    if not t:
        return False
    bad = t.count("\ufffd") + t.count("(cid:") * 6 + sum(0xE000 <= ord(c) <= 0xF8FF for c in t)
    return bad / max(1, len(t)) > 0.08

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

def pdf_sections(page_texts, force_pages=False):
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
    if force_pages or n_headings < MIN_PDF_HEADINGS:     # OCR text: headings are unreliable
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

def parse_pdf_ex(path, progress=None):
    """Reads a PDF of any size. Pages that have a text layer are read directly; pages without one
    (scans) are OCR'd when OCR is available. Returns (sections, page_count, info) where info is
    {'ocr_pages': n, 'ocr_error': str|None}.  progress(stage, done, total) reports the work."""
    from app.config import OCR_MIN_CHARS
    reader = PdfReader(str(path))       # raises on corrupted files; caller handles it
    n = len(reader.pages)
    texts, need_ocr = [], []
    for i, page in enumerate(reader.pages, start=1):
        t = (page.extract_text() or "").strip()
        texts.append(t)
        if len(t) < OCR_MIN_CHARS or looks_garbled(t):
            need_ocr.append(i)
        if progress and (i % 25 == 0 or i == n):
            progress("reading", i, n)
    info = {"ocr_pages": 0, "ocr_error": None}
    if need_ocr:
        from app import ocr
        try:
            done = ocr.ocr_pages(path, need_ocr,
                                 (lambda d, t: progress("ocr", d, t)) if progress else None)
            for p, txt in done.items():
                texts[p - 1] = txt
            info["ocr_pages"] = len(need_ocr)
        except Exception as e:           # OCR missing or failed: keep what has a text layer
            info["ocr_error"] = str(e) if isinstance(e, ocr.OCRUnavailable) else f"{type(e).__name__}: {e}"
    return pdf_sections(texts, force_pages=info["ocr_pages"] > 0), n, info

def parse_pdf(path) -> tuple[list[dict], int]:
    sections, n, _ = parse_pdf_ex(path)
    return sections, n


# =====================================================================================
# More file types. Each reader returns sections [{heading_path, page, text}] and needs no
# extra package unless it says so (the message tells the user what to pip install).
# =====================================================================================
from html.parser import HTMLParser

TEXT_LIKE = {".md", ".txt", ".text", ".log", ".rst", ".tex", ".yaml", ".yml", ".ini", ".cfg", ".toml",
             ".srt", ".vtt", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rb",
             ".php", ".sql", ".sh", ".bat", ".ps1", ".css", ".kt", ".swift", ".r"}


def _group_rows(sheet_name, head, body, per=CSV_ROWS_PER_SECTION):
    out = []
    for start in range(0, len(body), per):
        part = body[start:start + per]
        lines = ["; ".join(f"{h}: {v}" for h, v in zip(head, r) if v) + "." for r in part]
        lines = [ln for ln in lines if len(ln) > 1]
        if lines:
            out.append({"heading_path": f"{sheet_name} > rows {start + 1}-{start + len(part)}",
                        "page": None, "text": "\n\n".join(lines)})
    return out


def parse_xlsx(path):
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("Reading Excel files needs a package. Run: pip install openpyxl")
    wb = openpyxl.load_workbook(open(path, "rb"), read_only=True, data_only=True)   # file object: works whatever the extension
    sections = []
    try:
        for ws in wb.worksheets:
            rows = []
            for r in ws.iter_rows(values_only=True):
                cells = ["" if c is None else str(c).strip() for c in r]
                if any(cells):
                    rows.append(cells)
            if not rows:
                continue
            head = [h or f"column {i + 1}" for i, h in enumerate(rows[0])]
            sections += _group_rows(ws.title, head, rows[1:]) if len(rows) > 1 else \
                [{"heading_path": ws.title, "page": None, "text": "; ".join(c for c in rows[0] if c)}]
    finally:
        wb.close()
    return sections


def parse_pptx(path):
    try:
        from pptx import Presentation
    except ImportError:
        raise RuntimeError("Reading PowerPoint files needs a package. Run: pip install python-pptx")
    prs, sections = Presentation(str(path)), []
    for i, slide in enumerate(prs.slides, start=1):
        title, parts = None, []
        t_shape = slide.shapes.title
        for shp in slide.shapes:
            if getattr(shp, "has_text_frame", False) and shp.text_frame.text.strip():
                if title is None and t_shape is not None and shp.shape_id == t_shape.shape_id:
                    title = shp.text_frame.text.strip()
                else:
                    parts.append(shp.text_frame.text.strip())
            if getattr(shp, "has_table", False) and shp.has_table:
                rows = [[c.text.strip() for c in r.cells] for r in shp.table.rows]
                if len(rows) > 1:
                    head = [h or f"column {k + 1}" for k, h in enumerate(rows[0])]
                    parts += ["; ".join(f"{h}: {v}" for h, v in zip(head, r) if v) + "." for r in rows[1:]]
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            n = slide.notes_slide.notes_text_frame.text.strip()
            if n:
                parts.append("Notes: " + n)
        if parts or title:
            sections.append({"heading_path": f"slide {i}" + (f" > {title}" if title else ""),
                             "page": i, "text": "\n\n".join(parts) or title})
    return sections


class _HTMLText(HTMLParser):
    SKIP = {"script", "style", "noscript", "head", "svg", "template"}
    BLOCK = {"p", "div", "br", "li", "tr", "section", "article", "table", "ul", "ol", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur, self.skip, self.h = [], [], 0, None

    def _flush(self):
        t = " ".join("".join(self.cur).split())
        self.cur = []
        if t:
            self.lines.append(t)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush(); self.h = int(tag[1])
        elif tag in self.BLOCK:
            self._flush()
        elif tag in ("td", "th"):
            self.cur.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif re.fullmatch(r"h[1-6]", tag):
            t = " ".join("".join(self.cur).split()); self.cur = []
            if t:
                self.lines.append("#" * (self.h or 2) + " " + t)
            self.h = None
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.cur.append(data)


def html_to_markdown(html):
    p = _HTMLText()
    p.feed(html)
    p._flush()
    return "\n\n".join(p.lines)


def parse_html(path):
    return parse_markdown_text(html_to_markdown(read_text_file(path)))


def _flatten_json(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten_json(v, f"{prefix}{k}." if isinstance(v, (dict, list)) else f"{prefix}{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten_json(v, f"{prefix}{i + 1}." if isinstance(v, (dict, list)) else f"{prefix}{i + 1}")
    else:
        yield prefix.rstrip("."), obj


def parse_json(path):
    import json
    text = read_text_file(path)
    try:
        data = json.loads(text)
    except ValueError:                                   # JSON Lines: one object per line
        data = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    items = data if isinstance(data, list) else [data]
    sections, group = [], []
    for i, it in enumerate(items, start=1):
        if isinstance(it, dict):
            group.append("; ".join(f"{k}: {v}" for k, v in _flatten_json(it) if v not in (None, "")) + ".")
        else:
            group.append("; ".join(f"{k}: {v}" for k, v in _flatten_json(it) if v not in (None, "")) or str(it))
        if len(group) == CSV_ROWS_PER_SECTION or i == len(items):
            sections.append({"heading_path": f"items {i - len(group) + 1}-{i}", "page": None,
                             "text": "\n\n".join(group)})
            group = []
    return sections


def parse_xml(path):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(read_text_file(path).encode("utf-8"))
    lines = []
    for el in root.iter():
        t = (el.text or "").strip()
        if t:
            lines.append(f"{el.tag.rsplit('}', 1)[-1]}: {t}")
    return parse_markdown_text("\n\n".join(lines))


def rtf_to_text(rtf):
    """Small RTF reader: keeps letters (including \\'xx and \\uNNNN escapes), drops formatting."""
    rtf = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "replace"), rtf)
    rtf = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), rtf)
    rtf = re.sub(r"\\(par|line|tab)\b ?", lambda m: "\n" if m.group(1) != "tab" else "\t", rtf)
    rtf = re.sub(r"\{\\\*[^{}]*\}", "", rtf)
    rtf = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", rtf)
    return re.sub(r"[{}]", "", rtf)


def parse_rtf(path):
    return parse_markdown_text(rtf_to_text(read_text_file(path)))


def parse_odt(path):
    """OpenDocument text/slides/sheets (.odt .odp .ods): the text inside content.xml."""
    import zipfile, xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    lines = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("h", "p"):
            t = " ".join("".join(el.itertext()).split())
            if t:
                lines.append(("# " if tag == "h" else "") + t)
    return parse_markdown_text("\n\n".join(lines))


def parse_epub(path):
    import zipfile
    sections = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm")))
        for i, n in enumerate(names, start=1):
            md = html_to_markdown(decode_bytes(z.read(n)))
            secs = parse_markdown_text(md)
            for s in secs:
                s["heading_path"] = s["heading_path"] if s["heading_path"] != "(root)" else f"part {i}"
            sections += secs
    return sections


def parse_eml(path):
    import email
    from email import policy
    msg = email.message_from_binary_file(open(path, "rb"), policy=policy.default)
    head = [f"{k}: {msg[k]}" for k in ("From", "To", "Date", "Subject") if msg[k]]
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    if body and body.get_content_type() == "text/html":
        text = html_to_markdown(text)
    return [{"heading_path": str(msg["Subject"] or "email"), "page": None,
             "text": "\n".join(head) + "\n\n" + text}]


def sniff_type(path):
    """Real type of a file from its first bytes, for files with a missing or wrong extension."""
    with open(path, "rb") as f:
        head = f.read(4096)
    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"PK"):
        import zipfile
        try:
            names = zipfile.ZipFile(path).namelist()
        except Exception:
            return None
        if any(n.startswith("word/") for n in names): return ".docx"
        if any(n.startswith("xl/") for n in names): return ".xlsx"
        if any(n.startswith("ppt/") for n in names): return ".pptx"
        if "content.xml" in names and "mimetype" in names: return ".odt"
        if any(n.endswith((".xhtml", ".html")) for n in names): return ".epub"
        return None
    for magic, ext in ((b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"II*\x00", ".tif"),
                       (b"MM\x00*", ".tif"), (b"BM", ".bmp"), (b"RIFF", ".webp")):
        if head.startswith(magic):
            return ext
    if head.startswith(b"{\\rtf"):
        return ".rtf"
    if b"\x00" not in head[:2048] or head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        t = head.decode("utf-8", "ignore").lstrip().lower()
        if t.startswith(("<!doctype html", "<html")):
            return ".html"
        return ".txt"
    return None
