# app/feedback.py
import uuid
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from app import db

TABLE = """
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES query_runs(run_id),
    user_id TEXT NOT NULL,
    rating INTEGER NOT NULL,
    issue_type TEXT NOT NULL DEFAULT 'none',
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now());
"""

class FeedbackIn(BaseModel):
    run_id: str
    rating: Literal[-1, 1]          # -1 = thumbs down, 1 = thumbs up
    issue_type: Literal["none", "wrong_answer", "bad_citation",
                        "missing_source", "other"] = "none"
    comment: str | None = Field(default=None, max_length=1000)

def register(app, get_con, current_user):
    @app.post("/api/v1/feedback", status_code=201)
    def submit_feedback(body: FeedbackIn, user: str = Depends(current_user),
                        con=Depends(get_con)):
        con.execute(TABLE)
        con.commit()
        run = con.execute("SELECT run_id FROM query_runs WHERE run_id=%s AND user_id=%s",
                          (body.run_id, user)).fetchone()
        if not run:
            raise HTTPException(404, "Run not found")
        fid = str(uuid.uuid4())
        con.execute(
            "INSERT INTO feedback (feedback_id, run_id, user_id, rating, issue_type, comment) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (fid, body.run_id, user, body.rating, body.issue_type, db._clean(body.comment)))
        con.commit()
        return {"feedback_id": fid, "run_id": body.run_id}
