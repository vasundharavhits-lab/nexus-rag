# app/jobs.py
"""Runs long uploads (big PDFs, OCR, embedding) in the background so the web request returns at
once and the browser can show progress. State lives in memory: if the server is restarted while
a file is being processed, that file must be uploaded again (the saved copy on disk is kept)."""
import threading, time, uuid
from concurrent.futures import ThreadPoolExecutor

from app.config import JOB_WORKERS

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_POOL = ThreadPoolExecutor(max_workers=max(1, JOB_WORKERS), thread_name_prefix="nexus-job")
_KEEP_SECONDS = 24 * 3600


def _purge():
    cutoff = time.time() - _KEEP_SECONDS
    for jid in [j for j, v in _JOBS.items() if v["updated"] < cutoff]:
        _JOBS.pop(jid, None)


def create(owner, workspace_id, filename):
    jid = str(uuid.uuid4())
    with _LOCK:
        _purge()
        _JOBS[jid] = {"job_id": jid, "owner": owner, "workspace_id": workspace_id,
                      "filename": filename, "state": "queued", "stage": "waiting",
                      "done": 0, "total": 0, "message": "Waiting to start", "result": None,
                      "error": None, "created": time.time(), "updated": time.time()}
    return jid


def update(jid, **fields):
    with _LOCK:
        if jid in _JOBS:
            _JOBS[jid].update(fields, updated=time.time())


def get(jid, owner):
    with _LOCK:
        job = _JOBS.get(jid)
        if not job or job["owner"] != owner:
            return None
        return dict(job)


def submit(jid, fn, *args):
    """Run fn(*args) in the background; any exception becomes the job's error."""
    def run():
        update(jid, state="running", message="Starting")
        try:
            fn(*args)
        except Exception as e:                         # never let a thread die silently
            update(jid, state="failed", stage="failed", error=f"{type(e).__name__}: {e}",
                   message="Processing failed")
    _POOL.submit(run)
