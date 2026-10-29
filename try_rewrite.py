# try_rewrite.py - see how YOUR model understands a question typed in Latin letters, before and after the fix.
# Run from D:\nexus-rag (Ollama running):
#     python try_rewrite.py "yudha kaha hua tha ?"
#     python try_rewrite.py "Arjun ke sarathi kaun the?" --docs hi
#     python try_rewrite.py "quelle est la capitale ?" --docs en
# --docs is the language of your documents (hi, en, fr, ...); default hi.
import sys, time
sys.stdout.reconfigure(encoding="utf-8")
from app import llm, rewrite

args = [a for a in sys.argv[1:] if not a.startswith("--")]
docs = sys.argv[sys.argv.index("--docs") + 1] if "--docs" in sys.argv else "hi"
questions = args or ["yudha kaha hua tha ?", "Arjun ke sarathi kaun the?", "aatma ko shastra kyon nahi kaat sakte?"]
prof = {"languages": [(docs, 1.0)], "scripts": {}}

for q in questions:
    print(f"\nQUESTION: {q}")
    try:
        from app import ai_steps
        t = time.time()
        old = ai_steps.rewrite_queries(q, prof, llm.generate)
        print(f"  OLD  ({time.time() - t:.1f}s): {old}")
    except Exception as e:
        print("  OLD  not available:", type(e).__name__, e)
    t = time.time()
    res = rewrite.rewrite_chain(q, prof, llm.generate)
    print(f"  NEW  ({time.time() - t:.1f}s): language={res['language']!r}")
    print(f"       native  = {res['native']!r}")
    print(f"       english = {res['english']!r}")
    print(f"       search with: {res['queries']}")
