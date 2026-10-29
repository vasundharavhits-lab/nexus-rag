# app/rewrite.py
"""Understand a question typed in any language, including a language typed in Latin letters (romanized).

Small models translate romanized text badly ("yudha kaha hua tha" -> "where did yudha live?") because they
never see the real word. They are much better when they first write the question in the language's own
script and translate from that. So one model call is asked, in this order:

    Language: <what the question is written in>
    Native:   <the question in that language's own script>
    English:  <a faithful English translation, made from the native text>
    <DocLanguage>: <the question in each language the documents are written in>

Nothing here is specific to one language. Use rewrite_queries(question, prof, generate) as a drop-in
replacement for ai_steps.rewrite_queries: it returns the list of versions to search with (English first).
"""
import re
from app import grounding as gr

try:                                                     # a display name for a language code ("hi" -> "Hindi")
    from app.ai_steps import lang_name
except Exception:                                        # a different ai_steps.py: fall back to the code itself
    def lang_name(code):
        return code

_KEY = re.compile(r"^\s*[-*\d.)\s]*\**\s*([^:：\n]{2,40}?)\s*\**\s*[:：]\s*\**\s*(.+?)\s*$")


def rewrite_system(doc_langs=()):
    extra = "".join(f"\n{name}: the same question in {name}, written in {name}'s own script"
                    for name in doc_langs)
    return ("You prepare a question for a document search. The question may be in any language, and it may be "
            "typed in Latin letters even though the language normally uses another script (romanized text). "
            "Keep every noun and verb, do not summarize, do not add words, and do not answer the question. "
            "Reply with exactly these lines and nothing else:\n"
            "Language: the language the question is written in (add 'romanized' if typed in Latin letters)\n"
            "Native: the question written in that language's own script (copy it unchanged if it already is)\n"
            "English: a faithful English translation, made from the native text" + extra)


def parse(raw, question):
    """{'language', 'native', 'english', 'others': [..]} from the model's reply. Missing parts are None."""
    out = {"language": None, "native": None, "english": None, "others": []}
    for ln in (raw or "").splitlines():
        m = _KEY.match(ln)
        if not m:
            continue
        key, val = m.group(1).strip().casefold(), m.group(2).strip().strip('"\u201c\u201d')
        if not 2 <= len(val) <= 300:
            continue
        if key == "language":
            out["language"] = val
        elif key == "native":
            out["native"] = val
        elif key == "english":
            out["english"] = val
        elif val.casefold() != question.casefold() and val not in out["others"]:
            out["others"].append(val)
    # sanity checks: the English line must be English-looking, the native line must contain letters
    if out["english"] and not gr.is_latin(out["english"], 0.8):
        out["english"] = None
    if out["native"] and not any(c.isalpha() for c in out["native"]):
        out["native"] = None
    return out


def rewrite_chain(question, prof, generate, max_doc_langs=2):
    """Run the rewrite. Returns the parsed dict plus 'queries' (English first, then the native-script question,
    then the document languages), or queries == [] when the model could not be used."""
    doc_langs = []
    for code, _ in (prof or {}).get("languages", []):
        if code != "en" and len(doc_langs) < max_doc_langs:
            doc_langs.append(lang_name(code))
    try:
        raw = generate(rewrite_system(doc_langs), question, max_tokens=220)
    except Exception:
        return {"language": None, "native": None, "english": None, "others": [], "queries": []}
    res = parse(raw, question)
    queries = []
    for q in [res["english"], res["native"], *res["others"]]:
        if q and q.casefold() != question.casefold() and q not in queries:
            queries.append(q)
    res["queries"] = queries
    return res


def rewrite_queries(question, prof, generate):
    """Same call as ai_steps.rewrite_queries: the versions of the question to search with, [] if the model fails."""
    return rewrite_chain(question, prof, generate)["queries"]
