import hashlib, uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import db, profiling
from app.config import MAX_UPLOAD_MB, SUPPORTED, UPLOAD_DIR
from app.ingest import ingest_file


@asynccontextmanager
async def lifespan(app: FastAPI):
    con = db.connect()
    db.init_db(con)
    con.close()
    yield


app = FastAPI(title="NEXUS RAG", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def add_request_id(request, call_next):
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


def get_con():
    con = db.connect()
    try:
        yield con
    finally:
        con.close()


def current_user(x_user_id: str | None = Header(default=None)) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header")
    return x_user_id


def require_workspace(con, workspace_id: str, user: str):
    row = con.execute(
        "SELECT * FROM workspaces WHERE workspace_id=%s AND owner=%s",
        (workspace_id, user)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return row


@app.get("/health")
def health():
    return {"status": "ok"}


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@app.post("/api/v1/workspaces", status_code=201)
def create_workspace(body: WorkspaceIn, user: str = Depends(current_user),
                     con=Depends(get_con)):
    wid = str(uuid.uuid4())
    con.execute("INSERT INTO workspaces (workspace_id, name, owner) VALUES (%s,%s,%s)",
                (wid, body.name, user))
    con.commit()
    return {"workspace_id": wid, "name": body.name, "owner": user,
            "access_policy": "private"}


@app.post("/api/v1/documents/upload", status_code=201)
def upload_document(workspace_id: str, file: UploadFile = File(...),
                    user: str = Depends(current_user), con=Depends(get_con)):
    require_workspace(con, workspace_id, user)

    name = Path(file.filename or "").name
    ext = Path(name).suffix.lower()
    if not name or ext not in SUPPORTED:
        raise HTTPException(415, f"Unsupported file type. Allowed: {sorted(SUPPORTED)}")

    limit = MAX_UPLOAD_MB * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File larger than {MAX_UPLOAD_MB} MB")

    chash = hashlib.sha256(data).hexdigest()
    dest_dir = UPLOAD_DIR / workspace_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{chash}{ext}"
    if not dest.exists():
        dest.write_bytes(data)

    rec, secs = ingest_file(dest, workspace_id=workspace_id, original_name=name)
    sections = [{**s, "version_id": rec["version_id"], "idx": i} for i, s in enumerate(secs)]
    db.save(con, workspace_id, [rec], sections)

    df = profiling.add_flags(profiling.load_versions(con, workspace_id))
    profiling.save_flags(con, df, workspace_id)

    return {k: rec[k] for k in ("version_id", "document_id", "filename", "label",
                                "status", "error", "content_hash", "section_count")}


@app.get("/api/v1/documents")
def list_documents(workspace_id: str, user: str = Depends(current_user),
                   con=Depends(get_con)):
    require_workspace(con, workspace_id, user)
    return con.execute(
        "SELECT v.version_id, d.logical_name, v.label, v.filename, v.status, "
        "v.language, v.ingested_at FROM document_versions v "
        "JOIN documents d USING (document_id) WHERE d.workspace_id=%s "
        "ORDER BY d.logical_name, v.label", (workspace_id,)).fetchall()


@app.get("/api/v1/documents/{version_id}")
def get_document(version_id: str, user: str = Depends(current_user),
                 con=Depends(get_con)):
    row = con.execute(
        "SELECT v.version_id, v.document_id, d.workspace_id, d.logical_name, v.label, "
        "v.filename, v.file_type, v.size_bytes, v.content_hash, v.status, v.error, "
        "v.page_count, v.doc_status, v.effective_at, v.ingested_at, v.author, "
        "v.language, v.section_count "
        "FROM document_versions v JOIN documents d USING (document_id) "
        "JOIN workspaces w ON w.workspace_id = d.workspace_id "
        "WHERE v.version_id=%s AND w.owner=%s", (version_id, user)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    row["flags"] = [r["flag_type"] for r in con.execute(
        "SELECT flag_type FROM quality_flags WHERE version_id=%s", (version_id,)).fetchall()]
    return row


@app.get("/api/v1/analytics/corpus")
def corpus_analytics(workspace_id: str, user: str = Depends(current_user),
                     con=Depends(get_con)):
    require_workspace(con, workspace_id, user)
    df = profiling.load_versions(con, workspace_id)
    if df.empty:
        return {"total_files_seen": 0}
    return profiling.build_report(profiling.add_flags(df), [])