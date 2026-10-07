import re
from app import db
from app.verify import _entailment

CLAIM = "Restricted documents must not appear in snippets or citations for unauthorized users."

con = db.connect()
chunks = con.execute(
    "SELECT c.idx, c.text FROM chunks c "
    "JOIN document_versions v ON v.version_id = c.version_id "
    "JOIN documents d ON d.document_id = v.document_id "
    "JOIN workspaces w ON w.workspace_id = d.workspace_id "
    "WHERE w.owner = 'vasu-test' AND v.filename = 'data_governance_policy.pdf' "
    "AND c.strategy = 'structure' ORDER BY c.idx").fetchall()

if not chunks:
    print("No chunks found for data_governance_policy.pdf under user vasu-test.")
else:
    print(len(chunks), "chunks in your PDF\n")
    print(f"{'chunk':<7}{'words':<7}{'has sentence':<14}{'raw':<8}{'one line':<10}{'best 3-sentence window'}")
    for c in chunks:
        raw = c["text"]
        flat = " ".join(raw.split())
        sents = re.split(r"(?<=[.!?])\s+", flat)
        wins = [" ".join(sents[i:i + 3]) for i in range(max(1, len(sents) - 2))]
        s_raw = float(_entailment([(raw, CLAIM)])[0])
        s_flat = float(_entailment([(flat, CLAIM)])[0])
        s_win = float(max(_entailment([(w, CLAIM) for w in wins])))
        has = "Restricted documents must not appear" in flat
        print(f"{c['idx']:<7}{len(flat.split()):<7}{str(has):<14}{s_raw:<8.2f}{s_flat:<10.2f}{s_win:.2f}")