# app/llm.py
import httpx
from app.config import OLLAMA_URL, LLM_MODEL, LLM_TIMEOUT_S, LLM_MAX_TOKENS

class LLMUnavailable(Exception):
    pass

def generate(system: str, user: str) -> str:
    payload = {
        "model": LLM_MODEL, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": LLM_MAX_TOKENS},
    }
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=LLM_TIMEOUT_S)
        r.raise_for_status()
    except httpx.ConnectError as e:
        raise LLMUnavailable("Cannot reach Ollama. Start it and check "
                             f"{OLLAMA_URL} shows 'Ollama is running'.") from e
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"Ollama error: {e}. If the model is missing, run "
                             f"'ollama pull {LLM_MODEL}'.") from e
    return r.json()["message"]["content"].strip()