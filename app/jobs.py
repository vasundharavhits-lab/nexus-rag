# app/jobs.py
"""Background jobs for slow work (OCR of a scanned book, indexing thousands of passages), so
a request never waits minutes and the page can show real progress."""
import threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from app import db, indexing, ingest, ocr, profiling
from app.limits import JOB_WORKERS

_pool = ThreadPoolExecutor(max_workers=max(1, JOB_WORKERS), thread_name_prefix="nexus-job")
_jobs, _lock = {}, threading.Lock()
KEEP = 60


def _new(kind, workspace_id, label):
    job = {"id": uuid.uuid4().hex[:12], "kind": kind, "workspace_id": workspace_id,
           "label": label, "state": "queued", "stage": "queued", "done": 0, "total": 0,
           "error": None, "started_at": time.time(), "finished_at": None}
    with _lock:
        _jobs[job["id"]] = job
        for old in sorted(_jobs.values(), key=lambda j: j["started_at"])[:-KEEP]:
            _jobs.pop(old["id"], None)
    return job


def _set(job, **kw):
    with _lock:
        job.update(kw)


def snapshot(job):
    with _lock:
        return dict(job)


def list_jobs(workspace_id):
    with _lock:
        rows = [dict(j) for j in _jobs.values() if j["workspace_id"] == workspace_id]
    return sorted(rows, key=lambda j: -j["started_at"])


def _run(job, fn):
    _set(job, state="running")
    try:
        fn(job)
        _set(job, state="done", stage="done", finished_at=time.time())
    except Exception as e:                                  # reported to the page, never raised
        _set(job, state="failed", error=f"{type(e).__name__}: {e}", finished_at=time.time())


def _progress(job):
    return lambda done, total: _set(job, done=done, total=total)


def _index(con, workspace_id, job):
    _set(job, stage="indexing", done=0, total=0)
    indexing.index_workspace(con, workspace_id, strategies=("structure",), embed=True,
                             only_new=True, progress=_progress(job))


def submit_index(workspace_id):
    job = _new("index", workspace_id, "search index")

    def fn(j):
        con = db.connect()
        try:
            _index(con, workspace_id, j)
        finally:
            con.close()
    _pool.submit(_run, job, fn)
    return snapshot(job)


def submit_ocr(workspace_id, rec, texts, pages, path):
    """Read the scanned pages, save the finished document, then index it."""
    job = _new("ocr", workspace_id, rec["filename"])
    version_id = rec["version_id"]

    def fn(j):
        con = db.connect()
        try:
            _set(j, stage="reading scanned pages", done=0, total=len(pages))
            got = ocr.ocr_pages(path, pages, progress=_progress(j))
            for i in pages:
                texts[i] = got.get(i, "")
            _set(j, stage="saving", done=0, total=0)
            final, sections = ingest.finish_pdf(dict(rec), texts)
            sections = [{**s, "version_id": version_id, "idx": i} for i, s in enumerate(sections)]
            db.save(con, workspace_id, [final], sections)
            profiling.save_flags(con, profiling.add_flags(profiling.load_versions(con, workspace_id)),
                                 workspace_id)
            ocr.clear_checkpoint(path)
            if final["status"] == "ok":
                _index(con, workspace_id, j)
        except Exception as e:
            con.rollback()
            con.execute("UPDATE document_versions SET status='failed', error=%s WHERE version_id=%s",
                        (f"{type(e).__name__}: {e}"[:500], version_id))
            con.commit()
            raise
        finally:
            con.close()
    _pool.submit(_run, job, fn)
    return snapshot(job)
