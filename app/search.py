# app/search.py
import re
import numpy as np
from app.embeddings import embed_query

BASE = ("FROM chunks c "
        "JOIN document_versions v ON v.version_id = c.version_id "
        "JOIN documents d ON d.document_id = v.document_id ")
COLS = ("c.chunk_id, c.version_id, d.logical_name, v.label, v.filename, "
        "c.heading_path, c.page, c.text, v.doc_status, v.effective_at")

# "practice query set 15", "section 3", "step 7": a few words followed by a standalone number.
_NUM_REF = re.compile(r"((?:[A-Za-z]+\s+){1,3})(\d+)(?![\w.-])")


def numbered_phrase(query):
    """Return the exact phrase to look for when the question names a numbered item, else None."""
    m = _NUM_REF.search(query)
    return (m.group(1) + m.group(2)).strip() if m else None


def phrase_search(con, workspace_id, phrase, k=5, strategy="structure"):
    """Adjacent-words match (so 'set 15' cannot be satisfied by 'set 30'), ranked by cover density."""
    return con.execute(
        "WITH q AS (SELECT phraseto_tsquery('english', %s) AS query) "
        f"SELECT {COLS}, ts_rank_cd(c.tsv, q.query) AS score {BASE}, q "
        "WHERE d.workspace_id=%s AND c.strategy=%s AND c.tsv @@ q.query "
        "ORDER BY score DESC LIMIT %s",
        (phrase, workspace_id, strategy, k)).fetchall()


def keyword_search(con, workspace_id, query, k=5, strategy="structure"):
    phrase = numbered_phrase(query)
    if phrase:                                   # numbered reference: exact phrase first
        rows = phrase_search(con, workspace_id, phrase, k, strategy)
        if rows:                                 # nothing matched -> fall back to word matching
            return rows
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