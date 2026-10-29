# app/indexing.py
"""Turns parsed sections into searchable passages (chunks) and their vectors.

Designed for files of any size:
  * passages are saved first (keyword search works at once), then vectors are computed a few at a time and
    written as they are made. Memory stays flat, and an interrupted job continues where it stopped.
  * indexing is incremental: a file that is already indexed (with vectors from the current model) is skipped,
    so adding one file never re-embeds the others. rebuild=True forces everything again.
"""
from app import db
from app import embeddings as _emb
from app.chunking import build_chunks
from app.embeddings import embed_texts

EMBED_CHUNK = 64          # passages embedded per call, so progress can be reported on big files
VALID_STRATEGIES = ("structure", "fixed")


def _model_name():
    return _emb.EMBED_MODEL


def _count(con, version_id, strategy):
    return con.execute("SELECT count(*) AS n FROM chunks WHERE version_id=%s AND strategy=%s",
                       (version_id, strategy)).fetchone()["n"]


def _pending_sql():
    # no vector yet, or a vector from a different model (an unknown model, NULL, is trusted)
    return ("version_id=%s AND strategy=%s AND (embedding IS NULL OR "
            "(emb_model IS NOT NULL AND emb_model <> %s))")


def _pending_count(con, version_id, strategy):
    return con.execute("SELECT count(*) AS n FROM chunks WHERE " + _pending_sql(),
                       (version_id, strategy, _model_name())).fetchone()["n"]


def needs_work(con, version_id, strategies, embed):
    for strat in strategies:
        if _count(con, version_id, strat) == 0:
            return True
        if embed and _pending_count(con, version_id, strat) > 0:
            return True
    return False


def _embed_pending(con, version_id, strat, progress=None):
    total = _pending_count(con, version_id, strat)
    done = 0
    while True:
        rows = con.execute(
            "SELECT chunk_id, heading_path, text FROM chunks WHERE " + _pending_sql() +
            " ORDER BY idx LIMIT %s", (version_id, strat, _model_name(), EMBED_CHUNK)).fetchall()
        if not rows:
            break
        vectors = embed_texts([f"{r['heading_path']}\n{r['text']}" for r in rows])
        db.set_embeddings(con, [r["chunk_id"] for r in rows], vectors, _model_name())
        done += len(rows)
        if progress:
            progress(min(done, total), total)
    from app import vectorstore
    vectorstore.invalidate()


def _index_one(con, version_id, strategies, embed, rebuild, progress=None):
    sections = None
    for strat in strategies:
        if rebuild or _count(con, version_id, strat) == 0:
            if sections is None:
                sections = con.execute(
                    "SELECT heading_path, page, text FROM sections WHERE version_id=%s ORDER BY idx",
                    (version_id,)).fetchall()
            db.replace_chunks(con, version_id, strat, build_chunks(version_id, sections, strat))
        if embed:
            _embed_pending(con, version_id, strat, progress)


def _totals(con, version_ids, strategies):
    out = {}
    for strat in strategies:
        out[strat] = con.execute(
            "SELECT count(*) AS n FROM chunks WHERE strategy=%s AND version_id = ANY(%s)",
            (strat, list(version_ids))).fetchone()["n"] if version_ids else 0
    return out


def index_versions(con, version_ids, strategies=("structure",), embed=True, progress=None,
                   rebuild=False):
    """Index only the given versions (used right after an upload). progress(done, total) is optional."""
    strategies = tuple(strategies)
    skipped = 0
    for vid in version_ids:
        if not rebuild and not needs_work(con, vid, strategies, embed):
            skipped += 1
            continue
        _index_one(con, vid, strategies, embed, rebuild, progress)
    return {"versions": len(version_ids), "skipped": skipped,
            "chunks": _totals(con, version_ids, strategies), "embedded": embed}


def index_workspace(con, workspace_id, strategies=("structure",), embed=True, only_missing=False,
                    only_new=False, rebuild=False, progress=None):
    """Index every readable file of a workspace. Files that are already up to date are skipped.
    (only_missing and only_new are kept for older scripts: the behaviour is now always incremental.)"""
    versions = con.execute(
        "SELECT v.version_id FROM document_versions v "
        "JOIN documents d ON d.document_id = v.document_id "
        "WHERE d.workspace_id=%s AND v.status='ok' ORDER BY v.ingested_at", (workspace_id,)).fetchall()
    ids = [v["version_id"] for v in versions]
    return index_versions(con, ids, strategies, embed, progress, rebuild)
