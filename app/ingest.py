import hashlib, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from langdetect import detect, DetectorFactory
from app import ocr
from app.config import SUPPORTED
from app.limits import OCR_MIN_PAGE_CHARS, OCR_SCANNED_FRACTION
from app.parsing import (parse_markdown_text, docx_to_markdown, parse_pdf, pdf_page_texts,
                         pdf_sections)

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
    try:
        words = text.split()
        return detect(" ".join(words[:3000])) if len(words) >= 5 else "unknown"   # a sample is enough
    except Exception:
        return "unknown"

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):          # never hold a large file in memory
            h.update(chunk)
    return h.hexdigest()


def finish_pdf(rec, texts):
    """Build sections, text and metadata for a PDF from its page texts (also used after OCR)."""
    sections = pdf_sections(texts)
    text = "\n\n".join(s["text"] for s in sections)
    meta = extract_metadata(text)
    rec.update({"status": "ok" if text.strip() else "empty",
                "error": None if text.strip() else "No readable text was found, even after OCR.",
                "doc_status": meta["status"], "effective_at": meta["date"], "author": meta["author"],
                "text": text, "language": detect_lang(text), "section_count": len(sections)})
    return rec, sections


def ingest_file(path: Path, workspace_id: str = "default", original_name: str | None = None,
                defer_ocr: bool = False):
    """Parse one file. A scanned PDF (no text layer) is read with OCR: immediately, or with
    defer_ocr=True the record comes back as status 'processing' with rec['_ocr'] describing the
    work, so the caller can run it as a background job."""
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
    sections, text = [], ""
    try:
        if ext == ".md":
            sections = parse_markdown_text(path.read_text(encoding="utf-8", errors="replace"))
        elif ext == ".docx":
            sections = parse_markdown_text(docx_to_markdown(path))
        elif ext == ".pdf":
            texts = pdf_page_texts(path)
            rec["page_count"] = len(texts)
            blank = [i for i, t in enumerate(texts) if len(t.strip()) < OCR_MIN_PAGE_CHARS]
            if texts and len(blank) / len(texts) >= OCR_SCANNED_FRACTION:
                st = ocr.status()
                if not st["available"]:
                    rec["error"] = "This PDF is scanned (no text layer). " + (st["reason"] or "")
                elif defer_ocr:
                    rec["status"], rec["_ocr"] = "processing", {"texts": texts, "pages": blank}
                else:
                    pages = ocr.ocr_pages(path, blank)
                    for i in blank:
                        texts[i] = pages.get(i, "")
            if rec["status"] != "processing":
                sections = pdf_sections(texts)
        if rec["status"] != "processing":
            text = "\n\n".join(s["text"] for s in sections)
            if not text.strip():
                rec["status"] = "empty"
    except Exception as e:
        rec["status"], rec["error"] = "failed", f"{type(e).__name__}: {e}"

    meta = extract_metadata(text)
    rec.update({
        "doc_status": meta["status"], "effective_at": meta["date"],
        "author": meta["author"], "text": text,
        "language": detect_lang(text), "section_count": len(sections),
    })
    return rec, sections

def ingest_directory(raw_dir: Path, workspace_id: str = "default"):
    records, all_sections, unsupported = [], [], []
    for p in sorted(raw_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED:
            unsupported.append(p.name)
            continue
        rec, secs = ingest_file(p, workspace_id)
        records.append(rec)
        all_sections += [{**s, "version_id": rec["version_id"], "idx": i}
                         for i, s in enumerate(secs)]
    return records, all_sections, unsupported