from app import db
con = db.connect()
rows = con.execute("SELECT created_at, status, query FROM query_runs WHERE workspace_id = 'demo-workspace' ORDER BY created_at DESC LIMIT 10").fetchall()
for r in rows:
    print(r["created_at"], r["status"], r["query"])
