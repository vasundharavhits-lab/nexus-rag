# scripts/demo_split.py
# Usage: python -m scripts.demo_split
import pathlib, re
from app import verify

paras = []
for p in sorted(pathlib.Path("data/raw").glob("*.md")):
    for para in re.split(r"\n\s*\n", p.read_text(encoding="utf-8")):
        paras.append((p.name, para.strip()))

def find(*words):
    for name, para in paras:
        low = para.lower()
        if all(w in low for w in words):
            return name, para
    return None, None

n2, s2 = find("pgvector", "redis")
n3, s3 = find("rerank", "celery")
print("Source [2] from:", n2)
print("Source [3] from:", n3)
if not s2 or not s3:
    print("\nCould not find both paragraphs in data/raw. Paste this output and I will adjust the script.")
    raise SystemExit

sources = {2: s2, 3: s3}
answer = "The system uses PostgreSQL with pgvector, Redis, a reranking stage and Celery workers [3]."

def show(title):
    print(f"\n=== {title} ===")
    for r in verify.verify_answer(answer, sources):
        print(f'{r["verdict"]:13} cited={r["cited"]} better={r["better_sources"]} '
              f'scores={r["scores"]} | {r["claim"]}')

original_split = verify.split_compound
verify.split_compound = lambda t: [t.rstrip(".!? ")]        # old behaviour: no splitting
show("BEFORE: whole sentence")
verify.split_compound = original_split
show("AFTER: split into claims")