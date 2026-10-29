from app import db, search

WS = "demo-workspace"
QUESTIONS = [
    "What is the currently approved architecture?",
    "Which decision introduced vector search, and why?",
    "How do we avoid running a separate database?",
    "pgvector",
    "ingestion quality report",
]

def show(rows):
    for r in rows[:3]:
        print(f'   {r["score"]:.3f}  {r["filename"]} > {r["heading_path"]}')
    if not rows:
        print("   (no results)")

def main():
    con = db.connect()
    for q in QUESTIONS:
        print(f"\nQ: {q}")
        print(" keyword:"); show(search.keyword_search(con, WS, q))
        print(" vector:");  show(search.vector_search(con, WS, q))

if __name__ == "__main__":
    main()