from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

RAW_DIR = ROOT / "data" / "raw"
UPLOAD_DIR = ROOT / "data" / "uploads"
DB_PATH = ROOT / "db" / "nexus.db"          # old Week 1 SQLite file, no longer used
REPORT_DIR = ROOT / "reports"

DATABASE_URL = os.getenv("DATABASE_URL", "")
MAX_UPLOAD_MB = 20

SUPPORTED = {".md", ".docx", ".pdf"}
NEAR_DUP_THRESHOLD = 0.6
MIN_WORDS = 30

def ensure_dirs():
    for d in (RAW_DIR, UPLOAD_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)