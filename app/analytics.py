# app/analytics.py
import statistics
from collections import Counter
from fastapi import Depends
from app.feedback import TABLE

def _med(xs):
    return round(statistics.median(xs), 1) if xs else None

def _ms(t, new, old):
    return t.get(new, t.get(old))

def register(app, get_con, current_user, require_workspace):
    @app.get("/api/v1/analytics/retrieval")
    def retrieval_analytics(workspace_id: str, user: str = Depends(current_user),
                            con=Depends(get_con)):
        require_workspace(con, workspace_id, user)
        con.execute(TABLE)
        con.commit()
        runs = con.execute(
            "SELECT status, model, timings FROM query_runs WHERE workspace_id=%s",
            (workspace_id,)).fetchall()
        n = len(runs)
        if n == 0:
            return {"total_runs": 0}
        timings = [r["timings"] or {} for r in runs]
        by_status = Counter(r["status"] for r in runs)
        by_route = Counter(t["route"] for t in timings if "route" in t)
        retrieve = [v for t in timings
                    if (v := _ms(t, "retrieve_ms", "retrieve")) is not None]
        total = [v for t in timings
                 if (v := _ms(t, "total_ms", "total")) is not None]
        generate = [v for r, t in zip(runs, timings)
                    if r["model"] and (v := _ms(t, "generate_ms", "generate")) is not None]
        fb = con.execute(
            "SELECT f.rating, f.issue_type FROM feedback f "
            "JOIN query_runs r ON r.run_id = f.run_id WHERE r.workspace_id=%s",
            (workspace_id,)).fetchall()
        issues = Counter(f["issue_type"] for f in fb
                         if f["rating"] == -1 and f["issue_type"] != "none")
        return {
            "total_runs": n,
            "by_status": dict(by_status),
            "answered_rate": round(by_status["answered"] / n, 3),
            "refusal_rate": round(by_status["insufficient_evidence"] / n, 3),
            "uncited_rate": round(by_status["uncited"] / n, 3),
            "by_route": dict(by_route),
            "median_ms": {"retrieve": _med(retrieve), "generate": _med(generate),
                          "total": _med(total)},
            "model_calls": len(generate),
            "feedback": {"total": len(fb),
                         "thumbs_up": sum(1 for f in fb if f["rating"] == 1),
                         "thumbs_down": sum(1 for f in fb if f["rating"] == -1),
                         "issues": dict(issues)},
        }
