# app/verify.py
import re
import numpy as np

MODEL_NAME = "cross-encoder/nli-deberta-v3-small"
ENTAIL = 1          # label order: contradiction, entailment, neutral
SUPPORT_MIN = 0.5   # entailment probability needed to call a claim supported

_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder
        _model = CrossEncoder(MODEL_NAME)
    return _model

def split_claims(answer):
    """Split an answer into sentences, with citation markers removed, plus the cited numbers."""
    parts = re.split(r"(?<=[.!?])\s+", answer.strip())
    out = []
    for p in parts:
        cited = sorted({int(x) for g in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", p)
                        for x in g.split(",")})
        text = re.sub(r"\s*\[\d+(?:\s*,\s*\d+)*\]", "", p).strip()
        if len(text.split()) >= 3:
            out.append({"text": text, "cited": cited})
    return out

def _entailment(pairs):
    logits = get_model().predict(pairs)
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return (e / e.sum(axis=1, keepdims=True))[:, ENTAIL]

def verify_answer(answer, sources):
    """sources: {n: text}. Returns one result per sentence."""
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