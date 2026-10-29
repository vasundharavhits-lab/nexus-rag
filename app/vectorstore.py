# app/vectorstore.py
"""In-memory vector index, one per (workspace, chunking strategy).

Before, every question read every embedding of the workspace from PostgreSQL and turned it into Python
floats. That is fine for a small folder and far too slow for a big book or hundreds of files. Now the
vectors are loaded once, normalised, kept as float16 (half the memory), and searched in blocks.

* Only the chunk id and its vector are kept in memory. The text comes from the database for the few
  passages that win.
* The cache refreshes itself when documents are indexed in this process (invalidate()), and also every
  VECTOR_CACHE_TTL_S seconds, which covers indexing done by another process (e.g. reindex.py).
* Vectors from a different embedding model have a different length (or a different emb_model tag) and are
  never mixed with the current ones, so changing EMBED_MODEL can not crash a search.
"""
import threading, time
import numpy as np

from app.config import VECTOR_CACHE_TTL_S

BLOCK = 20000                    # rows scored at once (bounds the temporary float32 memory)
FETCH = 2000                     # rows read from the database at once

_lock = threading.RLock()
_generation = 0
_cache: dict = {}                # (workspace_id, strategy) -> entry


def invalidate():
    """Call after chunks or vectors changed in this process."""
    global _generation
    with _lock:
        _generation += 1


def _count(con, workspace_id, strategy):
    return con.execute(
        "SELECT count(*) AS n FROM chunks c JOIN document_versions v ON v.version_id = c.version_id "
        "JOIN documents d ON d.document_id = v.document_id "
        "WHERE d.workspace_id=%s AND c.strategy=%s AND c.embedding IS NOT NULL",
        (workspace_id, strategy)).fetchone()["n"]


def _load(con, workspace_id, strategy):
    by_dim = {}                                           # vector length -> ([ids], [arrays])
    with con.cursor(name=f"vs_{abs(hash((workspace_id, strategy))) % 10**9}") as cur:
        cur.itersize = FETCH
        cur.execute(
            "SELECT c.chunk_id, c.embedding, c.emb_model FROM chunks c "
            "JOIN document_versions v ON v.version_id = c.version_id "
            "JOIN documents d ON d.document_id = v.document_id "
            "WHERE d.workspace_id=%s AND c.strategy=%s AND c.embedding IS NOT NULL",
            (workspace_id, strategy))
        for r in cur:
            vec = r["embedding"]
            if not vec:
                continue
            ids, arrs = by_dim.setdefault((len(vec), r["emb_model"]), ([], []))
            ids.append(r["chunk_id"])
            arrs.append(np.asarray(vec, dtype=np.float32))
    groups = {}
    for key, (ids, arrs) in by_dim.items():
        m = np.vstack(arrs)
        m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-12
        groups[key] = (ids, m.astype(np.float16))
    return groups


def _entry(con, workspace_id, strategy):
    key = (workspace_id, strategy)
    now = time.monotonic()
    with _lock:
        e = _cache.get(key)
        fresh = e and e["gen"] == _generation and now - e["at"] < VECTOR_CACHE_TTL_S
        if fresh:
            return e
        n = _count(con, workspace_id, strategy)
        if e and e["gen"] == _generation and e["n"] == n:
            e["at"] = now                                  # nothing changed: keep what we have
            return e
        groups = _load(con, workspace_id, strategy)
        con.rollback()                                     # end the read transaction used by the cursor
        e = {"gen": _generation, "at": now, "n": n, "groups": groups}
        _cache[key] = e
        return e


def _pick_group(groups, dim, model):
    """Vectors of the right length, preferring the ones tagged with the current embedding model."""
    same = [(k, v) for k, v in groups.items() if k[0] == dim]
    if not same:
        return None
    tagged = [kv for kv in same if kv[0][1] == model]
    pool = tagged or [kv for kv in same if kv[0][1] is None] or same
    ids = [i for _, (g_ids, _) in pool for i in g_ids]
    mats = [m for _, (_, m) in pool]
    return ids, (mats[0] if len(mats) == 1 else np.vstack(mats))


def top_k(con, workspace_id, query_vec, k, strategy="structure", model=None):
    """[(chunk_id, cosine_score)] best first. [] when nothing is indexed (or only with another model)."""
    e = _entry(con, workspace_id, strategy)
    q = np.asarray(query_vec, dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-12
    picked = _pick_group(e["groups"], len(q), model)
    if not picked:
        return []
    ids, mat = picked
    scores = np.empty(len(ids), dtype=np.float32)
    for s in range(0, len(ids), BLOCK):
        scores[s:s + BLOCK] = mat[s:s + BLOCK].astype(np.float32) @ q
    k = min(k, len(ids))
    if k <= 0:
        return []
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [(ids[i], float(scores[i])) for i in idx]


def stale_summary(con, workspace_id, strategy="structure", model=None, dim=None):
    """How many passages exist, and how many have no usable vector (missing, or from another model)."""
    total = con.execute(
        "SELECT count(*) AS n FROM chunks c JOIN document_versions v ON v.version_id = c.version_id "
        "JOIN documents d ON d.document_id = v.document_id WHERE d.workspace_id=%s AND c.strategy=%s",
        (workspace_id, strategy)).fetchone()["n"]
    e = _entry(con, workspace_id, strategy)
    usable = 0
    for (d, m), (ids, _mat) in e["groups"].items():
        if (dim is None or d == dim) and (m is None or model is None or m == model):
            usable += len(ids)
    return {"passages": total, "searchable": usable, "needs_reindex": max(0, total - usable)}


def has_vectors(con, workspace_id, strategy="structure"):
    return any(len(ids) for ids, _m in _entry(con, workspace_id, strategy)["groups"].values())
