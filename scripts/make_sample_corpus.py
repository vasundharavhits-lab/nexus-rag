# scripts/make_sample_corpus.py
from docx import Document as DocxDocument
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from app.config import RAW_DIR, ensure_dirs

MD = {
"architecture_v1.md": """# Architecture
Status: Draft
Date: 2026-01-10

## Overview
The system is a monolithic FastAPI service. Retrieval uses keyword search only.

## Storage
All data is stored in PostgreSQL. Full-text search is used for retrieval of documents.
""",
"architecture_v2.md": """# Architecture
Status: Approved
Date: 2026-02-15

## Overview
The system is a FastAPI service with a separate ingestion worker. Retrieval combines keyword and vector search.

## Storage
PostgreSQL stores metadata and full-text indexes. The pgvector extension stores embeddings for semantic retrieval.
""",
"architecture_v3.md": """# Architecture
Status: Approved
Date: 2026-03-20

## Overview
The system adds a reranking stage after hybrid retrieval. Ingestion runs asynchronously through Celery workers.

## Storage
PostgreSQL with pgvector remains the primary store. Redis is used for caching and job queues.
""",
"decisions.md": """# Decision Records
Author: Tech Lead
Date: 2026-02-01

## DR-001 Vector search
We decided to introduce vector search because keyword search missed conceptual questions from users.

## DR-002 Use pgvector
We chose pgvector to avoid running a separate vector database during the prototype phase.
""",
"meeting_2026_03.md": """# Meeting Notes March
Date: 2026-03-05

## Discussion
The team reviewed retrieval latency and agreed to test a cross-encoder reranker on the benchmark set.

## Actions
Assign annotation of the evaluation questions and prepare the ingestion quality report.
""",
"empty_notes.md": "",
"short_note.md": "# Note\nTODO",
}
MD["decisions_copy.md"] = MD["decisions.md"]                                  # exact duplicate
MD["meeting_2026_03_final.md"] = MD["meeting_2026_03.md"].replace("agreed", "decided")  # near-duplicate

def main():
    ensure_dirs()
    for name, text in MD.items():
        (RAW_DIR / name).write_text(text, encoding="utf-8")

    d = DocxDocument()
    d.add_heading("Requirements", level=1)
    d.add_paragraph("Status: Approved")
    d.add_paragraph("Date: 2026-02-20")
    d.add_heading("Functional Requirements", level=2)
    d.add_paragraph("The system shall answer questions with citations that point to the exact source passage.")
    d.add_paragraph("The system shall abstain when retrieved evidence is insufficient.")
    d.save(RAW_DIR / "requirements_v2.docx")

    c = canvas.Canvas(str(RAW_DIR / "test_report_v1.pdf"), pagesize=A4)
    for lines in (["Test Report", "Date: 2026-03-10",
                   "Summary: Ingestion tests passed for markdown and docx files."],
                  ["Results", "Retrieval recall at 5 was measured on 40 questions.",
                   "Latency p95 was under two seconds."]):
        y = 800
        for line in lines:
            c.drawString(72, y, line); y -= 20
        c.showPage()
    c.save()

    (RAW_DIR / "broken_report.pdf").write_bytes(b"this is not a real pdf \x00\x01\x02")
    print("Sample corpus written to", RAW_DIR)

if __name__ == "__main__":
    main()