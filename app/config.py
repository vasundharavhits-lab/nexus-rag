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
NEAR_DUP_THRESHOLD = 0.85   # 0.6 gave 49 false alarms on data/raw2; see scripts/eval_duplicates.py
MIN_WORDS = 30

CHUNK_MAX_WORDS = 180       # words, used as a rough proxy for tokens
CHUNK_OVERLAP_WORDS = 30    # overlap when a single paragraph must be split
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# --- Language model -------------------------------------------------------------------
# LLM_PROVIDER=ollama  -> a local Ollama server (default), LLM_MODEL is any model you pulled
# LLM_PROVIDER=openai  -> ANY OpenAI-compatible API: OpenAI, Groq, OpenRouter, Together,
#                         LM Studio, vLLM ... set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")          # answers from documents (temperature 0)
CHAT_MODEL = os.getenv("CHAT_MODEL", "") or LLM_MODEL     # general chat; may be a stronger model
LLM_TIMEOUT_S = 300
LLM_MAX_TOKENS = 250          # document answers are short and cited
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "800"))
CHAT_TEMPERATURE = float(os.getenv("CHAT_TEMPERATURE", "0.7"))
# Global cap on /api/v1/chat requests per minute across ALL users (0 = off). X-User-Id is only a
# label, not a login, so this is what protects your CPU / API credits on a shared public link.
CHAT_RATE_LIMIT_PER_MIN = int(os.getenv("CHAT_RATE_LIMIT_PER_MIN", "30"))
CHAT_HISTORY_MESSAGES = 10    # most recent messages sent back to the model
CHAT_HISTORY_CHARS = 12000
MIN_VECTOR_SCORE = 0.60
def ensure_dirs():
    for d in (RAW_DIR, UPLOAD_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)