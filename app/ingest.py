# app/ingest.py
import hashlib, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from langdetect import detect, DetectorFactory
from app.config import SUPPORTED
from app.parsing import parse_markdown_text, docx_to_markdown, parse_pdf

DetectorFactory.seed = 0        # reproducible language detection
NS = uuid.UUID("12345678-1234-5678-1234-567812345678")

def extract_metadata(text: str) -> dict:
    meta = {}
    for key in ("Status", "Date", "Author"):
        m = re.search(rf"^{key}:\s*(.+)$", text, re.I | re.M)
        meta[key.lower()] = m.group(1).strip() if m else None
    return meta

def detect_lang(text: str) -> str:
    try:
        return detect(text) if len(text.split()) >= 5 else "unknown"
    except Exception:
        return "unknown"

def ingest_file(path: Path):
    raw = path.read_bytes()
    stem, ext = path.stem, path.suffix.lower()
    m = re.search(r"_v(\d+)$", stem)
    logical = re.sub(r"_v\d+$", "", stem)
    label = f"v{m.group(1)}" if m else "v1"
    chash = hashlib.sha256(raw).hexdigest()

    rec = {
        "document_id": str(uuid.uuid5(NS, logical)),
        "version_id": str(uuid.uuid5(NS, logical + chash)),
        "logical_name": logical, "label": label, "filename": path.name,
        "source_uri": str(path), "file_type": ext.lstrip("."),
        "size_bytes": len(raw), "content_hash": chash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok", "error": None, "page_count": None,
    }
    sections, text = [], ""
    try:
        if ext == ".md":
            sections = parse_markdown_text(raw.decode("utf-8", errors="replace"))
        elif ext == ".docx":
            sections = parse_markdown_text(docx_to_markdown(path))
        elif ext == ".pdf":
            sections, rec["page_count"] = parse_pdf(path)
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

def ingest_directory(raw_dir: Path):
    records, all_sections, unsupported = [], [], []
    for p in sorted(raw_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED:
            unsupported.append(p.name)
            continue
        rec, secs = ingest_file(p)
        records.append(rec)
        all_sections += [{**s, "version_id": rec["version_id"], "idx": i}
                         for i, s in enumerate(secs)]
    return records, all_sections, unsupported