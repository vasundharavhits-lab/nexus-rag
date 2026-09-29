# app/profiling.py
import json
from datetime import datetime, timezone
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.config import NEAR_DUP_THRESHOLD, MIN_WORDS, REPORT_DIR

def load_versions(con) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM document_versions", con)
    df["word_count"] = df["text"].fillna("").str.split().str.len()
    return df

def find_exact_duplicates(df):
    groups = df.groupby("content_hash")["filename"].apply(list)
    return [g for g in groups if len(g) > 1]

def find_near_duplicates(df, threshold=NEAR_DUP_THRESHOLD):
    ok = df[df.status == "ok"].reset_index(drop=True)
    if len(ok) < 2:
        return []
    try:
        sim = cosine_similarity(
            TfidfVectorizer(stop_words="english").fit_transform(ok["text"]))
    except ValueError:              # e.g. empty vocabulary
        return []
    pairs = []
    for i in range(len(ok)):
        for j in range(i + 1, len(ok)):
            if sim[i, j] >= threshold and ok.content_hash[i] != ok.content_hash[j]:
                pairs.append((ok.filename[i], ok.filename[j], round(float(sim[i, j]), 3)))
    return sorted(pairs, key=lambda p: -p[2])

def add_flags(df):
    df = df.copy()
    ok_wc = df.loc[df.status == "ok", "word_count"]
    q1, q3 = ok_wc.quantile([0.25, 0.75]) if len(ok_wc) else (0, 0)
    df["flag_failed_or_empty"] = df.status.isin(["failed", "empty"])
    df["flag_very_short"] = (df.status == "ok") & (df.word_count < MIN_WORDS)
    df["flag_long_outlier"] = df.word_count > q3 + 1.5 * (q3 - q1)
    df["flag_missing_date"] = df.effective_at.isna() & (df.status == "ok")
    return df

def save_flags(con, df):
    con.execute("DELETE FROM quality_flags")
    cols = [c for c in df.columns if c.startswith("flag_")]
    rows = [(r.version_id, c) for r in df.itertuples() for c in cols if getattr(r, c)]
    con.executemany("INSERT INTO quality_flags VALUES (?,?)", rows)
    con.commit()

def build_report(df, unsupported) -> dict:
    flag_cols = [c for c in df.columns if c.startswith("flag_")]
    ok = df[df.status == "ok"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_files_seen": len(df) + len(unsupported),
        "unsupported_files": unsupported,
        "by_status": df["status"].value_counts().to_dict(),
        "by_file_type": df["file_type"].value_counts().to_dict(),
        "by_language": df["language"].value_counts().to_dict(),
        "missing_metadata_pct": (df[["doc_status", "effective_at", "author"]]
                                 .isna().mean() * 100).round(1).to_dict(),
        "exact_duplicate_groups": find_exact_duplicates(df),
        "near_duplicate_pairs": find_near_duplicates(df),
        "flagged_documents": df[df[flag_cols].any(axis=1)]["filename"].tolist(),
        "failures": df[df.status == "failed"][["filename", "error"]].to_dict("records"),
        "median_words": float(ok["word_count"].median()) if len(ok) else 0.0,
    }

def write_report(report: dict):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "ingestion_quality_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    md = ["# Ingestion Quality Report", f"Generated: {report['generated_at']}", ""]
    md += [f"- **{k}**: {v}" for k, v in report.items() if k != "generated_at"]
    (REPORT_DIR / "ingestion_quality_report.md").write_text("\n".join(md), encoding="utf-8")