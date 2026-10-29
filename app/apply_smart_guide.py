"""Apply the Smart guide update to a NEXUS RAG project.

Usage (PowerShell, from anywhere):
    python apply_smart_guide.py D:\nexus-rag

What it does:
  1. copies guidance.py (next to this script) into <project>/app/guidance.py
  2. makes 3 small edits: main.py, chatting.py, static/chat.html
Safe to run twice: an edit that is already there is skipped.
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
ROOT = ROOT.resolve()

if not (ROOT / "app" / "main.py").exists():
    sys.exit(f"{ROOT} does not look like the project (app/main.py not found). "
             "Pass the project folder: python apply_smart_guide.py D:\\nexus-rag")

# 1. the new module
shutil.copyfile(HERE / "guidance.py", ROOT / "app" / "guidance.py")
print("[done] app/guidance.py copied")


def edit(path, old, new, marker, label):
    p = ROOT / path
    raw = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw                      # keep Windows line endings as they were
    text = raw.replace("\r\n", "\n")
    if marker in text:
        print("[ok]  ", label, "(already there)")
        return
    if old not in text:
        print("[FAIL]", label, "- expected text not found in", path)
        return
    text = text.replace(old, new, 1)
    p.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
    print("[done]", label)


# 2. the three edits
edit("app/main.py",
     'Literal["auto", "documents", "general"]',
     'Literal["auto", "documents", "general", "guidance"]',
     '"general", "guidance"', "main.py: scope guidance")

edit("app/chatting.py",
     "        return _general(con, workspace_id, user_id, message, history, scope, NOTE_GENERAL)\n",
     "        return _general(con, workspace_id, user_id, message, history, scope, NOTE_GENERAL)\n"
     "    if scope == \"guidance\":\n"
     "        from app import guidance\n"
     "        return guidance.reply(con, workspace_id, user_id, message, clean_history(history),\n"
     "                              owns_workspace(con, workspace_id, user_id), k, answer_lang)\n",
     "guidance.reply(", "chatting.py: route guidance")

edit("static/chat.html",
     '<option value="general">General chat</option>',
     '<option value="general">General chat</option>\n'
     '        <option value="guidance">Smart guide (feelings and questions, any PDF)</option>',
     'value="guidance"', "chat.html: menu option")
