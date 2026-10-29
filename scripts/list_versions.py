# scripts/list_versions.py
from app import db

def main():
    con = db.connect()
    rows = con.execute(
        "SELECT d.logical_name, v.label, v.filename, v.doc_status, v.effective_at "
        "FROM document_versions v JOIN documents d USING (document_id) "
        "WHERE d.workspace_id = %s ORDER BY d.logical_name, v.label",
        ("demo-workspace",)).fetchall()
    print(f"{'document':<20}{'label':<8}{'file':<30}{'status':<12}{'date'}")
    for r in rows:
        print(f"{r['logical_name']:<20}{str(r['label']):<8}{r['filename']:<30}"
              f"{str(r['doc_status']):<12}{r['effective_at']}")

if __name__ == "__main__":
    main()