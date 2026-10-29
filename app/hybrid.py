# app/hybrid.py
from app import search

RRF_K = 60

def rrf(rankings, top=None):
    fused = {}
    for name, rows in rankings:
        for rank, row in enumerate(rows, 1):
            entry = fused.setdefault(row["chunk_id"], {"row": dict(row), "score": 0.0, "ranks": {}})
            entry["score"] += 1.0 / (RRF_K + rank)
            entry["ranks"][name] = rank
            if name == "vector":
                entry["row"]["vector_score"] = row["score"]
    out = []
    for e in sorted(fused.values(), key=lambda e: e["score"], reverse=True):
        r = e["row"]
        r["score"] = round(e["score"], 5)
        r["ranks"] = e["ranks"]
        out.append(r)
    return out[:top] if top else out

def hybrid_search(con, workspace_id, query, k=5, strategy="structure", pool=20):
    kw = search.keyword_search(con, workspace_id, query, pool, strategy)
    vec = search.vector_search(con, workspace_id, query, pool, strategy)
    return rrf([("keyword", kw), ("vector", vec)], top=k)