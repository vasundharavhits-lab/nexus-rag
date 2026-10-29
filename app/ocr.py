# app/ocr.py
"""OCR for scanned PDFs. Everything here is optional: if the OCR packages or the Tesseract
program are missing, ocr_status() says why and the caller reports it instead of crashing."""
import os, re, shutil, unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from app import config as _cfg
from app.config import (OCR_ENABLED, OCR_LANGS, OCR_DPI, OCR_WORKERS, TESSERACT_CMD,
                        OCR_CLEAN)

# Words Tesseract itself is unsure about are mostly scan debris; dropping them keeps junk out of the index in
# every language. 0 switches the filter off. Set OCR_MIN_CONF in .env (default 45).
OCR_MIN_CONF = getattr(_cfg, "OCR_MIN_CONF", 45)
os.environ.setdefault("OMP_THREAD_LIMIT", "1")      # one thread per Tesseract process: the pool already runs several

class OCRUnavailable(RuntimeError):
    """OCR was needed but cannot run (package or Tesseract missing). The message says what to install."""


_WIN_DEFAULTS = (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe")


def _find_tesseract():
    for cand in (TESSERACT_CMD, shutil.which("tesseract"), *_WIN_DEFAULTS):
        if cand and os.path.exists(cand):
            return cand
        if cand and shutil.which(cand):
            return shutil.which(cand)
    return None


@lru_cache(maxsize=1)
def ocr_status():
    """Returns {'available': bool, 'reason': str, 'langs': 'eng+hin', 'missing': [...]}."""
    if not OCR_ENABLED:
        return {"available": False, "reason": "OCR is switched off (OCR_ENABLED=0).",
                "langs": "", "missing": []}
    try:
        import pypdfium2                                  # noqa: F401
        import pytesseract
        from PIL import Image                              # noqa: F401
    except ImportError as e:
        return {"available": False, "langs": "", "missing": [],
                "reason": f"Missing Python package ({e.name}). "
                          "Run: pip install pytesseract pypdfium2 pillow"}
    exe = _find_tesseract()
    if not exe:
        return {"available": False, "langs": "", "missing": [],
                "reason": "The Tesseract program was not found. Install it, or set "
                          "TESSERACT_CMD in .env to the full path of tesseract.exe."}
    pytesseract.pytesseract.tesseract_cmd = exe
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception as e:
        return {"available": False, "langs": "", "missing": [],
                "reason": f"Tesseract could not be started: {e}"}
    wanted = [l for l in re.split(r"[+,\s]+", OCR_LANGS) if l]
    if [w.lower() for w in wanted] == ["auto"]:           # the language is detected from the pages themselves
        usable = sorted(installed - {"osd"})
        if not usable:
            return {"available": False, "langs": "", "missing": [], "installed": [],
                    "reason": "No Tesseract language data found. Install at least 'eng'."}
        return {"available": True, "reason": "", "langs": "auto", "missing": [], "installed": usable}
    use = [l for l in wanted if l in installed] or (["eng"] if "eng" in installed else [])
    missing = [l for l in wanted if l not in installed]
    if not use:
        return {"available": False, "langs": "", "missing": missing,
                "reason": "No Tesseract language data found. Install at least 'eng'."}
    return {"available": True, "reason": "", "langs": "+".join(use), "missing": missing,
            "installed": sorted(installed - {"osd"})}


# --- language of a scan ------------------------------------------------------------------
# Tesseract's own table: the script its orientation/script detector reports -> language packs that read it.
SCRIPT_PACKS = {
    "Devanagari": ("hin", "san", "mar", "nep"), "Arabic": ("ara", "fas", "urd"), "Cyrillic": ("rus", "ukr", "bul"),
    "Bengali": ("ben", "asm"), "Tamil": ("tam",), "Telugu": ("tel",), "Gujarati": ("guj",), "Gurmukhi": ("pan",),
    "Kannada": ("kan",), "Malayalam": ("mal",), "Han": ("chi_sim", "chi_tra"), "Japanese": ("jpn",),
    "Korean": ("kor",), "Hangul": ("kor",), "Greek": ("ell",), "Hebrew": ("heb",), "Thai": ("tha",),
    "Armenian": ("hye",), "Georgian": ("kat",), "Khmer": ("khm",), "Lao": ("lao",), "Myanmar": ("mya",),
    "Sinhala": ("sin",), "Tibetan": ("bod",), "Ethiopic": ("amh",),
}
LATIN_PACKS = ("fra", "deu", "spa", "ita", "por", "nld", "pol", "tur", "swe", "dan", "nor", "fin", "ces",
               "ron", "hun", "ind", "vie", "cat", "hrv", "slk", "slv", "lav", "lit", "est")


def langs_for_scripts(scripts, installed):
    """Language packs to use for the scripts found on a document's pages. English is always added (most
    documents quote English), then up to two packs per script that are really installed."""
    packs = ["eng"] if "eng" in installed else []
    for sc in scripts:
        cands = LATIN_PACKS if sc == "Latin" else SCRIPT_PACKS.get(sc, ())
        packs += [p for p in cands if p in installed and p not in packs][:2]
    if not packs:
        packs = [p for p in sorted(installed) if p != "osd"][:3]
    return "+".join(dict.fromkeys(packs))


MAX_AUTO_PACKS = 4        # with this many language packs or fewer installed, auto reads with all of them


def detect_scripts(images, top=4):
    """Scripts Tesseract reports for sample page images (most common first). [] if it cannot tell. A page that mixes
    two scripts is reported as one of them, so this is only used to choose among MANY installed packs."""
    import pytesseract
    votes = {}
    for im in images:
        try:
            m = re.search(r"Script:\s*(\w+)", pytesseract.image_to_osd(im))
        except Exception:
            continue
        if m:
            votes[m.group(1)] = votes.get(m.group(1), 0) + 1
    return sorted(votes, key=votes.get, reverse=True)[:top]


def pick_langs(images, installed):
    """Languages to read a scan with when OCR_LANGS=auto. Books and reports often mix scripts on one page
    (a Hindi text with its English translation), and a script detector reports only one of them, so when a
    few packs are installed all of them are used (English first). With many packs installed, the scripts found
    on the sample pages decide."""
    usable = sorted(p for p in installed if p != "osd")
    usable.sort(key=lambda p: p != "eng")
    if len(usable) <= MAX_AUTO_PACKS:
        return "+".join(usable)
    scripts = detect_scripts(images)
    return langs_for_scripts(scripts, installed) if scripts else "+".join(usable[:MAX_AUTO_PACKS])


# --- cleanup --------------------------------------------------------------------------
_NOISE = re.compile(r"[|©®¦\\~_^`§¶•■□▪●]+")
_STOP = frozenset("""the of and to in is are was were be been it its this that these those with for on
by as at from or not but he she they we you i his her their our your my me him them who whom which
what when where why how all any each if then than there here so no yes do does did have has had
will would shall should can could may might must o said""".split())
_NON_LATIN = {"hin", "san", "ara", "ben", "tam", "tel", "guj", "kan", "mal", "mar", "pan",
              "urd", "rus", "chi_sim", "chi_tra", "jpn", "kor", "tha", "heb", "ell"}


_SHORT_OK = frozenset("a i o of to in is it he we me be by or on at as an if no so do up us my".split())


def _is_latin_token(tok):
    letters = [c for c in tok if c.isalpha()]
    return bool(letters) and all(c.isascii() for c in letters)


def _wordchar(c):
    """Letters, digits and the combining marks that belong to a word (vowel signs of Indic scripts, accents)."""
    return c.isalnum() or unicodedata.category(c)[0] == "M"


def _trim_edges(ln):
    """Page borders and decorations leave stray 1-2 letter tokens at line ends ('...wielding f'). Only Latin
    tokens are trimmed: in other scripts a one-letter token can be a real word."""
    ln = re.sub(r"^[)}\]>@*\u00a5\u00bb]+\s*", "", ln)
    ln = re.sub(r"\s*[({\[<@*\u00a5\u00ab]+$", "", ln)
    toks = ln.split()
    while len(toks) > 3 and _is_latin_token(toks[-1]) and len(re.sub(r"\W", "", toks[-1])) <= 2 \
            and toks[-1][-1:].isalnum() and toks[-1].lower() not in _SHORT_OK:
        toks.pop()
    while len(toks) > 3 and _is_latin_token(toks[0]) and len(re.sub(r"\W", "", toks[0])) <= 2 \
            and toks[0][-1:].isalnum() and toks[0].lower() not in _SHORT_OK:
        toks.pop(0)
    return " ".join(toks)


def _english_only(langs):
    return not (set(re.split(r"[+,\s]+", langs)) & _NON_LATIN)


def clean_ocr_text(text, langs="eng"):
    """Removes scanner noise. When only English is being read, also drops the lines that are
    really Sanskrit/Hindi text mis-read as Latin letters (they contain no English words and
    would pollute the search index)."""
    if not OCR_CLEAN:
        return text.strip()
    english = _english_only(langs)
    keep = []
    for raw in text.splitlines():
        ln = _NOISE.sub(" ", raw)
        ln = re.sub(r"\s{2,}", " ", ln).strip(" \t-—–.,;:'\"")
        chars = [c for c in ln if not c.isspace()]
        wordy = sum(_wordchar(c) for c in chars)
        if wordy < 3 or wordy / max(1, len(chars)) < 0.6:
            continue
        toks = re.findall(r"[A-Za-z']+", ln)
        if english and len(toks) >= 4:
            hits = sum(t.lower() in _STOP for t in toks)
            if hits == 0 or hits / len(toks) < 0.12:
                continue
            short = sum(len(t) <= 2 for t in toks) / len(toks)
            if short > 0.5 and hits / len(toks) < 0.4:      # "aA el uals ca eal iN"
                continue
        keep.append(_trim_edges(ln))      # trim only after the line has been judged
    return "\n".join(keep)


# --- OCR ------------------------------------------------------------------------------
def read_image(img, langs, min_conf=None):
    """Text of one page image. Words Tesseract is unsure about (confidence below `min_conf`) are dropped, and a
    line that is mostly such words is dropped whole: this removes scan debris in every script."""
    import pytesseract
    from pytesseract import Output
    min_conf = OCR_MIN_CONF if min_conf is None else min_conf
    if min_conf <= 0:
        return pytesseract.image_to_string(img, lang=langs, config="--psm 6")
    d = pytesseract.image_to_data(img, lang=langs, config="--psm 6", output_type=Output.DICT)
    lines, order = {}, []
    for i, word in enumerate(d["text"]):
        word = (word or "").strip()
        try:
            conf = float(d["conf"][i])
        except (TypeError, ValueError):
            continue
        if not word or conf < 0:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append((word, conf))
    out = []
    for key in order:
        words = lines[key]
        kept = [w for w, c in words if c >= min_conf]
        if not kept or (len(words) >= 3 and len(kept) < 0.5 * len(words)):
            continue
        out.append(" ".join(kept))
    return "\n".join(out)


def _installed():
    import pytesseract
    return set(pytesseract.get_languages(config=""))


def ocr_pages(pdf_path, page_numbers, progress=None):
    """OCR the given 1-based pages. Returns {page_number: text}. Pages are rendered one by one
    (so memory stays flat for a 1000-page scan) and read by several Tesseract processes at once.
    With OCR_LANGS=auto the language is detected from a few of the pages. progress(done, total) is called
    after each page."""
    st = ocr_status()
    if not st["available"]:
        raise OCRUnavailable(st["reason"])
    import pypdfium2 as pdfium
    import pytesseract
    total, out = len(page_numbers), {}
    workers = max(1, OCR_WORKERS)
    scale = OCR_DPI / 72.0
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        def render(p):
            page = pdf[p - 1]
            try:
                return page.render(scale=scale, grayscale=True).to_pil()
            finally:
                page.close()

        langs = st["langs"]
        if langs == "auto":
            step = max(1, total // 3)
            samples = [render(p) for p in page_numbers[::step][:3]]
            try:
                langs = pick_langs(samples, set(st["installed"]) | {"osd"} & _installed())
            finally:
                for im in samples:
                    im.close()

        def read(img):
            try:
                return read_image(img, langs)
            finally:
                img.close()

        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, total, workers * 2):               # small batches = bounded RAM
                batch = page_numbers[start:start + workers * 2]
                futures = [(p, pool.submit(read, render(p))) for p in batch]
                for p, fut in futures:
                    out[p] = clean_ocr_text(fut.result(), langs)
                    done += 1
                    if progress:
                        progress(done, total)
    finally:
        pdf.close()
    return out


def ocr_image(path):
    """OCR one image file (photo or scan of a page). Returns cleaned text."""
    st = ocr_status()
    if not st["available"]:
        raise OCRUnavailable(st["reason"])
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("L")
        if max(im.size) < 1500:                      # small photos read better when enlarged
            f = 1500 / max(im.size)
            im = im.resize((int(im.width * f), int(im.height * f)))
        langs = st["langs"]
        if langs == "auto":
            langs = pick_langs([im], set(st["installed"]) | {"osd"} & _installed())
        return clean_ocr_text(read_image(im, langs), langs)
