# app/llm.py
"""Language-model access. One small layer so the rest of the app never knows which model runs.

  * generate(system, user)  - single-turn, temperature 0: answers from documents (RAG)
  * chat(messages)          - multi-turn: general conversation

Providers (config.LLM_PROVIDER): "ollama" (local, default) or "openai" (any OpenAI-compatible
API). The API key is read from the environment and is never logged or returned.
"""
import httpx
from app.config import (OLLAMA_URL, LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
                        CHAT_MODEL, LLM_TIMEOUT_S, LLM_MAX_TOKENS, CHAT_MAX_TOKENS,
                        CHAT_TEMPERATURE)


class LLMUnavailable(Exception):
    pass


def describe():
    """Public description of the active setup (no secrets)."""
    return {"provider": LLM_PROVIDER, "rag_model": LLM_MODEL, "chat_model": CHAT_MODEL,
            "base_url": LLM_BASE_URL if LLM_PROVIDER == "openai" else OLLAMA_URL,
            "api_key_set": bool(LLM_API_KEY)}


def _ollama(messages, model, temperature, max_tokens):
    payload = {"model": model, "stream": False, "messages": messages,
               "options": {"temperature": temperature, "num_ctx": 4096,
                           "num_predict": max_tokens}}
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=LLM_TIMEOUT_S)
        r.raise_for_status()
    except httpx.ConnectError as e:
        raise LLMUnavailable("Cannot reach Ollama. Start it and check "
                             f"{OLLAMA_URL} shows 'Ollama is running'.") from e
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"Ollama error: {e}. If the model is missing, run "
                             f"'ollama pull {model}'.") from e
    return r.json()["message"]["content"].strip()


_OPENAI_HINTS = {401: "the API key was rejected (check LLM_API_KEY)",
                 403: "access was denied (check LLM_API_KEY and the model name)",
                 404: "the model or endpoint was not found (check LLM_MODEL and LLM_BASE_URL)",
                 429: "the provider's rate limit or quota was reached"}


def _openai(messages, model, temperature, max_tokens):
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    payload = {"model": model, "messages": messages, "temperature": temperature,
               "max_tokens": max_tokens}
    try:
        r = httpx.post(f"{LLM_BASE_URL}/chat/completions", json=payload, headers=headers,
                       timeout=LLM_TIMEOUT_S)
        r.raise_for_status()
    except httpx.ConnectError as e:
        raise LLMUnavailable(f"Cannot reach the language-model service at {LLM_BASE_URL}.") from e
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        raise LLMUnavailable(f"The language-model service returned {code}: "
                             f"{_OPENAI_HINTS.get(code, 'request failed')}.") from e
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"Language-model request failed: {type(e).__name__}.") from e
    return r.json()["choices"][0]["message"]["content"].strip()


def _complete(messages, model, temperature, max_tokens):
    if LLM_PROVIDER == "openai":
        return _openai(messages, model, temperature, max_tokens)
    return _ollama(messages, model, temperature, max_tokens)


def generate(system: str, user: str) -> str:
    """Answer from documents: deterministic and short."""
    return _complete([{"role": "system", "content": system},
                      {"role": "user", "content": user}], LLM_MODEL, 0, LLM_MAX_TOKENS)


def chat(messages, temperature=None, max_tokens=None, model=None) -> str:
    """General conversation. `messages` = [{'role': 'system'|'user'|'assistant', 'content': ...}]."""
    return _complete(messages, model or CHAT_MODEL,
                     CHAT_TEMPERATURE if temperature is None else temperature,
                     max_tokens or CHAT_MAX_TOKENS)
