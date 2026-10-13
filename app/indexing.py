# app/indexing.py
import threading
from app import db
from app.chunking import build_chunks
from app.limits import INDEX_GROUP
from app.embeddings import embed_texts

_locks, _locks_guard = {}, threading.Lock()


def workspace_lock(workspace_id):
    """One indexing run per workspace at a time (a background job and a request can overlap)."""
    with _locks_guard:
        return _locks.setdefault(workspace_id, threading.Lock())


def _already_indexed(con, version_id, strategies, embed):
    """True when this version already has chunks (and vectors, if wanted) for every strategy."""
    rows = con.execute(
        "SELECT strategy, count(*) AS n, count(embedding) AS e FROM chunks "
        "WHERE version_id=%s GROUP BY strategy", (version_id,)).fetchall()
    have = {r["strategy"]: r for r in rows}
    return all(s in have and have[s]["n"] > 0 and (not embed or have[s]["e"] == have[s]["n"])
               for s in strategies)


def index_workspace(con, workspace_id, strategies=("structure", "fixed"), embed=True,
                    only_new=False, progress=None):
    """Chunk and embed every document version. With only_new=True, versions that are already
    indexed are skipped, so adding one file does not re-embed the whole workspace.
    progress(done, total) counts passages embedded. stats["chunks"] reports what is present."""
    with workspace_lock(workspace_id):
        versions = con.execute(
            "SELECT v.version_id FROM document_versions v "
            "JOIN documents d ON d.document_id = v.document_id "
            "WHERE d.workspace_id=%s AND v.status='ok'", (workspace_id,)).fetchall()
        stats = {"versions": len(versions), "chunks": {}, "embedded": embed, "skipped": 0}
        todo = []                                         # phase 1: cut everything into passages
        for v in versions:
            if only_new and _already_indexed(con, v["version_id"], strategies, embed):
                stats["skipped"] += 1
                for strat in strategies:
                    n = con.execute("SELECT count(*) AS n FROM chunks WHERE version_id=%s "
                                    "AND strategy=%s", (v["version_id"], strat)).fetchone()["n"]
                    stats["chunks"][strat] = stats["chunks"].get(strat, 0) + n
                continue
            sections = con.execute(
                "SELECT heading_path, page, text FROM sections WHERE version_id=%s ORDER BY idx",
                (v["version_id"],)).fetchall()
            for strat in strategies:
                todo.append((v["version_id"], strat, build_chunks(v["version_id"], sections, strat)))
        total = sum(len(c) for _, _, c in todo) if embed else 0
        done = 0
        if progress:
            progress(0, total)
        for version_id, strat, chunks in todo:            # phase 2: embed and store
            vectors = None
            if embed and chunks:
                vectors = []
                for i in range(0, len(chunks), INDEX_GROUP):
                    part = chunks[i:i + INDEX_GROUP]
                    vectors += embed_texts([f'{c["heading_path"]}\n{c["text"]}' for c in part])
                    done += len(part)
                    if progress:
                        progress(done, total)
            db.replace_chunks(con, version_id, strat, chunks, vectors)
            stats["chunks"][strat] = stats["chunks"].get(strat, 0) + len(chunks)
        return stats
