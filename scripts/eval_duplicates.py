# scripts/eval_duplicates.py
"""Evaluate near-duplicate detection against labelled pairs (blueprint 6.3 / 19).

Needs no database and no models. Run:  python -m scripts.eval_duplicates

Ground truth (built from filenames, so it is cheap and reproducible):
  * data/raw  : decisions.md = decisions_copy.md (exact copy)
                meeting_2026_03.md ~ meeting_2026_03_final.md (reworded copy)
  * data/raw2 : the same document saved as .md / .docx / .pdf  -> duplicates
  Everything else is a NON-duplicate. Different *versions* of one document
  (architecture_v1 / v2 / v3) are deliberately negatives: they are related but
  must not be merged, because a version rule needs both of them.
"""
import itertools, json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import ROOT, REPORT_DIR, NEAR_DUP_THRESHOLD
from app.ingest import ingest_file

SUPPORTED = {".md", ".docx", ".pdf"}
THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

# data/raw: hand-labelled duplicate pairs (stems)
RAW_DUPLICATES = {frozenset({"decisions.md", "decisions_copy.md"}),
                  frozenset({"meeting_2026_03.md", "meeting_2026_03_final.md"})}


def load(folder: Path):
    docs = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in SUPPORTED:
            continue
        rec, _ = ingest_file(p, workspace_id="eval")
        if rec["status"] == "ok" and rec["text"].strip():
            docs.append({"name": p.name, "stem": p.stem, "text": rec["text"],
                         "hash": rec["content_hash"]})
    return docs


def labelled_pairs(docs, is_dup):
    """Return [(name_a, name_b, similarity, label)] for every pair of documents."""
    tfidf = TfidfVectorizer(stop_words="english").fit_transform([d["text"] for d in docs])
    sim = cosine_similarity(tfidf)
    out = []
    for i, j in itertools.combinations(range(len(docs)), 2):
        a, b = docs[i], docs[j]
        exact = a["hash"] == b["hash"]
        out.append({"a": a["name"], "b": b["name"], "sim": round(float(sim[i, j]), 3),
                    "exact": exact, "label": bool(is_dup(a, b))})
    return out


def score(pairs, t):
    """A pair is flagged when it is an exact copy OR similarity >= t (same rule as profiling.py)."""
    tp = sum(1 for p in pairs if p["label"] and (p["exact"] or p["sim"] >= t))
    fp = sum(1 for p in pairs if not p["label"] and (p["exact"] or p["sim"] >= t))
    fn = sum(1 for p in pairs if p["label"] and not (p["exact"] or p["sim"] >= t))
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"threshold": t, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}


def run_set(title, folder, is_dup):
    docs = load(folder)
    pairs = labelled_pairs(docs, is_dup)
    pos = sum(p["label"] for p in pairs)
    print(f"\n{title}: {len(docs)} documents, {len(pairs)} pairs, {pos} true duplicate pairs")
    print(f"{'thr':>5}{'TP':>4}{'FP':>4}{'FN':>4}{'prec':>7}{'rec':>7}{'F1':>7}")
    rows = []
    for t in THRESHOLDS:
        s = score(pairs, t)
        rows.append(s)
        mark = "  <- current setting" if abs(t - NEAR_DUP_THRESHOLD) < 1e-9 else ""
        print(f"{t:>5.1f}{s['tp']:>4}{s['fp']:>4}{s['fn']:>4}"
              f"{s['precision']:>7.2f}{s['recall']:>7.2f}{s['f1']:>7.2f}{mark}")
    cur = score(pairs, NEAR_DUP_THRESHOLD)
    errs = [p for p in pairs if (p["label"] and not (p["exact"] or p["sim"] >= NEAR_DUP_THRESHOLD))
            or (not p["label"] and (p["exact"] or p["sim"] >= NEAR_DUP_THRESHOLD))]
    if errs:
        print(f"Errors at the current threshold ({NEAR_DUP_THRESHOLD}):")
        for p in sorted(errs, key=lambda p: -p["sim"])[:8]:
            kind = "missed duplicate" if p["label"] else "false alarm"
            print(f"   {kind:<17} sim={p['sim']:.3f}  {p['a']}  <->  {p['b']}")
    # lowest similarity among true duplicates vs highest among non-duplicates:
    # a gap between them means a clean threshold exists
    lo = min((p["sim"] for p in pairs if p["label"] and not p["exact"]), default=None)
    hi = max((p["sim"] for p in pairs if not p["label"]), default=None)
    print(f"Lowest true-duplicate similarity: {lo}   Highest non-duplicate similarity: {hi}")
    if len(errs) > 8:
        print(f"   ... and {len(errs) - 8} more")
    rec_t = round((lo + hi) / 2, 2) if lo is not None and hi is not None and lo > hi else None
    if rec_t:
        print(f"A clean gap exists. Midpoint threshold: {rec_t}")
    return {"documents": len(docs), "pairs": len(pairs), "true_duplicates": pos,
            "sweep": rows, "current": cur, "min_dup_sim": lo, "max_nondup_sim": hi,
            "midpoint_threshold": rec_t, "errors_at_current": errs}


def main():
    results = {}
    results["raw"] = run_set(
        "data/raw (hand-labelled)", ROOT / "data" / "raw",
        lambda a, b: frozenset({a["name"], b["name"]}) in RAW_DUPLICATES)
    results["raw2"] = run_set(
        "data/raw2 (same document in 3 formats = duplicate)", ROOT / "data" / "raw2",
        lambda a, b: a["stem"] == b["stem"])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "duplicate_eval.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
