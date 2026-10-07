# app/changes.py
"""Version comparison ("what changed from v1 to v3?").

Blueprint 7.4: keep version lineage and answer historical / change questions
instead of retrieving whatever text looks similar. This is deterministic: it
diffs the stored sections of two versions, so no LLM is called and every
statement in the answer comes straight from one of the two versions.

Valid time (the document's own Date: header, `effective_at`) is reported
separately from transaction time (when we ingested it, `ingested_at`).
"""
import difflib, re, time, uuid
from app import versions

# --------------------------------------------------------------------------- #
# 1. Understanding the question
# --------------------------------------------------------------------------- #
_VER = r"(?:v|version\s*)(\d+)\b"
_JOIN = r"(?:and|&|to|vs\.?|versus|through|->|→|with|against)"

_PAIR_PLURAL = re.compile(rf"\bversions\s*(\d+)\s*{_JOIN}\s*(?:v|version\s*)?(\d+)\b", re.I)
_PAIR = re.compile(rf"\b{_VER}\s*{_JOIN}\s*{_VER}", re.I)
_SINCE = re.compile(rf"\bsince\s+{_VER}", re.I)
_ANY_VER = re.compile(rf"\b{_VER}", re.I)

_CHANGE = re.compile(
    r"\b(chang(?:e|ed|es|ing)|differ(?:s|ent|ence|ences)?|diff|compar(?:e|ed|ison)|"
    r"vs\.?|versus|what'?s new|new in|evolv(?:e|ed)|updat(?:e|ed))\b", re.I)
_RANGE_WORD = re.compile(r"\b(from|between)\b", re.I)


def parse_compare(question: str):
    """Return {'kind': 'pair'|'single'|'since', 'from': 'v1'|None, 'to': 'v3'|None} or None.

    Deliberately conservative: a question such as "What does version 3 add?"
    is NOT a comparison and stays an ordinary RAG question.
    """
    q = question or ""
    m = _PAIR_PLURAL.search(q) or _PAIR.search(q)
    if m and (_CHANGE.search(q) or _RANGE_WORD.search(q)):
        return {"kind": "pair", "from": f"v{m.group(1)}", "to": f"v{m.group(2)}"}
    m = _SINCE.search(q)
    if m:
        return {"kind": "since", "from": f"v{m.group(1)}", "to": None}
    found = _ANY_VER.findall(q)
    if len(found) == 1 and _CHANGE.search(q):
        return {"kind": "single", "from": None, "to": f"v{found[0]}"}
    return None


# --------------------------------------------------------------------------- #
# 2. Finding the two versions
# --------------------------------------------------------------------------- #
_FILE_PREF = {"md": 0, "docx": 1, "pdf": 2}


def _num(label):
    m = re.search(r"\d+", str(label or ""))
    return int(m.group()) if m else 0


def _load_versions(con, workspace_id):
    rows = con.execute(
        "SELECT d.logical_name, v.version_id, v.label, v.filename, v.file_type, "
        "v.doc_status, v.effective_at, v.ingested_at, v.author "
        "FROM document_versions v JOIN documents d USING (document_id) "
        "WHERE d.workspace_id=%s AND v.status='ok'", (workspace_id,)).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["logical_name"], []).append(r)
    return out


def _pick(group, label):
    """Best version for a label. The same label can exist as .md/.docx/.pdf: prefer
    the one with the strongest status, then the most structured file type."""
    cands = [v for v in group if str(v["label"]).lower() == label.lower()]
    if not cands:
        return None, 0
    best = max(cands, key=lambda v: (versions.currency_key(v),
                                     -_FILE_PREF.get(v["file_type"], 9)))
    return best, len(cands) - 1


def _name_overlap(name, question):
    tokens = {t for t in re.split(r"[_\-\s]+", name.lower()) if len(t) > 2}
    words = set(re.findall(r"[a-z]+", question.lower()))
    return len(tokens & words)


def resolve(con, workspace_id, question, spec):
    """Return None (not applicable), or a dict with status 'ok' or 'missing_version'."""
    by_doc = _load_versions(con, workspace_id)
    multi = {n: g for n, g in by_doc.items() if len({str(v["label"]).lower() for v in g}) >= 2}
    if not multi:
        return None

    def labels_of(g):
        return sorted({str(v["label"]).lower() for v in g}, key=_num)

    # which documents can answer this question?
    cands = []
    for name, g in multi.items():
        labs = labels_of(g)
        if spec["kind"] == "pair" and spec["from"] in labs and spec["to"] in labs:
            cands.append(name)
        elif spec["kind"] == "single" and spec["to"] in labs and any(
                _num(l) < _num(spec["to"]) for l in labs):
            cands.append(name)
        elif spec["kind"] == "since" and spec["from"] in labs and any(
                _num(l) > _num(spec["from"]) for l in labs):
            cands.append(name)

    if not cands:
        wanted = [x for x in (spec["from"], spec["to"]) if x]
        avail = "; ".join(f"{n}: {', '.join(labels_of(g))}" for n, g in sorted(multi.items()))
        return {"status": "missing_version",
                "message": (f"I couldn't compare {' and '.join(wanted)}: no document in this "
                            f"workspace has {'those versions' if len(wanted) > 1 else 'that version'} "
                            f"with an earlier or later one to compare against. "
                            f"Versions available: {avail}.")}

    note = None
    if len(cands) > 1:
        scored = sorted(cands, key=lambda n: -_name_overlap(n, question))
        if _name_overlap(scored[0], question) == _name_overlap(scored[1], question):
            return {"status": "missing_version",
                    "message": ("Several documents have those versions "
                                f"({', '.join(sorted(cands))}). Please name the document, "
                                "for example: 'What changed in the architecture from v1 to v3?'")}
        name = scored[0]
        note = f"Several documents matched; chose '{name}' because the question mentions it."
    else:
        name = cands[0]

    group, labs = multi[name], labels_of(multi[name])
    a, b = spec["from"], spec["to"]
    if spec["kind"] == "single":
        a = max((l for l in labs if _num(l) < _num(b)), key=_num)
    elif spec["kind"] == "since":
        b = max(labs, key=_num)
    va, alt_a = _pick(group, a)
    vb, alt_b = _pick(group, b)
    notes = [n for n in (note,) if n]
    if alt_a or alt_b:
        notes.append("Some versions exist in more than one file format; the best-ranked "
                     "file was used for each.")
    return {"status": "ok", "document": name, "from": va, "to": vb, "notes": notes}


# --------------------------------------------------------------------------- #
# 3. Diffing
# --------------------------------------------------------------------------- #
_META_LINE = re.compile(r"^\s*(status|date|version|author|title)\s*:", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
REWORD_RATIO = 0.6   # sentence pairs at least this similar are shown as "reworded"


_BULLET = re.compile(r"^\s*(?:[-*\u2022\u25cf\u25aa]|\d+[.)])\s+")
_ENDS = re.compile(r"[.!?:;][\"')\]]*$")


def _logical_lines(text):
    """Undo hard line wraps (PDF text extraction) without merging real list items.

    A line continues onto the next one only when it does not end in sentence
    punctuation and the next line is non-empty, not a bullet / numbered item.
    """
    out, buf = [], ""
    for ln in text.splitlines():
        raw = ln.strip()
        if not raw or _META_LINE.match(raw):
            if buf:
                out.append(buf)
            buf = ""
            continue
        if buf and not _ENDS.search(buf) and not _BULLET.match(raw):
            buf = f"{buf} {raw}"
        else:
            if buf:
                out.append(buf)
            buf = raw
    if buf:
        out.append(buf)
    return out


_LEAD_JUNK = re.compile(r"^[^\w\"'(\[]+")      # invisible/odd bullet glyphs from PDF extraction


def _clean(s):
    return _LEAD_JUNK.sub("", s.strip()).strip()


def _sentences(text):
    out = []
    for ln in _logical_lines(text):
        ln = _BULLET.sub("", _clean(ln))
        out += [c for c in (_clean(x) for x in _SENT.split(ln) if x) if c]
    return out


def diff_sentences(old_text, new_text):
    a, b = _sentences(old_text), _sentences(new_text)
    sa, sb = set(a), set(b)
    removed = [s for s in a if s not in sb]
    added = [s for s in b if s not in sa]
    changes, used = [], set()
    for r in removed:                       # pair each removed sentence with its closest new one
        best, best_ratio = None, 0.0
        for i, ad in enumerate(added):
            if i in used:
                continue
            ratio = difflib.SequenceMatcher(None, r.lower(), ad.lower()).ratio()
            if ratio > best_ratio:
                best, best_ratio = i, ratio
        if best is not None and best_ratio >= REWORD_RATIO:
            used.add(best)
            changes.append({"type": "reworded", "old": r, "new": added[best]})
        else:
            changes.append({"type": "removed", "old": r, "new": None})
    changes += [{"type": "added", "old": None, "new": ad}
                for i, ad in enumerate(added) if i not in used]
    return changes


def _sections(con, version_id):
    rows = con.execute("SELECT heading_path, text FROM sections WHERE version_id=%s ORDER BY idx",
                       (version_id,)).fetchall()
    out = {}
    for r in rows:
        out[r["heading_path"]] = (out.get(r["heading_path"], "") + "\n\n" + r["text"]).strip()
    return out


def diff_versions(con, va, vb):
    sa, sb = _sections(con, va["version_id"]), _sections(con, vb["version_id"])
    sections, counts = [], {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
    for path in list(sa) + [p for p in sb if p not in sa]:
        ta, tb = sa.get(path), sb.get(path)
        if ta is not None and tb is not None:
            ch = diff_sentences(ta, tb)
            status = "modified" if ch else "unchanged"
        elif ta is None:
            ch = [{"type": "added", "old": None, "new": s} for s in _sentences(tb)]
            status = "added" if ch else "unchanged"
        else:
            ch = [{"type": "removed", "old": s, "new": None} for s in _sentences(ta)]
            status = "removed" if ch else "unchanged"
        if status == "unchanged" and not (ta and tb and _sentences(ta)):
            continue            # header-only sections carry no content to report
        counts[status] += 1
        if status != "unchanged":
            sections.append({"heading_path": path, "status": status, "changes": ch})
    meta = []
    for field, label in (("doc_status", "status"), ("effective_at", "date"), ("author", "author")):
        if (va[field] or None) != (vb[field] or None):
            meta.append({"field": label, "old": va[field], "new": vb[field]})
    return {"sections": sections, "counts": counts, "metadata_changes": meta}


def _meta(v):
    return {"version_id": v["version_id"], "label": v["label"], "filename": v["filename"],
            "status": v["doc_status"], "effective_at": v["effective_at"],
            "ingested_at": str(v["ingested_at"]) if v["ingested_at"] else None}


def compare(con, workspace_id, document, from_label, to_label):
    """Public helper used by the /api/v1/changes endpoint."""
    by_doc = _load_versions(con, workspace_id)
    group = by_doc.get(document)
    if not group:
        return None
    va, _ = _pick(group, from_label)
    vb, _ = _pick(group, to_label)
    if not va or not vb:
        return None
    d = diff_versions(con, va, vb)
    return {"document": document, "from": _meta(va), "to": _meta(vb), **d}


# --------------------------------------------------------------------------- #
# 4. Answering (deterministic, cited)
# --------------------------------------------------------------------------- #
MAX_LINES = 10
_TYPE_ORDER = ("reworded", "added", "removed")      # display order within the answer


def select_balanced(items, max_lines=MAX_LINES):
    """Pick up to `max_lines` changes without letting one kind crowd out the others.

    `items` is a list of (heading_path, change). Taking the first N in document order
    hides every addition when the old version simply has more removed sentences (the
    v1-vs-v3 PDF case). Instead take changes round-robin across reworded / added /
    removed, then show them grouped by kind, each group in document order.
    Returns (shown, hidden_counts_by_type).
    """
    queues = {t: [it for it in items if it[1]["type"] == t] for t in _TYPE_ORDER}
    taken = {t: 0 for t in _TYPE_ORDER}
    left = max_lines
    while left > 0 and any(taken[t] < len(queues[t]) for t in _TYPE_ORDER):
        for t in _TYPE_ORDER:
            if left > 0 and taken[t] < len(queues[t]):
                taken[t] += 1
                left -= 1
    shown = [it for t in _TYPE_ORDER for it in queues[t][:taken[t]]]
    hidden = {t: len(queues[t]) - taken[t] for t in _TYPE_ORDER if len(queues[t]) > taken[t]}
    return shown, hidden


def summarize_counts(items):
    n = {t: sum(1 for _, c in items if c["type"] == t) for t in _TYPE_ORDER}
    parts = [f"{n[t]} {t}" for t in _TYPE_ORDER if n[t]]
    return "Overall: " + ", ".join(parts) + " (sentence-level)." if parts else ""


def _norm(t):
    return " ".join(t.lower().split())


def _chunk_for(con, version_id, heading_path, sentence):
    """Find the indexed chunk that contains `sentence` so the citation can open it."""
    rows = con.execute(
        "SELECT chunk_id, page, text FROM chunks "
        "WHERE version_id=%s AND strategy='structure' AND heading_path=%s ORDER BY idx",
        (version_id, heading_path)).fetchall()
    for r in rows:
        if _norm(sentence) in _norm(r["text"]):
            return r
    return rows[0] if rows else None


def _quote(s, limit=200):
    s = s.strip()
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"


def answer_compare(con, workspace_id, question):
    """Return a query-result dict for a comparison question, or None to fall back to RAG."""
    t0 = time.perf_counter()
    spec = parse_compare(question)
    if spec is None:
        return None
    res = resolve(con, workspace_id, question, spec)
    if res is None:
        return None

    base_trace = {"route": "version_diff", "reason": "comparison question",
                  "compare": spec, "gate_threshold": None, "gate_vector_score": None}
    if res["status"] != "ok":
        return _result("insufficient_evidence", res["message"], [], base_trace, t0)

    va, vb, name = res["from"], res["to"], res["document"]
    d = diff_versions(con, va, vb)
    evidence, index = [], {}

    def cite(v, path, sentence):
        key = (v["version_id"], path, sentence)
        if key in index:
            return index[key]
        ch = _chunk_for(con, v["version_id"], path, sentence)
        evidence.append({"n": len(evidence) + 1, "chunk_id": ch["chunk_id"] if ch else None,
                         "filename": v["filename"], "label": v["label"],
                         "heading_path": path, "page": ch["page"] if ch else None,
                         "score": None, "doc_status": v["doc_status"],
                         "effective_at": v["effective_at"]})
        index[key] = len(evidence)
        return index[key]

    def desc(v):
        bits = [str(v["doc_status"]).lower() if v["doc_status"] else None, v["effective_at"]]
        return f"{v['label']} ({', '.join(b for b in bits if b)})" if any(bits) else v["label"]

    items = [(sec["heading_path"], c) for sec in d["sections"] for c in sec["changes"]]
    shown, hidden = select_balanced(items)
    lines = []
    for path, c in shown:                      # look up citations only for the lines we show
        if c["type"] == "reworded":
            lines.append(f"{path} was reworded. Before: \"{_quote(c['old'])}\" "
                         f"[{cite(va, path, c['old'])}] Now: \"{_quote(c['new'])}\" "
                         f"[{cite(vb, path, c['new'])}]")
        elif c["type"] == "added":
            lines.append(f"{path} added: \"{_quote(c['new'])}\" [{cite(vb, path, c['new'])}]")
        else:
            lines.append(f"{path} removed: \"{_quote(c['old'])}\" [{cite(va, path, c['old'])}]")
    head = f"Comparing {name} {desc(va)} with {desc(vb)}."
    meta = [f"{m['field'].capitalize()} changed from {m['old'] or 'unknown'} to {m['new'] or 'unknown'}."
            for m in d["metadata_changes"]]
    if not items:
        body = "No content differences were found between these versions."
    else:
        body = "\n".join(f"- {ln}" for ln in lines)
        if hidden:
            more = ", ".join(f"{n} more {t}" for t, n in hidden.items())
            body += f"\n- …and {more} (see /api/v1/changes for the full list)."
    summary = summarize_counts(items)
    answer = "\n".join([head] + meta + ([summary] if summary else []) + [body])
    trace = {**base_trace, "document": name, "from": va["label"], "to": vb["label"],
             "counts": d["counts"], "notes": res["notes"]}
    return _result("answered", answer, evidence, trace, t0)


def _cited(text):
    return sorted({int(x) for x in re.findall(r"\[(\d+)\]", text)})


def _result(status, answer, evidence, trace, t0):
    ms = round((time.perf_counter() - t0) * 1000, 1)
    trace = {**trace, "retrieve_ms": ms, "generate_ms": 0.0, "verify_ms": 0.0, "total_ms": ms}
    used = set(_cited(answer))
    cites = [e for e in evidence if e["n"] in used] if status == "answered" else []
    return {"run_id": str(uuid.uuid4()), "status": status, "answer": answer,
            "citations": cites, "evidence": evidence, "invalid_citations": [],
            "model": None, "trace": trace, "verification": None,
            "timings_ms": {"retrieve": ms, "generate": 0.0, "total": ms}}
