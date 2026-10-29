from app import db
con = db.connect()
names = ["architecture_v2.pdf", "architecture_v3.pdf", "Reviewing shared chat conversation.pdf"]
rows = con.execute(
    "SELECT v.filename, v.ingested_at, v.size_bytes, v.page_count FROM document_versions v "
    "JOIN documents d USING (document_id) "
    "WHERE d.workspace_id = 'demo-workspace' AND v.filename = ANY(%s) ORDER BY v.ingested_at",
    (names,)).fetchall()
for r in rows:
    print(f"{r['ingested_at']:%Y-%m-%d %H:%M}  {r['size_bytes']:>8} bytes  {r['page_count']} pages  {r['filename']}")
