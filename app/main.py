import os, threading, time
from typing import Literal
from app import indexing, search as search_mod
import hashlib, uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import db, profiling
from app import answering, llm, changes, chatting, jobs, ocr
from app.config import SUPPORTED, UPLOAD_DIR
from app.limits import MAX_UPLOAD_MB, WARMUP_MODELS
from app.ingest import ingest_file

def _warm_up():
    """Load the search and claim-check models in the background so the first upload and the
    first answer do not pay the loading time. Failures are ignored: real use reports them."""
    try:
        from app import embeddings, verify
        embeddings._model()
        verify.get_model()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    con = db.connect()
    db.init_db(con)
    con.close()
    if WARMUP_MODELS and not os.getenv("PYTEST_CURRENT_TEST"):    # never during tests
        threading.Thread(target=_warm_up, daemon=True).start()
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

    # Stream to disk in 1 MB pieces while hashing: memory use does not grow with file size.
    limit = MAX_UPLOAD_MB * 1024 * 1024
    dest_dir = UPLOAD_DIR / workspace_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / f".upload-{uuid.uuid4().hex}"
    digest, size = hashlib.sha256(), 0
    try:
        with open(tmp, "wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"{name} is larger than the {MAX_UPLOAD_MB} MB limit "
                                             "(the server setting MAX_UPLOAD_MB).")
                digest.update(chunk)
                out.write(chunk)
        dest = dest_dir / f"{digest.hexdigest()}{ext}"
        if dest.exists():
            tmp.unlink()
        else:
            os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)

    rec, secs = ingest_file(dest, workspace_id=workspace_id, original_name=name, defer_ocr=True)

    pending = rec.pop("_ocr", None)                      # scanned PDF: read it in the background
    sections = [{**s, "version_id": rec["version_id"], "idx": i} for i, s in enumerate(secs)]
    db.save(con, workspace_id, [rec], sections)

    df = profiling.add_flags(profiling.load_versions(con, workspace_id))
    profiling.save_flags(con, df, workspace_id)

    job = jobs.submit_ocr(workspace_id, rec, pending["texts"], pending["pages"], dest) if pending else None
    out = {k: rec[k] for k in ("version_id", "document_id", "filename", "label",
                               "status", "error", "content_hash", "section_count")}
    out["job_id"] = job["id"] if job else None
    return out


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


@app.get("/api/v1/changes")
def version_changes(workspace_id: str, document: str, from_label: str, to_label: str,
                    user: str = Depends(current_user), con=Depends(get_con)):
    """Section-by-section difference between two versions of one document."""
    require_workspace(con, workspace_id, user)
    res = changes.compare(con, workspace_id, document, from_label, to_label)
    if res is None:
        raise HTTPException(status_code=404, detail="Document or versions not found")
    return res


@app.get("/api/v1/analytics/corpus")
def corpus_analytics(workspace_id: str, user: str = Depends(current_user),
                     con=Depends(get_con)):
    require_workspace(con, workspace_id, user)
    df = profiling.load_versions(con, workspace_id)
    if df.empty:
        return {"total_files_seen": 0}
    return profiling.build_report(profiling.add_flags(df), [])

@app.post("/api/v1/workspaces/{workspace_id}/index")
def index_workspace(workspace_id: str, embed: bool = True, rebuild: bool = False,
                    strategies: str = "structure", background: bool = False,
                    user: str = Depends(current_user), con=Depends(get_con)):
    """Index new documents. Already-indexed versions are skipped unless rebuild=true.
    strategies is "structure" (what search and chat use) and/or "fixed" (ablation only)."""
    require_workspace(con, workspace_id, user)
    wanted = tuple(s.strip() for s in strategies.split(",") if s.strip())
    if not wanted or any(s not in ("structure", "fixed") for s in wanted):
        raise HTTPException(422, "strategies must be 'structure', 'fixed' or 'structure,fixed'")
    if background:                                   # big collections: return at once, report progress
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=202, content={"job": jobs.submit_index(workspace_id)})
    return indexing.index_workspace(con, workspace_id, strategies=wanted, embed=embed,
                                    only_new=not rebuild)

@app.get("/api/v1/workspaces/{workspace_id}/jobs")
def workspace_jobs(workspace_id: str, user: str = Depends(current_user), con=Depends(get_con)):
    """Progress of background work (OCR, indexing) in this workspace."""
    require_workspace(con, workspace_id, user)
    return {"jobs": jobs.list_jobs(workspace_id)}

@app.get("/api/v1/limits")
def limits():
    """What this server accepts, so the page can tell the user instead of guessing."""
    return {"max_upload_mb": MAX_UPLOAD_MB, "supported": sorted(SUPPORTED), "ocr": ocr.status()}


class SearchIn(BaseModel):
    workspace_id: str
    query: str = Field(min_length=1, max_length=500)
    mode: Literal["keyword", "vector"] = "keyword"
    strategy: Literal["structure", "fixed"] = "structure"
    k: int = Field(default=5, ge=1, le=20)

@app.post("/api/v1/search")
def search(body: SearchIn, user: str = Depends(current_user), con=Depends(get_con)):
    require_workspace(con, body.workspace_id, user)
    fn = search_mod.keyword_search if body.mode == "keyword" else search_mod.vector_search
    t0 = time.perf_counter()
    results = fn(con, body.workspace_id, body.query, body.k, body.strategy)
    return {"query": body.query, "mode": body.mode, "strategy": body.strategy,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "results": results}

class QueryIn(BaseModel):
    workspace_id: str
    question: str = Field(min_length=1, max_length=500)
    mode: Literal["keyword", "vector", "auto"] = "vector"
    k: int = Field(default=4, ge=1, le=8)


@app.post("/api/v1/query")
def query(body: QueryIn, user: str = Depends(current_user), con=Depends(get_con)):
    require_workspace(con, body.workspace_id, user)
    try:
        return answering.answer_question(con, body.workspace_id, user,
                                         body.question, body.mode, body.k)
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    workspace_id: str | None = None
    scope: Literal["auto", "documents", "general"] = "auto"
    mode: Literal["keyword", "vector", "auto"] = "auto"       # retrieval mode for documents
    k: int = Field(default=4, ge=1, le=8)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)


@app.post("/api/v1/chat")
def chat(body: ChatIn, user: str = Depends(current_user), con=Depends(get_con)):
    """Chat with Nexus: documents first (auto), documents only, or general knowledge."""
    try:
        return chatting.reply(con, body.workspace_id, user, body.message, body.history,
                              body.scope, body.mode, body.k)
    except chatting.WorkspaceNotFound:
        raise HTTPException(404, "Workspace not found")
    except chatting.RateLimited:
        raise HTTPException(429, "Too many requests right now. Please wait a minute and try again.")
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))


@app.get("/api/v1/model")
def model_info():
    """Which language model is active (never includes the API key)."""
    return llm.describe()


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str, user: str = Depends(current_user), con=Depends(get_con)):
    row = con.execute("SELECT * FROM query_runs WHERE run_id=%s AND user_id=%s",
                      (run_id, user)).fetchone()
    if not row:
        raise HTTPException(404, "Run not found")
    return row


@app.get("/api/v1/chunks/{chunk_id}")
def get_chunk(chunk_id: str, user: str = Depends(current_user), con=Depends(get_con)):
    row = con.execute(
        "SELECT c.chunk_id, c.strategy, c.idx, c.heading_path, c.page, c.text, "
        "v.version_id, v.label, v.filename, v.doc_status, v.effective_at, "
        "d.logical_name, d.workspace_id "
        "FROM chunks c JOIN document_versions v ON v.version_id = c.version_id "
        "JOIN documents d ON d.document_id = v.document_id "
        "JOIN workspaces w ON w.workspace_id = d.workspace_id "
        "WHERE c.chunk_id=%s AND w.owner=%s", (chunk_id, user)).fetchone()
    if not row:
        raise HTTPException(404, "Chunk not found")
    return row

from app import feedback
feedback.register(app, get_con, current_user)

from app import analytics
analytics.register(app, get_con, current_user, require_workspace)

from app import explorer
explorer.register(app)

from pathlib import Path
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


from fastapi.responses import RedirectResponse


@app.get("/", include_in_schema=False)
def root():
    """Opening the bare server address (e.g. the ngrok link) lands on the chat page."""
    return RedirectResponse("/static/chat.html")
