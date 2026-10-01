# scripts/gate_check.py
from app import db
from app.answering import answer_question

con = db.connect()
r = answer_question(con, "demo-workspace", "demo-user",
                    "How does the current architecture handle ingestion?", "auto", 4)
print("gate:", r["trace"]["gate_vector_score"])
print("evidence[1] score:", r["evidence"][0]["score"])