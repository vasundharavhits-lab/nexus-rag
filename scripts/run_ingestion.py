# scripts/run_ingestion.py
from app.config import RAW_DIR, ensure_dirs
from app.ingest import ingest_directory
from app import db, profiling

def main():
    ensure_dirs()
    records, sections, unsupported = ingest_directory(RAW_DIR)

    con = db.connect()
    db.init_db(con)
    db.save(con, records, sections)

    df = profiling.add_flags(profiling.load_versions(con))
    profiling.save_flags(con, df)

    report = profiling.build_report(df, unsupported)
    profiling.write_report(report)
    print(f"Ingested {len(records)} files -> {report['by_status']}")
    print("Report written to reports/")

if __name__ == "__main__":
    main()