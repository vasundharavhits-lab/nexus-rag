# app/rerank.py
from fastembed.rerank.cross_encoder import TextCrossEncoder
from app import hybrid

RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
_model = None

def get_model():
    global _model
    if _model is None:
        _model = TextCrossEncoder(model_name=RERANK_MODEL)
    return _model

def rerank_rows(query, rows, top=None):
    if not rows:
        return []
    scores = list(get_model().rerank(query, [r["text"] for r in rows]))
    order = sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)
    out = []
    for i in order:
        r = dict(rows[i])
        r["fused_score"] = r.get("score")
        r["rerank_score"] = round(float(scores[i]), 4)
        r["score"] = r["rerank_score"]
        out.append(r)
    return out[:top] if top else out

def rerank_search(con, workspace_id, query, k=5, strategy="structure", pool=10):
    candidates = hybrid.hybrid_search(con, workspace_id, query, pool, strategy)
    return rerank_rows(query, candidates, top=k)