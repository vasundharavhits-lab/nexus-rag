import psycopg                              #- It allows your Python code to run SQL queries.,PostgreSQL connection.
from psycopg.rows import dict_row           #- It makes database results come as Python dictionaries instead of tuples.
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
    emb_model TEXT,
    tsv tsvector GENERATED ALWAYS AS
        (to_tsvector('simple', coalesce(heading_path, '') || ' ' || text)) STORED);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_version ON chunks(version_id);
CREATE INDEX IF NOT EXISTS idx_chunks_version_strategy ON chunks(version_id, strategy, idx);
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

def _migrate(con):
    """Bring a database created by an older version up to date. Safe to run every start."""
    con.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS emb_model TEXT")
    # Older databases index keywords with the 'english' configuration, which cannot search other languages.
    row = con.execute(
        "SELECT pg_get_expr(d.adbin, d.adrelid) AS expr FROM pg_attrdef d "
        "JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum "
        "WHERE d.adrelid = 'chunks'::regclass AND a.attname = 'tsv'").fetchone()
    if row and "'english'" in (row["expr"] or ""):
        con.execute("DROP INDEX IF EXISTS idx_chunks_tsv")
        con.execute("ALTER TABLE chunks DROP COLUMN tsv")
        con.execute("ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS "
                    "(to_tsvector('simple', coalesce(heading_path, '') || ' ' || text)) STORED")
        con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN (tsv)")


def init_db(con):
    con.execute(SCHEMA)
    _migrate(con)
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

def replace_chunks(con, version_id, strategy, chunks, vectors=None, emb_model=None):
    """Delete and re-insert, so re-indexing is idempotent (same result every run). Rows are inserted in
    batches, which keeps a book with thousands of passages fast."""
    from app import vectorstore
    rows = [(c["chunk_id"], version_id, strategy, c["idx"], _clean(c["heading_path"]), c["page"],
             _clean(c["text"]), c["word_count"], vectors[i] if vectors else None,
             emb_model if vectors else None) for i, c in enumerate(chunks)]
    with con.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE version_id=%s AND strategy=%s", (version_id, strategy))
        for start in range(0, len(rows), 500):
            cur.executemany(
                "INSERT INTO chunks (chunk_id, version_id, strategy, idx, heading_path, "
                "page, text, word_count, embedding, emb_model) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                rows[start:start + 500])
    con.commit()
    vectorstore.invalidate()

def set_embeddings(con, chunk_ids, vectors, emb_model):
    """Store the vectors of already saved passages (a few at a time, so memory stays flat on big files)."""
    with con.cursor() as cur:
        cur.executemany("UPDATE chunks SET embedding=%s, emb_model=%s WHERE chunk_id=%s",
                        [(v, emb_model, cid) for cid, v in zip(chunk_ids, vectors)])
    con.commit()

def save_run(con, run):
    con.execute(
        "INSERT INTO query_runs (run_id, workspace_id, user_id, query, mode, k, status, "
        "answer, model, evidence, timings) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (run["run_id"], run["workspace_id"], run["user_id"], run["query"], run["mode"],
         run["k"], run["status"], _clean(run["answer"]), run["model"],
         Jsonb(run["evidence"]), Jsonb(run["timings"])))
    con.commit()