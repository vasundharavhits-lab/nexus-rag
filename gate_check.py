# gate_check.py - shows the top search score for a few questions, so you can pick MIN_VECTOR_SCORE.
# Run from D:\nexus-rag with uvicorn STOPPED (it loads the search model itself):  python gate_check.py
from app import db, search

RELEVANT = [   # questions your documents CAN answer
    "आत्मा को शस्त्र क्यों नहीं काट सकते?",
    "What does the Gita say about the soul being unchangeable?",
    "What happens to the soul after death?",
]
UNRELATED = [  # questions your documents can NOT answer
    "What is the capital of France?",
    "How do I bake a chocolate cake?",
    "Who won the cricket world cup in 2011?",
]

con = db.connect()
row = con.execute(
    "SELECT d.workspace_id AS w, count(*) AS n FROM chunks c "
    "JOIN document_versions v ON v.version_id=c.version_id "
    "JOIN documents d ON d.document_id=v.document_id "
    "WHERE v.filename=%s AND c.embedding IS NOT NULL "
    "GROUP BY d.workspace_id ORDER BY n DESC LIMIT 1", ("279.pdf",)).fetchone()
if not row:
    raise SystemExit("279.pdf has no embedded passages. Run reindex.py first.")
ws = row["w"]
print("workspace", ws[:8], "with", row["n"], "passages\n")

def top(q):
    r = search.vector_search(con, ws, q, 1)
    return r[0]["score"] if r else 0.0

rel = [(q, top(q)) for q in RELEVANT]
unr = [(q, top(q)) for q in UNRELATED]
print("QUESTIONS THE BOOK CAN ANSWER")
for q, s in rel: print(f"  {s:.3f}  {q}")
print("QUESTIONS THE BOOK CANNOT ANSWER")
for q, s in unr: print(f"  {s:.3f}  {q}")
lo, hi = min(s for _, s in rel), max(s for _, s in unr)
print(f"\nlowest relevant = {lo:.3f}, highest unrelated = {hi:.3f}")
if lo > hi:
    print(f"Suggested MIN_VECTOR_SCORE = {(lo + hi) / 2:.2f}")
else:
    print("The scores overlap, so a threshold alone cannot separate them. Send me this output.")
