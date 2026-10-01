# app/router.py
import re, time
from app import search, hybrid

ID_PATTERNS = [
    (r"\b[A-Za-z]{1,6}-\d+\b", "identifier (e.g. DR-002)"),
    (r"\b[a-z0-9]+_[a-z0-9_]+\b", "snake_case term"),
    (r"\b\w+\.(?:md|pdf|docx|py|json)\b", "file name"),
    (r"\"[^\"]+\"", "quoted phrase"),
]

def classify(query: str):
    """Return (route, reason). Routes: 'vector' (default) or 'hybrid'."""
    for pat, why in ID_PATTERNS:
        if re.search(pat, query):
            return "hybrid", why
    words = query.split()
    if len(words) <= 3 and "?" not in query:
        return "hybrid", "short term lookup"
    return "vector", "conceptual question (default)"

def routed_search(con, workspace_id, query, k=5, strategy="structure"):
    route, reason = classify(query)
    fn = hybrid.hybrid_search if route == "hybrid" else search.vector_search
    t0 = time.perf_counter()
    rows = fn(con, workspace_id, query, k, strategy)
    trace = {"route": route, "reason": reason, "strategy": strategy,
             "returned": len(rows),
             "retrieve_ms": round((time.perf_counter() - t0) * 1000, 1),
             "top_score": round(float(rows[0]["score"]), 4) if rows else None}
    return rows, trace