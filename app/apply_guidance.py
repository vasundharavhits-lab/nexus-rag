"""Adds Gita guidance mode to NEXUS RAG. Run from the project folder (the one that contains app\\ and static\\):

    python apply_guidance.py

It backs up each file it changes (name.bak_guidance), keeps your line endings, and is safe to run twice.
If an edit cannot be applied because your file looks different, it tells you which one and what to type by hand.
"""
import shutil, sys
from pathlib import Path

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent


def edit(path, old, new, label, marker):
    p = ROOT / path
    if not p.exists():
        print(f"[skip] {path} not found. Run this from the project folder."); return False
    raw = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    if marker in text:
        print(f"[ok]   {label}: already applied"); return True
    if old not in text:
        print(f"[FAIL] {label}: expected text not found in {path}. Make this change by hand (see the instructions)."); return False
    shutil.copy2(p, str(p) + ".bak_guidance")
    text = text.replace(old, new, 1)
    if crlf:
        text = text.replace("\n", "\r\n")
    p.write_bytes(text.encode("utf-8"))
    print(f"[done] {label}"); return True


results = []

# 1. the new module
src, dst = HERE / "guidance.py", ROOT / "app" / "guidance.py"
if not (ROOT / "app").exists():
    sys.exit("Run this from the project folder (it must contain the app folder).")
shutil.copy2(src, dst)
print("[done] app/guidance.py copied")

# 2. the API accepts the new scope
results.append(edit("app/main.py",
    'Literal["auto", "documents", "general"]',
    'Literal["auto", "documents", "general", "guidance"]',
    "main.py: allow scope 'guidance'", '"general", "guidance"'))

# 3. the chat router sends that scope to the new module
results.append(edit("app/chatting.py",
    "        return _general(con, workspace_id, user_id, message, history, scope, NOTE_GENERAL)\n",
    "        return _general(con, workspace_id, user_id, message, history, scope, NOTE_GENERAL)\n"
    "    if scope == \"guidance\":\n"
    "        from app import guidance\n"
    "        return guidance.reply(con, workspace_id, user_id, message, clean_history(history),\n"
    "                              owns_workspace(con, workspace_id, user_id), k, answer_lang)\n",
    "chatting.py: route scope 'guidance'", "guidance.reply("))

# 4. the page gets a new choice in the 'Answer from' menu
results.append(edit("static/chat.html",
    '<option value="general">General chat</option>',
    '<option value="general">General chat</option>\n        <option value="guidance">Smart guide (feelings and questions, any PDF)</option>',
    "chat.html: add the menu option", 'value="guidance"'))

print()
print("All set. Restart the server (Ctrl+C, then uvicorn again) and refresh the page." if all(results)
      else "Some edits failed. Send me the [FAIL] lines.")
