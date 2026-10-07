# scripts/remove_docs.py
import sys
from app import db
from app.config import UPLOAD_DIR

WS = "demo-workspace"
NAMES = ["architecture_v1.md", "architecture_v2.md", "architecture_v3.md", "broken_report.pdf", "decisions.md", "decisions_copy.md", "empty_notes.md", "incident_log.md", "meeting_2026_03.md", "meeting_2026_03_final.md", "requirements_v2.docx", "short_note.md", "test_report_v1.pdf"]  # files to KEEP

def main():
    go = "--yes" in sys.argv
    con = db.connect()
    rows = con.execute(
        "SELECT v.version_id, v.filename, v.content_hash, v.file_type, v.ingested_at "
        "FROM document_versions v JOIN documents d USING (document_id) "
        "WHERE d.workspace_id = %s AND NOT (v.filename = ANY(%s)) ORDER BY v.ingested_at",
        (WS, NAMES)).fetchall()
    if not rows:
        print("Nothing to remove.")
        return
    print("Removing:" if go else "Would remove:")
    for r in rows:
        print(f"  {r['ingested_at']:%Y-%m-%d %H:%M}  {r['filename']}")
    if not go:
        print("\nNothing was deleted. Run again with --yes to delete.")
        return
    ids = [r["version_id"] for r in rows]
    for t in ("chunks", "sections", "quality_flags"):
        con.execute(f"DELETE FROM {t} WHERE version_id = ANY(%s)", (ids,))
    con.execute("DELETE FROM document_versions WHERE version_id = ANY(%s)", (ids,))
    con.execute(
        "DELETE FROM documents d WHERE d.workspace_id = %s AND NOT EXISTS "
        "(SELECT 1 FROM document_versions v WHERE v.document_id = d.document_id)", (WS,))
    con.commit()
    for r in rows:
        left = con.execute(
            "SELECT 1 FROM document_versions v JOIN documents d USING (document_id) "
            "WHERE d.workspace_id = %s AND v.content_hash = %s LIMIT 1",
            (WS, r["content_hash"])).fetchone()
        f = UPLOAD_DIR / WS / f"{r['content_hash']}.{r['file_type']}"
        if not left and f.exists():
            f.unlink()
    print("Done.")

if __name__ == "__main__":
    main()
