# app/config.py
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "db" / "nexus.db"
REPORT_DIR = ROOT / "reports"

SUPPORTED = {".md", ".docx", ".pdf"}
NEAR_DUP_THRESHOLD = 0.6    # starting guess; tune by inspecting pairs
MIN_WORDS = 30              # below this a document is "very short"

def ensure_dirs():
    for d in (RAW_DIR, DB_PATH.parent, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)