# scripts/show_chunk.py
import sys
from app import db

def main():
    cid = sys.argv[1]
    con = db.connect()
    row = con.execute(
        "SELECT c.text, v.filename, v.label, v.doc_status, v.effective_at "
        "FROM chunks c JOIN document_versions v ON v.version_id = c.version_id "
        "WHERE c.chunk_id = %s", (cid,)).fetchone()
    if not row:
        print("No chunk with that id")
        return
    print(f"{row['filename']} | {row['label']} | {row['doc_status']} | {row['effective_at']}")
    print("-" * 60)
    print(row["text"])

if __name__ == "__main__":
    main()