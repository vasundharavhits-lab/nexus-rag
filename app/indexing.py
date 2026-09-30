# app/indexing.py
from app import db
from app.chunking import build_chunks
from app.embeddings import embed_texts

def index_workspace(con, workspace_id, strategies=("structure", "fixed"), embed=True):
    versions = con.execute(
        "SELECT v.version_id FROM document_versions v "
        "JOIN documents d ON d.document_id = v.document_id "
        "WHERE d.workspace_id=%s AND v.status='ok'", (workspace_id,)).fetchall()
    stats = {"versions": len(versions), "chunks": {}, "embedded": embed}
    for v in versions:
        sections = con.execute(
            "SELECT heading_path, page, text FROM sections WHERE version_id=%s ORDER BY idx",
            (v["version_id"],)).fetchall()
        for strat in strategies:
            chunks = build_chunks(v["version_id"], sections, strat)
            vectors = None
            if embed and chunks:
                vectors = embed_texts([f'{c["heading_path"]}\n{c["text"]}' for c in chunks])
            db.replace_chunks(con, v["version_id"], strat, chunks, vectors)
            stats["chunks"][strat] = stats["chunks"].get(strat, 0) + len(chunks)
    return stats