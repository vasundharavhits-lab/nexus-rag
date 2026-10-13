# app/ocr.py
"""OCR for scanned PDFs (pages that are pictures with no text layer).

Engine: Tesseract, because it reads 100+ languages (Hindi, Sanskrit, Arabic, ...). Pages are
rendered with pypdfium2, read in parallel, filtered by word confidence (so page borders and
show-through from the other side of the paper do not pollute search), and checkpointed to disk
so an interrupted run resumes instead of starting again.

Settings (.env): OCR_ENABLED, OCR_LANGS, OCR_SCALE, OCR_MIN_CONF, OCR_WORKERS,
OCR_PAGE_TIMEOUT_S, TESSERACT_CMD.
"""
import json, os, shutil, threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from app import limits as config

os.environ.setdefault("OMP_THREAD_LIMIT", "1")      # one thread per Tesseract process; we parallelise pages
MAX_SIDE_PX = 3200                                   # shrink absurdly large renders


class OCRUnavailable(Exception):
    pass


def _find_tesseract():
    if config.TESSERACT_CMD and Path(config.TESSERACT_CMD).exists():
        return config.TESSERACT_CMD
    found = shutil.which("tesseract")
    if found:
        return found
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if Path(p).exists():
            return p
    return None


def _requested_langs():
    return [x for x in config.OCR_LANGS.replace(",", "+").split("+") if x.strip()]


def status():
    """Can OCR run right now? Never raises; says what is missing so the UI can tell the user."""
    out = {"enabled": config.OCR_ENABLED, "available": False, "engine": "tesseract",
           "langs": "+".join(_requested_langs()), "missing_langs": [], "reason": None}
    if not config.OCR_ENABLED:
        out["reason"] = "OCR is turned off (OCR_ENABLED=0)."
        return out
    try:
        import pytesseract, pypdfium2, PIL          # noqa: F401
    except ImportError as e:
        out["reason"] = f"Python package missing ({e.name}). Run: pip install pytesseract pypdfium2 pillow"
        return out
    exe = _find_tesseract()
    if not exe:
        out["reason"] = ("The Tesseract program was not found. Install it, or set TESSERACT_CMD "
                         "to its full path.")
        return out
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = exe
        installed = set(pytesseract.get_languages(config=""))
    except Exception as e:
        out["reason"] = f"Tesseract could not be started ({type(e).__name__})."
        return out
    out["missing_langs"] = [l for l in _requested_langs() if l not in installed]
    if out["missing_langs"]:
        out["reason"] = ("Tesseract language data missing: " + ", ".join(out["missing_langs"]) +
                         ". Install it or change OCR_LANGS.")
        return out
    out["available"] = True
    return out


def workers():
    if config.OCR_WORKERS > 0:
        return config.OCR_WORKERS
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def _read_image(img):
    """Text of one page image, keeping only words Tesseract is reasonably sure about."""
    import pytesseract
    from pytesseract import Output
    d = pytesseract.image_to_data(img, lang="+".join(_requested_langs()), config="--psm 3",
                                  output_type=Output.DICT, timeout=config.OCR_PAGE_TIMEOUT_S)
    lines, order = {}, []
    for i, w in enumerate(d["text"]):
        w = w.strip()
        if not w:
            continue
        try:
            conf = float(d["conf"][i])
        except (TypeError, ValueError):
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append((w, conf))
    out = []
    for k in order:
        words = [w for w, c in lines[k] if c >= config.OCR_MIN_CONF]
        if len(words) >= 2 or (words and len(words[0]) >= 4):     # drop specks and stray marks
            out.append(" ".join(words))
    return "\n".join(out)


def _checkpoint_path(pdf_path):
    return Path(str(pdf_path) + ".ocr.json")


def _settings_key():
    return {"langs": config.OCR_LANGS, "scale": config.OCR_SCALE, "conf": config.OCR_MIN_CONF}


def _load_checkpoint(pdf_path):
    p = _checkpoint_path(pdf_path)
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        if j.get("settings") == _settings_key():
            return {int(k): v for k, v in j["pages"].items()}
    except Exception:
        pass
    return {}


def _save_checkpoint(pdf_path, pages):
    p = _checkpoint_path(pdf_path)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"settings": _settings_key(),
                               "pages": {str(k): v for k, v in pages.items()}},
                              ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def ocr_pages(pdf_path, page_indexes, progress=None, should_stop=None):
    """OCR the given 0-based pages of a PDF. Returns {page_index: text}.

    progress(done, total) is called after each page. Finished pages are checkpointed every few
    pages, so calling this again after a crash continues where it stopped.
    """
    st = status()
    if not st["available"]:
        raise OCRUnavailable(st["reason"])
    import pytesseract, pypdfium2 as pdfium
    pytesseract.pytesseract.tesseract_cmd = _find_tesseract()

    result = _load_checkpoint(pdf_path)
    todo = [i for i in page_indexes if i not in result]
    total, done = len(page_indexes), len(page_indexes) - len(todo)
    if progress:
        progress(done, total)
    if not todo:
        return {i: result[i] for i in page_indexes}

    pdf = pdfium.PdfDocument(str(pdf_path))
    lock = threading.Lock()
    since_save = 0

    def work(i, img):
        try:
            return i, _read_image(img)
        except Exception:                      # one bad page must not lose the other 400
            return i, ""

    with ThreadPoolExecutor(max_workers=workers()) as pool:
        pending = set()

        def collect(finished):
            nonlocal done, since_save
            for f in finished:
                i, text = f.result()
                with lock:
                    result[i] = text
                    done += 1
                    since_save += 1
                if progress:
                    progress(done, total)
            if since_save >= 10:
                _save_checkpoint(pdf_path, result)
                since_save = 0

        for i in todo:
            if should_stop and should_stop():
                break
            img = pdf[i].render(scale=config.OCR_SCALE, grayscale=True).to_pil()
            if max(img.size) > MAX_SIDE_PX:
                img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
            pending.add(pool.submit(work, i, img))
            if len(pending) >= workers() * 2:        # keep memory bounded: few images in flight
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                collect(finished)
        while pending:
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            collect(finished)
    _save_checkpoint(pdf_path, result)
    return {i: result.get(i, "") for i in page_indexes}


def clear_checkpoint(pdf_path):
    try:
        _checkpoint_path(pdf_path).unlink()
    except FileNotFoundError:
        pass
