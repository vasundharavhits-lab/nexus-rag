# reindex.py - run once from D:\nexus-rag after changing EMBED_MODEL in .env
# Re-embeds every document with the new model. Stop uvicorn before running it.
import time
from app import db, indexing

con = db.connect()
n = con.execute("SELECT count(*) AS n FROM chunks WHERE text LIKE %s", ("%\u0936\u0938\u094d\u0924\u094d\u0930\u093e\u0926\u093f%",)).fetchone()["n"]
print("passages containing the verse word 'shastradi':", n)
con.execute("UPDATE chunks SET embedding = NULL")
con.commit()
for r in con.execute("SELECT workspace_id FROM workspaces").fetchall():
    wid, t0, last = r["workspace_id"], time.time(), [0]

    def prog(done, total):
        if done - last[0] >= 50 or done == total:
            print(f"  {wid[:8]}: {done}/{total} passages", flush=True)
            last[0] = done

    stats = indexing.index_workspace(con, wid, strategies=("structure",), embed=True,
                                     only_new=True, progress=prog)
    print(wid[:8], stats["chunks"], round(time.time() - t0), "s")
print("done")
