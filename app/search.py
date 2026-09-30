# app/search.py
import numpy as np
from app.embeddings import embed_query

BASE = ("FROM chunks c "
        "JOIN document_versions v ON v.version_id = c.version_id "
        "JOIN documents d ON d.document_id = v.document_id ")
COLS = ("c.chunk_id, c.version_id, d.logical_name, v.label, v.filename, "
        "c.heading_path, c.page, c.text, v.doc_status, v.effective_at")

def keyword_search(con, workspace_id, query, k=5, strategy="structure"):
    return con.execute(
        "WITH q AS (SELECT replace(plainto_tsquery('english', %s)::text, '&', '|')"
        "::tsquery AS query) "
        f"SELECT {COLS}, ts_rank(c.tsv, q.query) AS score {BASE}, q "
        "WHERE d.workspace_id=%s AND c.strategy=%s AND c.tsv @@ q.query "
        "ORDER BY score DESC LIMIT %s",
        (query, workspace_id, strategy, k)).fetchall()

def vector_search(con, workspace_id, query, k=5, strategy="structure"):
    rows = con.execute(
        f"SELECT {COLS}, c.embedding {BASE} "
        "WHERE d.workspace_id=%s AND c.strategy=%s AND c.embedding IS NOT NULL",
        (workspace_id, strategy)).fetchall()
    if not rows:
        return []
    m = np.array([r["embedding"] for r in rows], dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-12
    q = np.array(embed_query(query), dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-12
    scores = m @ q
    results = []
    for i in np.argsort(-scores)[:k]:
        r = dict(rows[i]); r.pop("embedding")
        r["score"] = float(scores[i])
        results.append(r)
    return results