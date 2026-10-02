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

CHUNK_MAX_WORDS = 180       # words, used as a rough proxy for tokens
CHUNK_OVERLAP_WORDS = 30    # overlap when a single paragraph must be split
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")
LLM_TIMEOUT_S = 300
LLM_MAX_TOKENS = 250
MIN_VECTOR_SCORE = 0.60
def ensure_dirs():
    for d in (RAW_DIR, UPLOAD_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)