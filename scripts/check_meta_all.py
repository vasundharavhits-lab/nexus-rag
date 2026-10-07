import random, re, time
from app import db
from app.answering import is_metadata_only
from app.verify import _entailment, SUPPORT_MIN

WS = "demo-workspace"
MAX_SENTENCES = 60
META = re.compile(r"^\s*(status|date|version|author)\s*:", re.I)

def lower_first(s):
    return s[0].lower() + s[1:]

def score(pairs, label):
    out, t0 = [], time.time()
    for i in range(0, len(pairs), 20):
        out += [float(x) for x in _entailment(pairs[i:i + 20])]
        print(f"  {label}: {len(out)}/{len(pairs)} scored, {time.time() - t0:.0f} s", flush=True)
    return out

con = db.connect()
rows = con.execute(
    "SELECT c.text, v.filename, v.label, v.doc_status, v.effective_at "
    "FROM chunks c JOIN document_versions v ON v.version_id = c.version_id "
    "JOIN documents d ON d.document_id = v.document_id "
    "WHERE d.workspace_id = %s AND c.strategy = 'structure' AND v.status = 'ok'",
    (WS,)).fetchall()
print(len(rows), "chunks read from", WS, flush=True)

groups = []
for r in rows:
    if is_metadata_only(r["text"]):
        continue
    flat = " ".join(r["text"].split())
    status = r["doc_status"]
    prefix = (f"Document {r['filename']}, version {r['label']}, status {status or 'unknown'}, "
              f"date {r['effective_at'] or 'unknown'}. ")
    for s in re.split(r"(?<=[.!?])\s+", flat):
        s = s.strip()
        if len(s.split()) < 4 or META.match(s):
            continue
        body = lower_first(s.rstrip(".!?"))
        other = "v2" if r["label"] == "v1" else "v1"
        g = [("version", "true", f"According to {r['label']}, {body}.", r["text"], prefix + r["text"]),
             ("version", "false", f"According to {other}, {body}.", r["text"], prefix + r["text"])]
        if status in ("Draft", "Approved"):
            opp = "Approved" if status == "Draft" else "Draft"
            g.append(("status", "true", f"According to the {status.lower()} document, {body}.", r["text"], prefix + r["text"]))
            g.append(("status", "false", f"According to the {opp.lower()} document, {body}.", r["text"], prefix + r["text"]))
        groups.append(g)

if not groups:
    print("No sentences found. Is demo-workspace indexed? Run: python -m scripts.build_index")
    raise SystemExit
if len(groups) > MAX_SENTENCES:
    groups = random.Random(1).sample(groups, MAX_SENTENCES)
cases = [c for g in groups for c in g]
print(f"{len(cases)} claims from {len(groups)} sentences, cut-off {SUPPORT_MIN}\n", flush=True)

s_text = score([(c[3], c[2]) for c in cases], "text only")
s_meta = score([(c[4], c[2]) for c in cases], "+metadata")

print(f"\n{'variant':<9}{'claims':<8}{'n':<5}{'>=cut text only':<17}{'>=cut +metadata':<17}{'max +metadata'}")
for variant in ("version", "status"):
    for kind in ("true", "false"):
        idx = [i for i, c in enumerate(cases) if c[0] == variant and c[1] == kind]
        if not idx:
            continue
        a = [s_text[i] for i in idx]
        b = [s_meta[i] for i in idx]
        print(f"{variant:<9}{kind:<8}{len(idx):<5}"
              f"{sum(x >= SUPPORT_MIN for x in a) / len(a):<17.0%}"
              f"{sum(x >= SUPPORT_MIN for x in b) / len(b):<17.0%}{max(b):.2f}")

print("\nFalse claims scoring 0.30 or more with the metadata sentence:")
shown = 0
for i, c in enumerate(cases):
    if c[1] == "false" and s_meta[i] >= 0.30:
        print(f"  {s_meta[i]:.2f}  {c[2][:100]}")
        shown += 1
if not shown:
    print("  none")