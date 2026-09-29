# app/db.py
import sqlite3
from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY, logical_name TEXT);
CREATE TABLE IF NOT EXISTS document_versions (
    version_id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(document_id),
    label TEXT, filename TEXT, source_uri TEXT, file_type TEXT, size_bytes INTEGER,
    content_hash TEXT, status TEXT, error TEXT, page_count INTEGER,
    doc_status TEXT, effective_at TEXT, ingested_at TEXT, author TEXT,
    language TEXT, section_count INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS sections (
    version_id TEXT REFERENCES document_versions(version_id),
    idx INTEGER, heading_path TEXT, page INTEGER, text TEXT,
    PRIMARY KEY (version_id, idx));
CREATE TABLE IF NOT EXISTS quality_flags (
    version_id TEXT REFERENCES document_versions(version_id),
    flag_type TEXT,
    PRIMARY KEY (version_id, flag_type));
"""

VERSION_COLS = ["version_id", "document_id", "label", "filename", "source_uri",
                "file_type", "size_bytes", "content_hash", "status", "error",
                "page_count", "doc_status", "effective_at", "ingested_at",
                "author", "language", "section_count", "text"]

def connect(path=DB_PATH):
    return sqlite3.connect(path)

def init_db(con):
    con.executescript(SCHEMA)
    con.commit()

def save(con, records, sections):
    for r in records:
        con.execute("INSERT OR REPLACE INTO documents VALUES (?,?)",
                    (r["document_id"], r["logical_name"]))
        con.execute(
            f"INSERT OR REPLACE INTO document_versions ({','.join(VERSION_COLS)}) "
            f"VALUES ({','.join('?' * len(VERSION_COLS))})",
            [r[c] for c in VERSION_COLS])
    for s in sections:
        con.execute("INSERT OR REPLACE INTO sections VALUES (?,?,?,?,?)",
                    (s["version_id"], s["idx"], s["heading_path"], s["page"], s["text"]))
    con.commit()