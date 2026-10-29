import base64, json, re, sys, zlib
from pathlib import Path

if len(sys.argv) != 3:
    sys.exit("Usage: python smart_guide_from_notebook.py <notebook.ipynb> <project folder>")
nb_path, root = Path(sys.argv[1]), Path(sys.argv[2])
if not (root / "app" / "main.py").exists():
    sys.exit("app/main.py not found in " + str(root))

nb = json.load(open(nb_path, encoding="utf-8"))
src = next("".join(c["source"]) for c in nb["cells"] if "zlib.decompress" in "".join(c["source"]))
block = re.search(r"B = \((.*?)\n\)", src, re.S).group(1)
data = zlib.decompress(base64.b64decode("".join(re.findall(r'"([^"]*)"', block))))
(root / "app" / "guidance.py").write_bytes(data)
print("[done] app/guidance.py written,", len(data), "bytes")


def edit(path, old, new, marker, label):
    p = root / path
    raw = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    if marker in text:
        print("[ok]  ", label, "(already there)"); return
    if old not in text:
        print("[FAIL]", label, "- expected text not found in", path); return
    text = text.replace(old, new, 1)
    p.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
    print("[done]", label)


edit("app/main.py",
     'Literal["auto", "documents", "general"]',
     'Literal["auto", "documents", "general", "guidance"]',
     '"general", "guidance"', "main.py")
edit("app/chatting.py",
     "        return _general(con, workspace_id, user_id, message, history, scope, NOTE_GENERAL)\n",
     "        return _general(con, workspace_id, user_id, message, history, scope, NOTE_GENERAL)\n"
     "    if scope == \"guidance\":\n"
     "        from app import guidance\n"
     "        return guidance.reply(con, workspace_id, user_id, message, clean_history(history),\n"
     "                              owns_workspace(con, workspace_id, user_id), k, answer_lang)\n",
     "guidance.reply(", "chatting.py")
edit("static/chat.html",
     '<option value="general">General chat</option>',
     '<option value="general">General chat</option>\n'
     '        <option value="guidance">Smart guide (feelings and questions, any PDF)</option>',
     'value="guidance"', "chat.html")
