import time
from typing import Literal
from app import indexing, jobs, ocr, search as search_mod
import hashlib, uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db, profiling
from app import answering, llm, changes, chatting
import logging
from app.config import MAX_UPLOAD_MB, SUPPORTED, UPLOAD_DIR, WARMUP_ON_START, ACCEPT_ANY_FILE
log = logging.getLogger('nexus')
from app.ingest import ingest_file

def _warmup():
    """Load the search model before the first question (retries, because a download can fail once)."""
    from app import embeddings
    for _ in range(3):
        try:
            embeddings.embed_query("warm up")
            return
        except Exception as e:
            log.warning("search model warm-up failed: %s", e)
            time.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    con = db.connect()
    db.init_db(con)
    con.close()
    if WARMUP_ON_START:
        import threading
        threading.Thread(target=_warmup, daemon=True).start()
    yield


app = FastAPI(title="NEXUS RAG", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def add_request_id(request, call_next):
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    """Never a bare 500: log the real cause, tell the user something useful."""
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:8]
    log.exception("request %s failed", rid)
    return JSONResponse(status_code=500, content={
        "detail": f"Something went wrong on the server ({type(exc).__name__}). Please try again; "
                  f"if it keeps happening, check the server window for reference {rid}.",
        "request_id": rid})


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


def _save_stream(file: UploadFile, dest_dir: Path, ext: str):
    """Copy the upload to disk 1 MB at a time while hashing it, so memory use stays flat whether
    the file is 1 MB or 1 GB. The limit (MAX_UPLOAD_MB in .env, 0 = no limit) is enforced while
    streaming, so an oversized file is rejected early and never stored."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    limit = MAX_UPLOAD_MB * 1024 * 1024 if MAX_UPLOAD_MB > 0 else None
    tmp = dest_dir / f".upload-{uuid.uuid4().hex}.part"
    h, size = hashlib.sha256(), 0
    try:
        with open(tmp, "wb") as out:
            while True:
                block = file.file.read(1 << 20)
                if not block:
                    break
                size += len(block)
                if limit and size > limit:
                    raise HTTPException(413, f"File larger than {MAX_UPLOAD_MB} MB")
                h.update(block)
                out.write(block)
        chash = h.hexdigest()
        dest = dest_dir / f"{chash}{ext}"
        if dest.exists():
            tmp.unlink()
        else:
            tmp.replace(dest)
        return dest, size
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


_RESULT_KEYS = ("version_id", "document_id", "filename", "label", "status", "error",
                "content_hash", "section_count")
_STAGE_LABEL = {"reading": "Reading pages", "ocr": "Reading scanned pages (OCR)",
                "indexing": "Building the search index"}


def _refresh_quality_flags(con, workspace_id):
    df = profiling.add_flags(profiling.load_versions(con, workspace_id))
    profiling.save_flags(con, df, workspace_id)


def _process_upload(job_id, dest, workspace_id, name):
    """Runs in a background thread: parse (and OCR if needed), save, then index this file only."""
    def prog(stage, done, total):
        jobs.update(job_id, stage=stage, done=done, total=total,
                    message=f"{_STAGE_LABEL.get(stage, stage)}: {done} of {total}")

    con = db.connect()
    try:
        jobs.update(job_id, stage="reading", message="Reading the file")
        rec, secs = ingest_file(dest, workspace_id=workspace_id, original_name=name,
                                progress=prog)
        sections = [{**s, "version_id": rec["version_id"], "idx": i}
                    for i, s in enumerate(secs)]
        jobs.update(job_id, stage="saving", message="Saving")
        db.save(con, workspace_id, [rec], sections)
        _refresh_quality_flags(con, workspace_id)
        result = {k: rec[k] for k in _RESULT_KEYS}
        result["ocr_pages"] = rec.get("ocr_pages", 0)
        if rec["status"] == "ok":
            indexing.index_versions(con, [rec["version_id"]],
                                    progress=lambda d, t: prog("indexing", d, t))
            jobs.update(job_id, state="done", stage="done", result=result,
                        message="Ready. You can ask questions about this file now.")
        else:
            jobs.update(job_id, state="done", stage="done", result=result, error=rec["error"],
                        message=rec["error"] or f"No text could be read ({rec['status']}).")
    finally:
        con.close()


@app.get("/api/v1/limits")
def limits():
    """What this server accepts. The web page reads this, so nothing is hard-coded there."""
    st = ocr.ocr_status()
    return {"max_upload_mb": MAX_UPLOAD_MB,           # 0 = no limit
            "supported": sorted(SUPPORTED),
            "ocr": {"available": st["available"], "languages": st["langs"],
                    "missing_languages": st["missing"], "reason": st["reason"]}}


@app.get("/api/v1/jobs/{job_id}")
def job_status(job_id: str, user: str = Depends(current_user)):
    job = jobs.get(job_id, user)
    if not job:
        raise HTTPException(404, "Job not found")
    return {k: v for k, v in job.items() if k != "owner"}


@app.post("/api/v1/documents/upload", status_code=201)
def upload_document(workspace_id: str, background: bool = False,
                    file: UploadFile = File(...),
                    user: str = Depends(current_user), con=Depends(get_con)):
    """background=false (default): process before answering, as before.
    background=true: save the file, answer 202 with a job_id and keep working in the background
    (use this for big files and scans; poll GET /api/v1/jobs/{job_id})."""
    require_workspace(con, workspace_id, user)

    name = Path(file.filename or "").name
    ext = Path(name).suffix.lower()
    if not name or (ext not in SUPPORTED and not ACCEPT_ANY_FILE):
        raise HTTPException(415, f"Unsupported file type. Allowed: {sorted(SUPPORTED)}")

    dest, _size = _save_stream(file, UPLOAD_DIR / workspace_id, ext)
    if ext not in SUPPORTED:                       # unknown extension: look at the content instead
        from app.parsing import sniff_type
        real = sniff_type(dest)
        if not real:
            dest.unlink(missing_ok=True)
            raise HTTPException(415, f"{name}: this file type is not supported (could not recognise its content).")

    if background:
        jid = jobs.create(user, workspace_id, name)
        jobs.submit(jid, _process_upload, jid, dest, workspace_id, name)
        return JSONResponse(status_code=202,
                            content={"job_id": jid, "filename": name, "state": "queued"})

    rec, secs = ingest_file(dest, workspace_id=workspace_id, original_name=name)
    sections = [{**s, "version_id": rec["version_id"], "idx": i} for i, s in enumerate(secs)]
    db.save(con, workspace_id, [rec], sections)
    _refresh_quality_flags(con, workspace_id)
    return {k: rec[k] for k in _RESULT_KEYS}


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
def index_workspace(workspace_id: str, embed: bool = True, only_missing: bool = False,
                    rebuild: bool = False, strategies: str = "structure",
                    user: str = Depends(current_user), con=Depends(get_con)):
    require_workspace(con, workspace_id, user)
    strat = tuple(x.strip() for x in strategies.split(",") if x.strip())
    if not strat or any(x not in indexing.VALID_STRATEGIES for x in strat):
        raise HTTPException(422, f"strategies must be a comma list of {list(indexing.VALID_STRATEGIES)}")
    return indexing.index_workspace(con, workspace_id, strategies=strat, embed=embed, rebuild=rebuild)


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
    question: str = Field(min_length=1, max_length=4000)
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
    scope: Literal["auto", "documents", "general", "guidance"] = "auto"
    mode: Literal["keyword", "vector", "auto"] = "auto"       # retrieval mode for documents
    k: int = Field(default=4, ge=1, le=8)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)
    answer_lang: str | None = Field(default=None, max_length=30)


@app.post("/api/v1/chat")
def chat(body: ChatIn, user: str = Depends(current_user), con=Depends(get_con)):
    """Chat with Nexus: documents first (auto), documents only, or general knowledge."""
    try:
        return chatting.reply(con, body.workspace_id, user, body.message, body.history,
                              body.scope, body.mode, body.k, body.answer_lang)
    except chatting.WorkspaceNotFound:
        raise HTTPException(404, "Workspace not found")
    except chatting.RateLimited:
        raise HTTPException(429, "Too many requests right now. Please wait a minute and try again.")
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))


@app.get("/api/v1/status")
def status():
    """Health of each part, for the chat page banner."""
    out = {"llm": {"ok": True, "message": ""}, "ocr": ocr.ocr_status()}
    try:
        llm.chat([{"role": "user", "content": "hi"}], max_tokens=1)
    except Exception as e:
        out["llm"] = {"ok": False, "message": str(e)}
    return out


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
