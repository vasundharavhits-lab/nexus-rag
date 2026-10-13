"""Settings for large files, OCR and background jobs. All come from the environment (.env),
nothing here is fixed in code. Kept apart from config.py on purpose."""
import os

# --- Large files -----------------------------------------------------------------------
# Uploads are streamed to disk, so the limit is about disk space and patience, not memory.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "300"))

# --- OCR for scanned PDFs (needs the Tesseract program, see docs/LARGE_FILES_AND_OCR.md) ---
OCR_ENABLED = os.getenv("OCR_ENABLED", "1") != "0"
OCR_LANGS = os.getenv("OCR_LANGS", "eng")          # Tesseract codes joined by +, e.g. eng+hin+san
OCR_SCALE = float(os.getenv("OCR_SCALE", "2.0"))   # page render scale; 2.0 is about 150 dpi
OCR_MIN_CONF = int(os.getenv("OCR_MIN_CONF", "55")) # drop words Tesseract is less sure of (0-100)
OCR_WORKERS = int(os.getenv("OCR_WORKERS", "0"))   # 0 = choose from the number of CPU cores
OCR_PAGE_TIMEOUT_S = int(os.getenv("OCR_PAGE_TIMEOUT_S", "180"))
OCR_MIN_PAGE_CHARS = 20                            # a page with less text than this is "scanned"
OCR_SCANNED_FRACTION = float(os.getenv("OCR_SCANNED_FRACTION", "0.5"))  # share of such pages
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")     # full path to tesseract(.exe) if not on PATH
JOB_WORKERS = int(os.getenv("JOB_WORKERS", "1"))   # background jobs running at once
INDEX_GROUP = 64                                   # passages embedded between progress updates
WARMUP_MODELS = os.getenv("WARMUP_MODELS", "1") != "0"   # load search + claim-check models at start-up
