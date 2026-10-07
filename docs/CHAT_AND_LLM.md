# Nexus as a chatbot: general questions and any language model

Nexus now answers **two kinds of question** in the same chat box:

| "Answer from" | What happens | Citations and claim check |
|---|---|---|
| **Auto** (default) | Searches your documents first. If they cover the question, answers from them. If not, answers from the model's general knowledge and says so. | Only for document answers |
| **My documents only** | Strict mode: answers only from your files, or refuses. | Yes |
| **General chat** | An ordinary assistant. Documents are not used. | No |

A general answer is always labelled **General answer** with a note, because it is *not* checked
against your files. Document answers keep the **From your documents** label.

## Flow of one message (Auto)

    message + last 10 messages
        -> workspace has indexed documents?  no -> general answer
        -> document search + 0.6 relevance gate
              covers it  -> cited answer + claim check              (source = documents)
              does not   -> general answer, refusal kept as a run   (source = general)

The refusal that triggers the fallback is still saved as a run, so "questions your documents
could not answer" stays visible in analytics as a coverage-gap signal. General answers are kept
out of the answered/refusal rates and latency medians (they are counted as `general_answers`).

## Choose the language model (.env)

Copy `.env.example` to `.env`.

* **Local (default):** `LLM_PROVIDER=ollama`, `LLM_MODEL=<any model you pulled>`.
* **Hosted:** `LLM_PROVIDER=openai` plus `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. This works with
  any service that offers an OpenAI-style `/chat/completions` endpoint.
* `CHAT_MODEL` lets general chat use a stronger model than the one that writes cited answers.
  Restart `uvicorn` after changing `.env`. The active model is shown in the settings panel.

**Privacy.** With a hosted provider, general messages *and the document passages used for
cited answers* are sent to that provider. Use Ollama if your documents must stay on your computer.

## Protecting a shared link

`X-User-Id` is a label, not a login. Anyone with your public link can chat, which uses your CPU
or your API credits. `CHAT_RATE_LIMIT_PER_MIN` (default 30, all users together) returns a clear
"too many requests" message when exceeded. For real use add authentication.

## API

    POST /api/v1/chat
    {"message": "...", "workspace_id": "optional", "scope": "auto|documents|general",
     "mode": "auto|vector|keyword", "history": [{"role": "user", "content": "..."}, ...]}

The response is the usual answer object plus `source` (`documents` or `general`), `note`, and
`saved` (whether it was stored as a run; feedback needs a saved run). `GET /api/v1/model` shows the
active provider and models, never the key. `POST /api/v1/query` is unchanged.

## Limits

* Replies appear when finished (no token streaming yet).
* The browser keeps the conversation; reloading the page starts a new one.
* General answers can be wrong. They are not verified.
* The 0.6 document gate decides what counts as "covered"; questions near the boundary can go either way.

## If you edited main.py or analytics.py yourself

Copy `app/chatting.py` and `app/llm.py` as they are, then add by hand: in `main.py` the `chatting`
import and the `/api/v1/chat` and `/api/v1/model` routes (see the patch's main.py); in
`analytics.py` the `general_answer` filter at the top of `retrieval_analytics`.

## Tests

`python -m pytest` (adds `test_chat.py`, `test_chat_http.py`). The page itself is tested with
`cd tests/ui && npm install jsdom && node chat_ui_test.js ../../app/static/chat.html`.
