from app import db
from app.verify import _entailment

con = db.connect()
rows = con.execute(
    "SELECT c.text, v.filename, v.label, v.doc_status, v.effective_at "
    "FROM chunks c JOIN document_versions v ON v.version_id = c.version_id "
    "JOIN documents d ON d.document_id = v.document_id "
    "WHERE d.workspace_id = 'demo-workspace' AND v.filename = 'architecture_v1.md' "
    "AND c.strategy = 'structure'").fetchall()
row = next(r for r in rows if "keyword search only" in r["text"].lower())

text = row["text"]
prefix = (f"Document {row['filename']}, version {row['label']}, "
          f"status {row['doc_status']}, date {row['effective_at']}. ")
PREMISES = [text, prefix + text]

CLAIMS = [
    ("TRUE   as answered", "The draft uses keyword relevance matching for search."),
    ("TRUE   plain", "The draft uses keyword search only."),
    ("TRUE   monolith", "The draft is a monolithic FastAPI service."),
    ("FALSE  vector", "The draft uses vector search."),
    ("FALSE  wrong status", "The approved version uses keyword search only."),
]

print("metadata sentence:", repr(prefix))
print(f"\n{'text only':<11}{'+metadata':<11}claim")
for label, claim in CLAIMS:
    s = [float(_entailment([(p, claim)])[0]) for p in PREMISES]
    print(f"{s[0]:<11.2f}{s[1]:<11.2f}{label}  {claim}")