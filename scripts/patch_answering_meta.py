"""One-time edit: pass each source's version label and status to the claim checker.
Stops without changing anything if answering.py does not look exactly as expected."""
import re, shutil, sys, ast
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "app/answering.py")
raw = path.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
text = raw.replace("\r\n", "\n")

OLD = re.compile(r'verify\.verify_answer\(\s*answer,\s*\{e\["n"\]: e\["text"\] for e in evidence\}\s*\)')
NEW = ('verify.verify_answer(\n'
       '                answer, {e["n"]: e["text"] for e in evidence},\n'
       '                {e["n"]: {"label": e.get("label"), "status": e.get("doc_status")}\n'
       '                 for e in evidence})')

i = text.find("verify.verify_answer(")
if i != -1 and '"status": e.get("doc_status")' in text[i:i + 400]:
    print("Already patched - nothing to do."); sys.exit(0)
hits = OLD.findall(text)
if len(hits) != 1:
    print(f"STOPPED: expected exactly 1 matching verify_answer call, found {len(hits)}. "
          "answering.py was not changed. Send me the lines around 'verify.verify_answer'.")
    sys.exit(1)
out = OLD.sub(lambda m: NEW, text)
ast.parse(out)                                   # never write a file that does not parse
shutil.copyfile(path, str(path) + ".bak2")
path.write_bytes((out.replace("\n", "\r\n") if crlf else out).encode("utf-8"))
print(f"Patched {path} (backup: {path}.bak2). Restart uvicorn and run: python -m pytest -q")