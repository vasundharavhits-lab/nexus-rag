# app/versions.py
import re

CURRENT = re.compile(r"\b(current(ly)?|latest|newest|most recent|up[- ]to[- ]date|now)\b", re.I)
NAMED = re.compile(r"\b(?:v|version\s*)(\d+)\b", re.I)

STATUS_RANK = {"approved": 2, "draft": 0, "superseded": -1,
               "deprecated": -1, "archived": -1, "obsolete": -1}

def intent(question):
    m = NAMED.search(question)
    if m:
        return "named", f"v{m.group(1)}"
    if CURRENT.search(question):
        return "current", None
    return "none", None

def _label_num(label):
    m = re.search(r"\d+", str(label or ""))
    return int(m.group()) if m else 0

def currency_key(v):
    status = (v.get("doc_status") or "").strip().lower()
    return (STATUS_RANK.get(status, 1), str(v.get("effective_at") or ""),
            _label_num(v.get("label")))

def load_versions(con, workspace_id):
    rows = con.execute(
        "SELECT d.logical_name, v.version_id, v.label, v.doc_status, v.effective_at "
        "FROM document_versions v JOIN documents d USING (document_id) "
        "WHERE d.workspace_id = %s", (workspace_id,)).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["logical_name"], []).append(r)
    return out

def apply(con, workspace_id, question, rows):
    kind, named = intent(question)
    info = {"intent": kind, "named": named, "dropped": [], "notes": []}
    if kind == "none" or not rows:
        return rows, info

    target = {}
    for name, group in load_versions(con, workspace_id).items():
        if len(group) < 2:
            continue
        present = {r["version_id"] for r in rows if r["logical_name"] == name}
        if not present:
            continue
        if kind == "current":
            best = max(group, key=currency_key)
        else:
            matches = [v for v in group if str(v["label"]).lower() == named]
            if not matches:
                info["notes"].append(f"{name}: no version {named}")
                continue
            best = matches[0]
        if best["version_id"] in present:
            target[name] = best["version_id"]
        else:
            info["notes"].append(
                f"{name}: wanted {best['label']} but none of its chunks were retrieved")

    out = []
    for r in rows:
        want = target.get(r["logical_name"])
        if want and r["version_id"] != want:
            if r["filename"] not in info["dropped"]:
                info["dropped"].append(r["filename"])
            continue
        out.append(r)
    return out, info