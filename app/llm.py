# app/llm.py
"""Language-model access. One small layer so the rest of the app never knows which model runs.

  * generate(system, user)  - single-turn, temperature 0: answers from documents (RAG)
  * chat(messages)          - multi-turn: general conversation

Providers (config.LLM_PROVIDER): "ollama" (local, default) or "openai" (any OpenAI-compatible
API). The API key is read from the environment and is never logged or returned.
"""
import os
import time
import httpx
from app.config import (OLLAMA_URL, LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
                        CHAT_MODEL, LLM_TIMEOUT_S, LLM_MAX_TOKENS, CHAT_MAX_TOKENS,
                        CHAT_TEMPERATURE, LLM_NUM_CTX)


class LLMUnavailable(Exception):
    pass


def describe():
    """Public description of the active setup (no secrets)."""
    return {"provider": LLM_PROVIDER, "rag_model": LLM_MODEL, "chat_model": CHAT_MODEL,
            "base_url": LLM_BASE_URL if LLM_PROVIDER == "openai" else OLLAMA_URL,
            "api_key_set": bool(LLM_API_KEY)}


def _explain_status(r, model):
    """Turn an Ollama HTTP error into a plain sentence (never empty)."""
    try:
        msg = r.json().get("error") or r.text
    except Exception:
        msg = r.text
    msg = (msg or "").strip()[:300]
    low = msg.lower()
    if r.status_code == 404 or "not found" in low:
        return f"The model '{model}' is not installed in Ollama. Run: ollama pull {model}"
    if "memory" in low:
        return (f"Ollama does not have enough free memory to load '{model}' ({msg}). "
                "Close other programs, or use a smaller model (qwen2.5:3b) in .env.")
    return f"Ollama returned HTTP {r.status_code}: {msg or 'no details'}"


def _ollama(messages, model, temperature, max_tokens, repeat_penalty=None):
    payload = {"model": model, "stream": False, "messages": messages,
               "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "60m"),   # keep the model in memory between questions
               "options": {"temperature": temperature, "num_ctx": LLM_NUM_CTX,
                           "num_predict": max_tokens}}
    if repeat_penalty:
        payload["options"]["repeat_penalty"] = repeat_penalty     # stops the model looping on the same words
    timeout = httpx.Timeout(LLM_TIMEOUT_S, connect=10)
    last = None
    for attempt in (1, 2):       # one automatic retry: Ollama may just be loading or restarting
        try:
            r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
        except httpx.ConnectError:
            last = LLMUnavailable(f"Cannot reach Ollama at {OLLAMA_URL}. Start the Ollama app "
                                  "(or run 'ollama serve') and check that address shows 'Ollama is running'.")
        except httpx.TimeoutException:
            last = LLMUnavailable(f"The model '{model}' did not answer within {LLM_TIMEOUT_S} s. "
                                  "It is probably still loading or the computer is short of memory. "
                                  "Try again in a minute, or use a smaller model (qwen2.5:3b).")
        except httpx.HTTPError as e:
            last = LLMUnavailable(f"The connection to Ollama broke ({type(e).__name__}). "
                                  "Ollama may have restarted or run out of memory.")
        else:
            if r.status_code >= 400:
                raise LLMUnavailable(_explain_status(r, model))      # a real error: do not retry
            return r.json()["message"]["content"].strip()
        if attempt == 1:
            time.sleep(3)
    raise last


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


def _complete(messages, model, temperature, max_tokens, repeat_penalty=None):
    if LLM_PROVIDER == "openai":
        return _openai(messages, model, temperature, max_tokens)
    return _ollama(messages, model, temperature, max_tokens, repeat_penalty)


def generate_with(model, system: str, user: str, max_tokens=None) -> str:
    """Same as generate(), but with a named model (used for translation only)."""
    return _complete([{"role": "system", "content": system},
                      {"role": "user", "content": user}], model, 0, max_tokens or LLM_MAX_TOKENS)


def generate(system: str, user: str, max_tokens=None, repeat_penalty=None) -> str:
    """Answer from documents: deterministic and short."""
    return _complete([{"role": "system", "content": system},
                      {"role": "user", "content": user}], LLM_MODEL, 0, max_tokens or LLM_MAX_TOKENS,
                     repeat_penalty)


def chat(messages, temperature=None, max_tokens=None, model=None) -> str:
    """General conversation. `messages` = [{'role': 'system'|'user'|'assistant', 'content': ...}]."""
    return _complete(messages, model or CHAT_MODEL,
                     CHAT_TEMPERATURE if temperature is None else temperature,
                     max_tokens or CHAT_MAX_TOKENS)
