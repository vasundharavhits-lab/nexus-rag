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
def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default

def _env_bool(name, default):
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")

# --- Large files ------------------------------------------------------------------------
# Set in .env, nothing is fixed in the code.  MAX_UPLOAD_MB=0 means "no limit".
MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 1024)
JOB_WORKERS = _env_int("JOB_WORKERS", 1)           # files processed at the same time

# --- OCR (scanned PDFs / images of text) ------------------------------------------------
OCR_ENABLED = _env_bool("OCR_ENABLED", True)
OCR_LANGS = os.getenv("OCR_LANGS", "auto")         # "auto" = pick from the printed script of each file; or fixed codes like eng+hin+san
OCR_DPI = _env_int("OCR_DPI", 150)                 # higher = slower, a little more accurate
OCR_WORKERS = _env_int("OCR_WORKERS", 0) or max(1, (os.cpu_count() or 2) - 1)
OCR_MIN_CHARS = _env_int("OCR_MIN_CHARS", 25)      # a page with less text than this is OCR'd
OCR_CLEAN = _env_bool("OCR_CLEAN", True)           # drop scanner noise / unreadable lines
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")     # full path to tesseract.exe if not on PATH

# File types the server accepts. Override in .env, e.g. SUPPORTED_TYPES=.pdf,.docx,.md
_DEFAULT_TYPES = (".pdf,.docx,.xlsx,.xlsm,.pptx,.odt,.odp,.ods,.rtf,.epub,.html,.htm,.xml,.json,.jsonl,.eml,"
                  ".md,.txt,.text,.log,.rst,.tex,.yaml,.yml,.ini,.cfg,.toml,.srt,.vtt,.csv,.tsv,"
                  ".py,.js,.ts,.java,.c,.cpp,.h,.cs,.go,.rb,.php,.sql,.sh,.bat,.ps1,.css,.kt,.swift,.r,"
                  ".png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp")
SUPPORTED = {t.strip().lower() if t.strip().startswith(".") else "." + t.strip().lower()
             for t in os.getenv("SUPPORTED_TYPES", _DEFAULT_TYPES).split(",") if t.strip()}
# A file with an unknown or missing extension is accepted when its content turns out to be a known type
# (PDF, Office, image, plain text...). Set ACCEPT_ANY_FILE=0 to allow only the extensions above.
ACCEPT_ANY_FILE = _env_bool("ACCEPT_ANY_FILE", True)
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
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
LLM_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT_S", "300"))
LLM_NUM_CTX = _env_int("LLM_NUM_CTX", 8192)         # context window asked from Ollama (Hindi text needs many tokens)
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 400)   # document answers: short, cited, but not cut off
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

# --- Answers in every language (see docs/HOW_ANSWERS_WORK.md) ------------------------------
# ANSWER_PIVOT=on   : non-English questions are answered in English first (models are best at it) and then
#                     translated, with the citations kept. Best for small local models (3B-8B).
# ANSWER_PIVOT=off  : the model writes the answer directly in the user's language. Use with a strong model.
ANSWER_PIVOT = os.getenv("ANSWER_PIVOT", "on").strip().lower() not in ("0", "off", "false", "no")
# Evidence sent to the model is trimmed to this many (estimated) tokens, whatever the script.
PROMPT_TOKEN_BUDGET = _env_int("PROMPT_TOKEN_BUDGET", 5000)
# Passages that are only a table of contents, an index or page furniture are not used as evidence.
DROP_JUNK_PASSAGES = _env_bool("DROP_JUNK_PASSAGES", True)
# Passages added around the best hits (the passage before and after), so an answer that continues
# onto the next chunk is not cut in half. 0 = off.
NEIGHBOR_PASSAGES = _env_int("NEIGHBOR_PASSAGES", 1)
# Vector search keeps the vectors of a workspace in memory (float16) instead of reading the database for
# every question. The cache refreshes by itself when documents change or after this many seconds.
VECTOR_CACHE_TTL_S = _env_int("VECTOR_CACHE_TTL_S", 120)
# Load the search model (and check the language model) when the server starts, so the first question is fast.
WARMUP_ON_START = _env_bool("WARMUP_ON_START", True)

# --- Answer checks (set in .env; 1 = on, 0 = off) -------------------------------------------
# CHECK_QUOTES: remove quotation marks around text that is not in the cited passages.
# CHECK_COPY:   if the answer copies a verse or line word for word, ask once more in plain words.
# CHECK_SUPPORT: refuse an answer whose key ideas are not in the cited passages (strict; can refuse
#                correct answers when the glossary is small). Off by default for now.
CHECK_QUOTES = _env_bool("CHECK_QUOTES", True)
CHECK_COPY = _env_bool("CHECK_COPY", True)
CHECK_SUPPORT = _env_bool("CHECK_SUPPORT", False)
# CHECK_CLAIMS: after answering, test each sentence against its citation. When one sentence fails, the
# whole answer is refused. Set to 0 to show the answer (the sentence check is then not applied).
CHECK_CLAIMS = _env_bool("CHECK_CLAIMS", True)

# Optional: a model used only to translate answers into Hinglish, e.g. aya-expanse:8b
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "").strip()

# Re-sort search results with a cross-encoder (needs the fastembed package). 1 = on, 0 = off.
RERANK = os.getenv("RERANK", "0").strip() == "1"
