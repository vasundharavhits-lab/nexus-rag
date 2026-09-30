from app.config import RAW_DIR, ensure_dirs
from app.ingest import ingest_directory
from app import db, profiling

WS, OWNER = "demo-workspace", "demo-user"

def main():
    ensure_dirs()
    con = db.connect()
    db.init_db(con)
    con.execute("INSERT INTO workspaces (workspace_id, name, owner) VALUES (%s,%s,%s) "
                "ON CONFLICT DO NOTHING", (WS, "Demo", OWNER))
    con.commit()

    records, sections, unsupported = ingest_directory(RAW_DIR, workspace_id=WS)
    db.save(con, WS, records, sections)

    df = profiling.add_flags(profiling.load_versions(con, WS))
    profiling.save_flags(con, df, WS)
    report = profiling.build_report(df, unsupported)
    profiling.write_report(report)
    print(f"Ingested {len(records)} files -> {report['by_status']}")

if __name__ == "__main__":
    main()