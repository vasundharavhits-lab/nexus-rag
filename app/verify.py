# app/verify.py
import re
import numpy as np

MODEL_NAME = "cross-encoder/nli-deberta-v3-small"
ENTAIL = 1          # label order: contradiction, entailment, neutral
SUPPORT_MIN = 0.5   # entailment probability needed to call a claim supported

# Verbs that let a list sentence be split: "The system uses A, B and C".
LEAD_VERBS = {"uses", "use", "includes", "include", "stores", "handles", "runs",
              "adds", "provides", "supports", "contains", "combines", "relies",
              "needs", "requires"}
_SPLIT = re.compile(r"\s*;\s*|,\s+and\s+|,\s+|\s+and\s+")

_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder
        _model = CrossEncoder(MODEL_NAME)
    return _model

def _verb_index(words):
    for i, w in enumerate(words):
        if w.lower().strip(".,;:") in LEAD_VERBS:
            return i
    return None

def split_compound(text, max_parts=6):
    """Split one sentence into smaller claims. Returns [text] when unsure."""
    body = text.strip().rstrip(".!?").strip()
    segs = [s.strip() for s in _SPLIT.split(body) if s and s.strip()]
    if len(segs) < 2 or len(segs) > max_parts:
        return [body]
    first = segs[0].split()
    vi = _verb_index(first)
    later_have_verb = any(_verb_index(s.split()) is not None for s in segs[1:])
    # List mode: "The system uses A, B and C" -> repeat the opening words.
    if vi is not None and not later_have_verb and all(len(s.split()) <= 6 for s in segs[1:]):
        lead = " ".join(first[:vi + 1])
        return [segs[0]] + [f"{lead} {s}" for s in segs[1:]]
    # Independent clauses: every part is long enough to stand alone.
    if len(first) >= 4 and all(len(s.split()) >= 4 for s in segs[1:]):
        return segs
    return [body]

def split_claims(answer):
    """Split an answer into claims, with citation markers removed, plus the cited numbers."""
    parts = re.split(r"(?<=[.!?])\s+(?!\[)", answer.strip())
    out = []
    for p in parts:
        cited = sorted({int(x) for g in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", p)
                        for x in g.split(",")})
        text = re.sub(r"\s*\[\d+(?:\s*,\s*\d+)*\]", "", p).strip()
        if len(text.split()) >= 3:
            end = text[-1] if text[-1] in ".!?" else ""
            for sub in split_compound(text):
                if len(sub.split()) >= 3:
                    out.append({"text": sub + end, "cited": cited})
    return out

def _entailment(pairs):
    logits = get_model().predict(pairs)
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return (e / e.sum(axis=1, keepdims=True))[:, ENTAIL]

def verify_answer(answer, sources):
    """sources: {n: text}. Returns one result per claim."""
    results = []
    for c in split_claims(answer):
        ns = list(sources)
        scores = dict(zip(ns, _entailment([(sources[n], c["text"]) for n in ns]))) if ns else {}
        scores = {n: float(s) for n, s in scores.items()}
        cited_ok = [n for n in c["cited"] if scores.get(n, 0) >= SUPPORT_MIN]
        other_ok = [n for n in scores if n not in c["cited"] and scores[n] >= SUPPORT_MIN]
        if cited_ok:
            verdict = "supported"
        elif other_ok:
            verdict = "wrong_source"       # true, but cited source doesn't say it
        else:
            verdict = "unsupported"
        results.append({"claim": c["text"], "cited": c["cited"], "verdict": verdict,
                        "better_sources": other_ok if verdict == "wrong_source" else [],
                        "scores": {n: round(s, 2) for n, s in scores.items()}})
    return results