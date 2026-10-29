import re
from app import db
from app.verify import _entailment

CLAIMS = [
    ("TRUE   restricted sentence",
     "Restricted documents must not appear in snippets or citations for unauthorized users."),
    ("TRUE   purpose, long as answered",
     "The document defines how organizational documents are classified, owned, approved, indexed, "
     "retained, and retired, applying to various types of documents like technical specifications, "
     "business procedures, project records, training materials, support documentation, and internal policies."),
    ("TRUE   owner sentence",
     "Every managed document should have a business owner and a classification label."),
    ("FALSE  negated",
     "Restricted documents must appear in snippets for all users."),
    ("FALSE  invented rule",
     "The policy requires every document to be encrypted."),
    ("FALSE  invented number",
     "Documents are retained for exactly seven years."),
]

con = db.connect()
row = con.execute(
    "SELECT c.text FROM chunks c "
    "JOIN document_versions v ON v.version_id = c.version_id "
    "JOIN documents d ON d.document_id = v.document_id "
    "JOIN workspaces w ON w.workspace_id = d.workspace_id "
    "WHERE w.owner = 'vasu-test' AND v.filename = 'data_governance_policy.pdf' "
    "AND c.strategy = 'structure' AND c.idx = 0 LIMIT 1").fetchone()

flat = " ".join(row["text"].split())
sents = [s for s in re.split(r"(?<=[.!?])\s+", flat) if s]
cands = sents + [sents[i] + " " + sents[i + 1] for i in range(len(sents) - 1)]
print(len(sents), "sentences,", len(cands), "windows (singles + neighbour pairs)\n")
print(f"{'whole':<7}{'best':<7}claim and winning window")

for label, claim in CLAIMS:
    whole = float(_entailment([(flat, claim)])[0])
    scores = _entailment([(c, claim) for c in cands])
    i = int(scores.argmax())
    print(f"{whole:<7.2f}{float(scores[i]):<7.2f}{label}")
    print(f"             window: {cands[i][:90]}")