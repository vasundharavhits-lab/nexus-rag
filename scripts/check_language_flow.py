# scripts/check_language_flow.py - runs answer_question end to end with a fake model (no DB, no Ollama).
# Run from the project folder:  python scripts/check_language_flow.py
import sys, types, os
from unittest import mock
sys.path.insert(0, ".")
os.environ.update({"CHECK_QUOTES":"0","CHECK_COPY":"0","CHECK_SUPPORT":"0","CHECK_CLAIMS":"0"})
for name in ["app.db","app.search","app.hybrid","app.router","app.versions","app.glossary",
             "app.quote_check","app.support_check","app.verify","app.changes","app.llm"]:
    sys.modules[name] = mock.MagicMock()
class LLMUnavailable(Exception): pass
sys.modules["app.llm"].LLMUnavailable = LLMUnavailable
import app.ai_steps as ai
import app.answer_format as af
import app.answering as A
A.ai.doc_profile = lambda *a, **k: {"languages": []}
A.ai.margin = lambda rows: 1.0
A.ai.rewrite_reason = lambda *a, **k: None
A.glossary.expand = lambda q: ""
A.versions.intent = lambda q: ("none", None)
A.versions.apply = lambda con, ws, q, rows: (rows, {})
A.changes.answer_compare = lambda *a, **k: None
A.quote_check.strip_unsupported = lambda body, texts: (body, [])
A.quote_check.copies_source = lambda body, texts: False
A.support_check.check = lambda body, texts: (True, "ok")
A.verify.verify_answer = lambda *a, **k: []
PASSAGE = ("Krishna blew his conch, named Paficajanya, at the start of the war. "
           "Each warrior had a special conch with its own name.")
ROW = {"chunk_id": "c1", "filename": "279.pdf", "label": "v1", "heading_path": "ch1", "page": 21,
       "score": 0.84, "doc_status": None, "effective_at": None, "text": PASSAGE}
A.retrieve = lambda con, ws, q, mode, n: ([ROW], 0.84, "hybrid", "test")
A.hybrid = mock.MagicMock()

def run(question, translator_output, label):
    calls = []
    def gen(system, user, **kw):
        calls.append(("translate" if "translate" in system.lower() else "answer", user[:60]))
        if "translate" in system.lower():
            return translator_output
        return "Krishna's conch was named Paficajanya [1]. It was a special name [1]."
    A.llm.generate = gen
    res = A.answer_question(mock.MagicMock(), "ws", "u", question, mode="auto", k=4)
    print(f"--- {label}")
    print("answer:", res["answer"])
    print("trace pivot/language:", res["trace"].get("pivot"), res["trace"].get("language_fix"),
          "| rejected:", res["trace"].get("language_rejected"), "| calls:", [c[0] for c in calls])
    return res

Q = "Shri Krishna ke shankh ka kya naam tha?"
run(Q, "Shri Krishna ke shankh ka naam Paficajanya tha [1]. Yeh ek khaas naam tha [1].", "good Hinglish translation")
run(Q, "Krishna ke shankh ka naam Paficajanya tha. Yeh khaas naam tha.", "translation without citations")
run(Q, "Krishna's conch was named Paficajanya [1].", "translator returned English")

# the translator must be shown the user's question as the style sample
seen = []
A.llm.generate = lambda system, user, **kw: (seen.append(user) or "Krishna ke shankh ka naam Paficajanya tha [1].") if "translate" in system.lower() else "Krishna's conch was named Paficajanya [1]."
A.answer_question(mock.MagicMock(), "ws", "u", Q, mode="auto", k=4)
assert any(Q in u and "same language" in u for u in seen), seen
print("sample passed to translator: OK")

# --- grounding check (CHECK_SUPPORT=1): a wrong answer whose passage does not state it must be refused
A.CHECK_SUPPORT = True
def run_grounded(reply_to_check, label):
    def gen(system, user, **kw):
        if "check an answer" in system.lower():
            return reply_to_check
        return "Shri Krishna ke shankh ka naam Paficajanya tha [1]."
    A.llm.generate = gen
    return A.answer_question(mock.MagicMock(), "ws", "u", Q, mode="auto", k=4)

res = run_grounded("NO", "checker says NO")
print("--- checker NO:", res["status"], "|", res["answer"][:60])
assert res["status"] == "insufficient_evidence"
res = run_grounded("YES.", "checker says YES")
print("--- checker YES:", res["status"])
assert res["status"] == "answered"
res = run_grounded("maybe?", "checker unclear")
print("--- checker unclear:", res["status"])
assert res["status"] == "answered"
assert A.grounded(Q, "x [1]", ["a"], lambda s, u, **k: "NO") == (False, {"grounding": "no"})
print("grounding checks: OK")

# --- Hinglish questions are searched in English, even when the first search looks confident
searched = []
def fake_retrieve(con, ws, q, mode, n):
    searched.append(q)
    return ([ROW], 0.84, "hybrid", "test")
A.retrieve = fake_retrieve
A.CHECK_SUPPORT = False
def gen_rewrite(system, user, **kw):
    if "rewrite a search question" in system.lower():
        return "Where did the battle take place?"
    if "translate" in system.lower():
        return "Yuddh Kurukshetra mein hua tha [1]."
    return "The battle took place in Kurukshetra [1]."
A.llm.generate = gen_rewrite
A.ai.rewrite_reason = lambda *a, **k: None          # the first search looks strong, so no rewrite was asked for
res = A.answer_question(mock.MagicMock(), "ws", "u", "Yuddh kahan hua tha?", mode="auto", k=4)
print("searched with:", searched[:2], "| status:", res["status"])
assert any("battle" in q.lower() for q in searched), searched
print("hinglish search in English: OK")

# --- the grounding check also gets the English version of a Hinglish question
seen_ground = []
def gen_ground(system, user, **kw):
    if "check an answer" in system.lower():
        seen_ground.append(user)
        return "YES"
    if "rewrite a search question" in system.lower():
        return "Where did the battle take place?"
    if "translate" in system.lower():
        return "Yuddh kahan hua tha [1]."
    return "The battle took place at Kurukshetra [1]."
A.llm.generate = gen_ground
A.CHECK_SUPPORT = True
A.retrieve = lambda con, ws, q, mode, n: ([ROW], 0.84, "hybrid", "test")
A.answer_question(mock.MagicMock(), "ws", "u", "Yuddh kahan hua tha?", mode="auto", k=4)
assert seen_ground and "in English: Where did the battle take place?" in seen_ground[0], seen_ground
print("grounding gets English question: OK")

# --- Hinglish via the translator model: English -> Hindi (Devanagari) -> Roman Hinglish
from app import translit as T
A.TRANSLATE_MODEL = "aya-expanse:8b"
calls_t = []
def fake_generate_with(model, system, user, max_tokens=None):
    calls_t.append(model)
    return "युद्ध कुरुक्षेत्र में हुआ [3]।"
A.llm.generate_with = fake_generate_with
out = A.translate_answer("The war took place in Kurukshetra [3].", "Hinglish (Hindi written in English letters)",
                         A.llm.generate, sample="Yuddh kahan hua tha?")
print("hinglish via translator:", out)
assert out == "yuddh kurukshetra mein hua [3]." and calls_t and all(m == "aya-expanse:8b" for m in calls_t), (out, calls_t)
print("translator path: OK")
