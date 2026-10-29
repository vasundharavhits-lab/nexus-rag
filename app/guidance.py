# app/guidance.py
"""Smart guide mode. Works with any documents: nothing in this file is about one book or one subject.

For every message the model first decides, from the person's own words, which kind it is:

  FEELING   the person says how they feel or describes a struggle
            -> the app learns what the uploaded documents are about, searches them for ideas that could help,
               and writes a gentle reply that cites a passage [n] only when a passage really says it.
               Without a relevant passage the reply is warm, general support, clearly labelled as such.
  QUESTION  anything else -> the normal document pipeline (documents first, verified and cited),
            and a labelled general answer when the documents do not cover it.

If a message suggests the person may be in danger, no search is done: a caring message with helpline numbers is returned.
"""
import re
import time
import uuid

from app import answering as ans
from app import db, hybrid, llm, search
from app.config import CHAT_MODEL, MIN_VECTOR_SCORE

DEV = re.compile(r"[\u0900-\u097F]")
FEELING_GATE = 0.8 * MIN_VECTOR_SCORE        # looser than question answering: feelings and advice match more loosely

# Words that suggest the person may be thinking of ending their life or hurting themselves.
# A word list can never catch everything, so this is a first safety net only.
CRISIS = re.compile(
    r"(kill myself|end my life|want to die|wanna die|suicid|self[- ]?harm|hurt myself|don'?t want to live|better off dead"
    r"|mar jaun|mar jau\b|marna chah|mar jana chah|jeena nahi|jeene ka (man|mann|mn)|jeene ki (iccha|ichha)|jaan de(n|ne| du| dun)"
    r"|khudkushi|khud ?kushi|aatm ?hatya|zindagi (khatam|khtm)|jindagi (khatam|khtm)|khatam kar (lu|lun|du|dun)|khud ko (nuksan|hurt|khatam)"
    r"|आत्महत्या|खुदकुशी|मर जाऊँ|मर जाऊं|मरना चाह|जीना नहीं|जीने का मन नहीं|जान दे|ज़िंदगी खत्म|जिंदगी खत्म|खुद को (नुकसान|खत्म))",
    re.I)

CRISIS_TEXT = {
    "hinglish": ("Tumne jo likha, use padh kar mujhe tumhari fikr ho rahi hai. Agar tumhe apni jaan ko khatra lag raha hai "
                 "ya khud ko nuksan pahunchane ka khayal aa raha hai, to abhi kisi apne ko bulao ya unke paas chale jao. "
                 "India mein Tele-MANAS ki free helpline 14416 (ya 1800-891-4416) par kabhi bhi baat kar sakte ho, "
                 "aur turant khatra ho to 112 dial karo. Tum akele nahi ho. Main yahin hoon."),
    "devanagari": ("आपने जो लिखा, उसे पढ़कर मुझे आपकी चिंता हो रही है। अगर आपको अपनी जान को खतरा लग रहा है या खुद को नुकसान "
                   "पहुँचाने का ख़याल आ रहा है, तो अभी किसी अपने को बुलाइए या उनके पास चले जाइए। भारत में Tele-MANAS की मुफ़्त "
                   "हेल्पलाइन 14416 (या 1800-891-4416) पर कभी भी बात कर सकते हैं, और तुरंत खतरा हो तो 112 डायल कीजिए। "
                   "आप अकेले नहीं हैं। मैं यहीं हूँ।"),
    "en": ("I am worried about you after reading this. If you feel your life is in danger or you are thinking of hurting "
           "yourself, please call or go to someone you trust right now. In India you can talk to the free Tele-MANAS "
           "helpline at 14416 (or 1800-891-4416) at any time, and if there is immediate danger, dial 112. "
           "You are not alone. I am here."),
}

DISCLAIMER_DOC = {
    "hinglish": "Note: Yeh tumhare documents par based ek vichar hai, therapy ya medical salah nahi.",
    "devanagari": "नोट: यह आपके दस्तावेज़ों पर आधारित एक विचार है, थेरेपी या चिकित्सा सलाह नहीं।",
    "en": "Note: This is a reflection based on your documents, not therapy or medical advice.",
}
DISCLAIMER_GEN = {
    "hinglish": "Note: Yeh general support hai, therapy ya medical salah nahi.",
    "devanagari": "नोट: यह सामान्य सहयोग है, थेरेपी या चिकित्सा सलाह नहीं।",
    "en": "Note: This is general support, not therapy or medical advice.",
}
NOTE_FEELING_GEN = "Not drawn from your documents: no passage in them spoke to this, so this is general support."

INTENT_SYSTEM = (
    "Classify the user's message into exactly one word.\n"
    "FEELING: the person talks about THEIR OWN current state or a personal struggle and wants comfort or advice "
    "(for example: I am sad, I feel lazy, mai bahut pareshan hu, kuch karne ka mann nahi hota).\n"
    "QUESTION: they ask for information or an explanation, even when the topic is an emotion "
    "(for example: how does anger affect the mind, what does the text say about fear, krodh kya hota hai, "
    "what is 2+2, summarise this chapter).\n"
    "If the message asks what something is, why something happens, or how a text explains something, it is QUESTION. "
    "The message may be in any language, including Hindi typed in English letters. Output only FEELING or QUESTION."
)

TOPIC_SYSTEM = (
    "You are given the file names and the first passages of some documents. In ONE line of at most 30 words, say what "
    "the documents are about (subject and kind of text). Do not add opinions. Output only the line."
)


def _theme_system(topic):
    return (
        f"The person uploaded documents about: {topic}\n"
        "The person now describes how they feel or a problem in their life, in any language. Write ONE English search "
        "line (at most 25 words) naming the kinds of ideas, teachings or advice in such documents that could help them, "
        "using plain words likely to appear in an English version of the text. Do not answer the person. Do not add "
        "quotes. Example input: I am afraid I will fail my exam. Example output: fear of failure, effort without "
        "worrying about results, staying calm under pressure, perseverance. Output only the search line.")


def _guide_system(topic):
    return (
        "You are Nexus, a gentle companion. The person uploaded documents about: " + topic + "\n"
        "Numbered sources from those documents may follow. Rules:\n"
        "1. Start with one or two warm sentences that acknowledge the feeling. Do not judge, scold or hurry them.\n"
        "2. If the sources genuinely speak to the feeling, share one or two ideas using ONLY what the sources say, in "
        "simple words, and put the source number like [1] right after each idea. Never invent quotes, names, or "
        "chapter or page numbers. If the sources do not really speak to it, or there are none, do not cite anything and "
        "do not claim the documents say anything: just be warm.\n"
        "3. Give two or three tiny, doable steps for today that fit what THIS person said (for example: drink water, walk "
        "for ten minutes, do one small task for five minutes, talk to one person). Do not repeat steps from earlier in the "
        "conversation and do not use a fixed list.\n"
        "4. Never diagnose, never promise a cure, never tell them to stop any treatment. If they say this has lasted "
        "weeks, gently suggest talking to someone they trust or a counsellor.\n"
        "5. Plain text only: no markdown, no bold, no bullet symbols, no headings. Keep it under 170 words.")


_TOPIC_CACHE = {}


def _kind(label_kind):
    return label_kind if label_kind in ("hinglish", "devanagari") else "en"


def _lang_rule(label, kind):
    rule = f"Reply in {label}."
    if kind == "hinglish":
        rule += " Use Roman letters only, the way people text in Hindi. Do not use Devanagari."
    elif kind == "devanagari":
        rule += " Use Devanagari script."
    return " " + rule


def _intent(message, history):
    """FEELING or QUESTION, decided by the model from the person's own words. Unsure -> QUESTION."""
    recent = " ".join(m["content"] for m in history[-2:] if m["role"] == "user")
    try:
        out = (llm.generate(INTENT_SYSTEM, (recent + " " + message).strip()[:500], max_tokens=6) or "").upper()
    except llm.LLMUnavailable:
        raise
    except Exception:
        out = ""
    return "FEELING" if "FEELING" in out else "QUESTION"


_SAMPLE_SQL = (
    "SELECT logical_name, filename, text FROM ("
    " SELECT d.logical_name, v.filename, c.text,"
    "        row_number() OVER (PARTITION BY v.version_id ORDER BY c.idx) AS rn"
    " FROM chunks c JOIN document_versions v ON v.version_id = c.version_id"
    " JOIN documents d ON d.document_id = v.document_id"
    " WHERE d.workspace_id = %s AND v.status = 'ok' AND c.strategy = 'structure') t"
    " WHERE rn <= 3 LIMIT 15")


def _corpus_topic(con, workspace_id):
    """One line on what the workspace's documents are about, written by the model from a small sample of them.
    Cached until the set of files changes, so it costs one model call per upload, not per message."""
    if not con or not workspace_id:
        return "the uploaded documents"
    try:
        rows = con.execute(_SAMPLE_SQL, (workspace_id,)).fetchall()
    except Exception:
        return "the uploaded documents"
    names = tuple(sorted({r["filename"] for r in rows}))
    if not names:
        return "the uploaded documents"
    key = (workspace_id, names)
    if key in _TOPIC_CACHE:
        return _TOPIC_CACHE[key]
    parts, used = [], 0
    for r in rows:
        txt = r["text"] or ""
        if ans.is_junk(txt) or ans.is_metadata_only(txt):
            continue
        snippet = f'[{r["filename"]}] ' + " ".join(txt.split())[:260]
        if used + len(snippet) > 2400:
            break
        parts.append(snippet)
        used += len(snippet)
    topic = "the uploaded documents"
    if parts:
        try:
            line = (llm.generate(TOPIC_SYSTEM, "\n".join(parts), max_tokens=60) or "").strip().strip('"')
            line = line.splitlines()[0].strip() if line else ""
            if len(line) >= 8:
                topic = line
        except llm.LLMUnavailable:
            raise
        except Exception:
            pass
    _TOPIC_CACHE[key] = topic
    return topic


def _theme_line(message, history, topic):
    recent = " ".join(m["content"] for m in history[-2:] if m["role"] == "user")
    text = (recent + " " + message).strip()[:600]
    try:
        line = (llm.generate(_theme_system(topic), text, max_tokens=70) or "").strip().strip('"')
    except llm.LLMUnavailable:
        raise
    except Exception:
        line = ""
    line = line.splitlines()[0].strip() if line else ""
    return line if len(line) >= 8 else message


def _passages(con, workspace_id, theme, n=4):
    """Passages that could help, or [] when nothing in the documents is close enough to the theme."""
    try:
        top = search.vector_search(con, workspace_id, theme, 1)
        if top and top[0]["score"] < FEELING_GATE:
            return []
    except Exception:
        pass
    rows = hybrid.hybrid_search(con, workspace_id, theme, k=n * 2)
    out, seen = [], set()
    for r in rows:
        txt = r.get("text") or ""
        if r["chunk_id"] in seen or ans.is_junk(txt) or ans.is_metadata_only(txt):
            continue
        seen.add(r["chunk_id"])
        out.append(r)
        if len(out) == n:
            break
    return [{"n": i, "chunk_id": r["chunk_id"], "filename": r["filename"], "label": r["label"],
             "heading_path": r["heading_path"], "page": r["page"], "score": round(float(r.get("score", 0) or 0), 4),
             "doc_status": r.get("doc_status"), "effective_at": r.get("effective_at"), "text": r["text"]}
            for i, r in enumerate(out, 1)]


def _public(e):
    return {k: v for k, v in e.items() if k != "text"}


def _result(status, answer, evidence, citations, trace, ms, source=None, note=None):
    res = {"run_id": str(uuid.uuid4()), "status": status, "answer": answer, "citations": citations,
           "evidence": [_public(e) for e in evidence], "invalid_citations": [], "model": CHAT_MODEL,
           "verification": None, "saved": False, "trace": trace,
           "timings_ms": {"retrieve": trace.get("retrieve_ms", 0.0), "generate": trace.get("generate_ms", 0.0), "total": ms}}
    if source:
        res["source"] = source
    if note:
        res["note"] = note
    return res


def _save(con, ok, workspace_id, user_id, message, res):
    if ok and workspace_id:
        db.save_run(con, {"run_id": res["run_id"], "workspace_id": workspace_id, "user_id": user_id,
                          "query": message, "mode": "general", "k": 0, "status": res["status"],
                          "answer": res["answer"], "model": CHAT_MODEL, "evidence": res["evidence"],
                          "timings": res["trace"]})
        res["saved"] = True


TRANSLATE_SYSTEM = (
    "Translate the user's text into {label}. Keep every source marker like [1] or [2] exactly as it is, right after "
    "the same idea. Use simple, everyday words, the way a kind friend would say it, in short sentences. Avoid difficult "
    "or bookish words. Keep the meaning exactly: do not add or remove ideas. Output only the translation.")


def _markers(text):
    found = set()
    for grp in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", text):
        found.update(int(x) for x in grp.split(","))
    return found


def _translate(draft, label, kind, code=None, message=None):
    """The model writes best in English, so the reply is drafted in English and then translated, keeping the [n] marks.
    First choice is the app's own route (for Hinglish: English -> Hindi in Devanagari -> Roman, using TRANSLATE_MODEL);
    if that gives nothing usable, a plain translation prompt is the fallback."""
    try:
        tr = ans.translate_answer(draft, label, llm.generate, sample=message)
        if tr and ans.in_target_language(tr, kind, code) and _markers(draft) <= _markers(tr):
            return tr
    except llm.LLMUnavailable:
        raise
    except Exception:
        pass
    system = TRANSLATE_SYSTEM.format(label=label) + _lang_rule(label, kind)
    need = _markers(draft)
    out = ""
    for strict in (False, True):
        user = draft if not strict else draft + "\n\n(Keep every [n] marker. Follow the script rule strictly.)"
        out = (llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                        temperature=0.2, max_tokens=520) or "").strip()
        script_ok = not ((kind == "hinglish" and DEV.search(out)) or (kind == "devanagari" and not DEV.search(out)))
        if out and script_ok and need <= _markers(out):
            return out
    if out and need - _markers(out):                 # markers lost: put them back at the end rather than lose the citations
        out += " " + " ".join(f"[{n}]" for n in sorted(need - _markers(out)))
    return out or draft


def _renumber(text, valid):
    """Cited passages become [1], [2], ... in order of use; marks that point to nothing are dropped."""
    new = {old: i for i, old in enumerate(valid, 1)}

    def sub(m):
        nums = [new[int(x)] for x in m.group(1).split(",") if int(x) in new]
        return "[" + ", ".join(str(n) for n in nums) + "]" if nums else ""
    out = re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", sub, text)
    out = re.sub(r"[ \t]+([.,;!?\u0964])", r"\1", out)      # no gap left where a dropped mark used to be
    return re.sub(r"[ \t]{2,}", " ", out), new


def _question(con, workspace_id, user_id, message, history, ok, k, answer_lang):
    """Same behaviour as the 'Auto' choice: documents first (verified, cited), labelled general answer as the fallback."""
    from app import chatting
    if not ok or not chatting.has_documents(con, workspace_id) or chatting.GREETING.match(message):
        return chatting._general(con, workspace_id, user_id, message, history, "guidance", chatting.NOTE_NO_DOCS)
    res = ans.answer_question(con, workspace_id, user_id, message, "auto", k, history, answer_lang)
    if res["status"] not in ("insufficient_evidence", "uncited"):
        res["source"], res["saved"] = "documents", True
        return res
    gate = res["trace"].get("gate_vector_score")
    return chatting._general(con, workspace_id, user_id, message, history, "guidance", chatting.NOTE_FALLBACK,
                             {"doc_attempt_run": res["run_id"], "doc_gate_score": gate})


def reply(con, workspace_id, user_id, message, history, ok, k=4, answer_lang=None):
    """history: already cleaned [{'role','content'}]. ok: the person owns this workspace."""
    t0 = time.perf_counter()
    label, kind, code = ans.target_language(message, answer_lang)
    kind = _kind(kind)

    if CRISIS.search(message):
        text = CRISIS_TEXT[kind]
        ms = round((time.perf_counter() - t0) * 1000, 1)
        res = _result("general_answer", text, [], [], {"mode": "guidance", "route": "crisis", "total_ms": ms}, ms,
                      source="general", note="Support message. This is not a document answer.")
        _save(con, ok, workspace_id, user_id, message, res)
        return res

    if _intent(message, history) != "FEELING":
        return _question(con, workspace_id, user_id, message, history, ok, k, answer_lang)

    # --- FEELING ---
    topic = _corpus_topic(con, workspace_id) if ok else "the uploaded documents"
    evidence = []
    theme = message
    t1 = time.perf_counter()
    if ok:
        theme = _theme_line(message, history, topic)
        evidence = _passages(con, workspace_id, theme, n=max(2, min(k, 4)))
    t2 = time.perf_counter()

    if evidence:
        blocks = "\n\n".join(f'<source id="{e["n"]}">\n{e["text"][:1100]}\n</source>' for e in evidence)
        user_msg = f"{blocks}\n\nThe person says: {message}"
    else:
        user_msg = f"(No sources.)\n\nThe person says: {message}"
    # Only the person's own earlier words go back to the model: its earlier replies made it repeat itself.
    said = [m for m in history[-6:] if m["role"] == "user"]
    draft_lang = " Reply in simple English." if kind != "en" else _lang_rule(label, kind)
    msgs = [{"role": "system", "content": _guide_system(topic) + draft_lang}] + said + [{"role": "user", "content": user_msg}]
    text = (llm.chat(msgs, temperature=0.4, max_tokens=420) or "").strip()
    if kind != "en":
        text = _translate(text, label, kind, code, message)

    valid = sorted(i for i in _markers(text) if 1 <= i <= len(evidence))
    text, renum = _renumber(text, valid)
    t3 = time.perf_counter()
    trace = {"mode": "guidance", "intent": "feeling", "topic": topic, "theme": theme, "route": "hybrid",
             "retrieve_ms": round((t2 - t1) * 1000, 1), "generate_ms": round((t3 - t2) * 1000, 1),
             "total_ms": round((t3 - t0) * 1000, 1)}

    if valid:
        cites = [dict(_public(evidence[old - 1]), n=renum[old]) for old in valid]
        res = _result("answered", text + "\n\n" + DISCLAIMER_DOC[kind], evidence, cites, trace, trace["total_ms"],
                      source="documents")
    else:
        # No idea in the reply rests on a passage: never present it as coming from the documents.
        res = _result("general_answer", text + "\n\n" + DISCLAIMER_GEN[kind], evidence, [], trace, trace["total_ms"],
                      source="general", note=NOTE_FEELING_GEN)
    _save(con, ok, workspace_id, user_id, message, res)
    return res
