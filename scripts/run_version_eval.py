# scripts/run_version_eval.py
from app import db, search, versions
from app.answering import dedupe, is_metadata_only

WS = "demo-workspace"
K = 4
CASES = [
    ("What is the currently approved architecture?", "v3"),
    ("What is the latest architecture for storing embeddings?", "v3"),
    ("Which architecture design is the most recent?", "v3"),
    ("How does the current architecture handle ingestion?", "v3"),
    ("In v1, what was used for retrieval?", "v1"),
    ("In version 2, how are embeddings stored?", "v2"),
    ("What does version 3 add to the architecture?", "v3"),
]

def arch_labels(rows):
    return [str(r["label"]) for r in rows if r["logical_name"] == "architecture"]

def main():
    con = db.connect()
    stale_before = stale_after = hit_before = hit_after = 0
    for q, want in CASES:
        raw = dedupe([r for r in search.vector_search(con, WS, q, 30)
                      if not is_metadata_only(r["text"])])
        before = raw[:K]
        kept, info = versions.apply(con, WS, q, raw)
        after = kept[:K]
        b, a = arch_labels(before), arch_labels(after)
        stale_before += sum(1 for x in b if x != want)
        stale_after += sum(1 for x in a if x != want)
        hit_before += want in b
        hit_after += want in a
        print(f"{q}\n   wanted {want} | before {b} | after {a} | intent {info['intent']}"
              + (f" | notes {info['notes']}" if info["notes"] else ""))
    n = len(CASES)
    print(f"\nStale-version chunks in the top {K}: {stale_before} before, {stale_after} after")
    print(f"Wanted version present in the top {K}: {hit_before}/{n} before, {hit_after}/{n} after")

if __name__ == "__main__":
    main()