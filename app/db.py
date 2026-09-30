import psycopg
from psycopg.rows import dict_row
from app.config import DATABASE_URL
from psycopg.types.json import Jsonb

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    access_policy TEXT NOT NULL DEFAULT 'private',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    logical_name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS document_versions (
    version_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    label TEXT, filename TEXT, source_uri TEXT, file_type TEXT, size_bytes BIGINT,
    content_hash TEXT, status TEXT, error TEXT, page_count INTEGER,
    doc_status TEXT, effective_at TEXT, ingested_at TIMESTAMPTZ, author TEXT,
    language TEXT, section_count INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS sections (
    version_id TEXT REFERENCES document_versions(version_id),
    idx INTEGER, heading_path TEXT, page INTEGER, text TEXT,
    PRIMARY KEY (version_id, idx));
CREATE TABLE IF NOT EXISTS quality_flags (
    version_id TEXT REFERENCES document_versions(version_id),
    flag_type TEXT,
    PRIMARY KEY (version_id, flag_type));
CREATE INDEX IF NOT EXISTS idx_docs_ws ON documents(workspace_id);
CREATE INDEX IF NOT EXISTS idx_versions_doc ON document_versions(document_id);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    strategy TEXT NOT NULL,
    idx INTEGER NOT NULL,
    heading_path TEXT, page INTEGER,
    text TEXT NOT NULL,
    word_count INTEGER,
    embedding REAL[],
    tsv tsvector GENERATED ALWAYS AS
        (to_tsvector('english', coalesce(heading_path, '') || ' ' || text)) STORED);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_version ON chunks(version_id);
CREATE TABLE IF NOT EXISTS query_runs (
    run_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    mode TEXT, k INTEGER,
    status TEXT NOT NULL,
    answer TEXT,
    model TEXT,
    evidence JSONB,
    timings JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_runs_ws ON query_runs(workspace_id);
"""

VERSION_COLS = ["version_id", "document_id", "label", "filename", "source_uri",
                "file_type", "size_bytes", "content_hash", "status", "error",
                "page_count", "doc_status", "effective_at", "ingested_at",
                "author", "language", "section_count", "text"]

def connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db(con):
    con.execute(SCHEMA)
    con.commit()

def _clean(v):
    return v.replace("\x00", "") if isinstance(v, str) else v   # Postgres rejects NUL

def save(con, workspace_id, records, sections):
    update_set = ", ".join(f"{c}=EXCLUDED.{c}" for c in VERSION_COLS if c != "version_id")
    with con.cursor() as cur:
        for r in records:
            cur.execute(
                "INSERT INTO documents (document_id, workspace_id, logical_name) "
                "VALUES (%s,%s,%s) ON CONFLICT (document_id) DO NOTHING",
                (r["document_id"], workspace_id, r["logical_name"]))
            cur.execute(
                f"INSERT INTO document_versions ({','.join(VERSION_COLS)}) "
                f"VALUES ({','.join(['%s'] * len(VERSION_COLS))}) "
                f"ON CONFLICT (version_id) DO UPDATE SET {update_set}",
                [_clean(r[c]) for c in VERSION_COLS])
        for s in sections:
            cur.execute(
                "INSERT INTO sections (version_id, idx, heading_path, page, text) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (version_id, idx) DO UPDATE "
                "SET heading_path=EXCLUDED.heading_path, page=EXCLUDED.page, text=EXCLUDED.text",
                (s["version_id"], s["idx"], _clean(s["heading_path"]), s["page"], _clean(s["text"])))
    con.commit()

def replace_chunks(con, version_id, strategy, chunks, vectors=None):
    """Delete and re-insert, so re-indexing is idempotent (same result every run)."""
    with con.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE version_id=%s AND strategy=%s",
                    (version_id, strategy))
        for i, c in enumerate(chunks):
            cur.execute(
                "INSERT INTO chunks (chunk_id, version_id, strategy, idx, heading_path, "
                "page, text, word_count, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (c["chunk_id"], version_id, strategy, c["idx"], _clean(c["heading_path"]),
                 c["page"], _clean(c["text"]), c["word_count"],
                 vectors[i] if vectors else None))
    con.commit()

def save_run(con, run):
    con.execute(
        "INSERT INTO query_runs (run_id, workspace_id, user_id, query, mode, k, status, "
        "answer, model, evidence, timings) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (run["run_id"], run["workspace_id"], run["user_id"], run["query"], run["mode"],
         run["k"], run["status"], _clean(run["answer"]), run["model"],
         Jsonb(run["evidence"]), Jsonb(run["timings"])))
    con.commit()