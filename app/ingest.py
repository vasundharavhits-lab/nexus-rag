import hashlib, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from langdetect import detect, DetectorFactory
from app.config import SUPPORTED, IMAGE_TYPES, ACCEPT_ANY_FILE
from app.ocr import OCRUnavailable
from app.parsing import (parse_markdown_text, docx_to_markdown, parse_pdf_ex, parse_csv,
                         parse_image, read_text_file, parse_xlsx, parse_pptx, parse_html, parse_json,
                         parse_xml, parse_rtf, parse_odt, parse_epub, parse_eml, sniff_type, TEXT_LIKE)

DetectorFactory.seed = 0
NS = uuid.UUID("12345678-1234-5678-1234-567812345678")

_KEYS = ("Status", "Date", "Author")
_KEY_SPLIT = re.compile(r"\s+(?=(?:Status|Date|Author):)", re.I)

def _header_lines(text: str):
    """Yield lines with Markdown noise removed so that '- **Status:** Approved'
    reads like 'Status: Approved', and 'Status: A Date: B' (PDF text extraction
    often joins header lines) is split back into one key per line."""
    for ln in text.splitlines():
        ln = re.sub(r"^[\s>\-*+]+", "", ln.replace("*", "").replace("`", ""))
        if re.match(r"(?:Status|Date|Author):", ln, re.I):
            yield from _KEY_SPLIT.split(ln)
        else:
            yield ln

def extract_metadata(text: str) -> dict:
    scan = "\n".join(_header_lines(text))
    meta = {}
    for key in _KEYS:
        m = re.search(rf"^{key}:\s*(.+)$", scan, re.I | re.M)
        meta[key.lower()] = m.group(1).strip() if m else None
    return meta

def detect_lang(text: str) -> str:
    """Main language of a document. Three samples (start, middle, end) vote, so a book whose first pages
    are an English preface but whose body is Hindi (or the reverse) is labelled by what most of it is."""
    t = text or ""
    if len(t.split()) < 5 and len(t) < 40:
        return "unknown"
    n, votes = len(t), {}
    spots = [t[:4000]] if n <= 12000 else [t[:4000], t[n // 2 - 2000:n // 2 + 2000], t[-4000:]]
    for s in spots:
        try:
            lang = detect(s)
        except Exception:
            continue
        votes[lang] = votes.get(lang, 0) + 1
    return max(votes, key=votes.get) if votes else "unknown"

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:                       # 1 MB at a time: any file size is fine
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def ingest_file(path: Path, workspace_id: str = "default", original_name: str | None = None,
                progress=None):
    """progress(stage, done, total) is optional; it is how long scans report OCR progress."""
    name = original_name or path.name
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    m = re.search(r"_v(\d+)$", stem)
    logical = re.sub(r"_v\d+$", "", stem)
    label = f"v{m.group(1)}" if m else "v1"
    chash = _sha256_file(path)

    rec = {
        "document_id": str(uuid.uuid5(NS, f"{workspace_id}:{logical}")),
        "version_id": str(uuid.uuid5(NS, f"{workspace_id}:{logical}:{chash}")),
        "logical_name": logical, "label": label, "filename": name,
        "source_uri": str(path), "file_type": ext.lstrip("."),
        "size_bytes": path.stat().st_size, "content_hash": chash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok", "error": None, "page_count": None,
    }
    sections, text, ocr_info = [], "", None
    try:
        kind = ext
        if ext not in SUPPORTED:                      # wrong or missing extension: trust the content
            kind = sniff_type(path) or ext
        if kind in TEXT_LIKE:
            sections = parse_markdown_text(read_text_file(path))
        elif kind in (".csv", ".tsv"):
            sections = parse_csv(path)
        elif kind in IMAGE_TYPES:
            sections = parse_image(path)
            ocr_info = {"ocr_pages": 1 if sections else 0, "ocr_error": None}
        elif kind == ".docx":
            sections = parse_markdown_text(docx_to_markdown(path))
        elif kind in (".xlsx", ".xlsm"):
            sections = parse_xlsx(path)
        elif kind == ".pptx":
            sections = parse_pptx(path)
        elif kind in (".html", ".htm"):
            sections = parse_html(path)
        elif kind in (".json", ".jsonl"):
            sections = parse_json(path)
        elif kind == ".xml":
            sections = parse_xml(path)
        elif kind == ".rtf":
            sections = parse_rtf(path)
        elif kind in (".odt", ".odp", ".ods"):
            sections = parse_odt(path)
        elif kind == ".epub":
            sections = parse_epub(path)
        elif kind == ".eml":
            sections = parse_eml(path)
        elif kind == ".pdf":
            sections, rec["page_count"], info = parse_pdf_ex(path, progress)
            ocr_info = info
        else:
            raise ValueError(f"Unsupported file type '{ext or 'unknown'}'")
        text = "\n\n".join(s["text"] for s in sections)
        if not text.strip():
            rec["status"] = "empty"
            if ocr_info and ocr_info["ocr_error"]:
                rec["error"] = "Scanned PDF and OCR is not available: " + ocr_info["ocr_error"]
            elif ocr_info and ocr_info["ocr_pages"]:
                rec["error"] = "OCR ran but found no readable text."
    except OCRUnavailable as e:                     # OCR needed but not available
        rec["status"], rec["error"] = "empty", f"OCR is not available: {e}"
    except Exception as e:
        rec["status"], rec["error"] = "failed", f"{type(e).__name__}: {e}"

    meta = extract_metadata(text)
    rec.update({
        "doc_status": meta["status"], "effective_at": meta["date"],
        "author": meta["author"], "text": text,
        "language": detect_lang(text), "section_count": len(sections),
    })
    rec["ocr_pages"] = ocr_info["ocr_pages"] if ocr_info else 0      # not stored in the DB
    return rec, sections

def ingest_directory(raw_dir: Path, workspace_id: str = "default"):
    records, all_sections, unsupported = [], [], []
    for p in sorted(raw_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED and not (ACCEPT_ANY_FILE and sniff_type(p)):
            unsupported.append(p.name)
            continue
        rec, secs = ingest_file(p, workspace_id)
        records.append(rec)
        all_sections += [{**s, "version_id": rec["version_id"], "idx": i}
                         for i, s in enumerate(secs)]
    return records, all_sections, unsupported