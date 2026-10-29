import time
from app.verify import verify_answer

V1 = "The system is a monolithic FastAPI service. Retrieval uses keyword search only."
V2 = ("The system is a FastAPI service with a separate ingestion worker. "
      "Retrieval combines keyword and vector search.")
V3 = "PostgreSQL with pgvector remains the primary store. Redis is used for caching and job queues."
ERR = ("Error ERR-5023 means the nightly reindex job could not acquire the chunk table lock. "
       "Retry after the lock_timeout_ms window expires.")
POLICY = (
    "Data Governance and Document Lifecycle Policy Status: Approved Date: 2026-05-01 "
    "Author: Data Governance Office Purpose and Scope This policy defines how organizational "
    "documents are classified, owned, approved, indexed, retained, and retired. It applies to "
    "technical specifications, business procedures, project records, training materials, support "
    "documentation, and internal policies. Ownership and Classification Every managed document "
    "should have a business owner and a classification label such as Public, Internal, "
    "Confidential, or Restricted. The owner is responsible for accuracy and updates. Restricted "
    "documents must not appear in snippets or citations for unauthorized users. Missing ownership "
    "should trigger a review queue. Approval Lifecycle Documents move through Draft, In Review, "
    "Approved, Archived, and Withdrawn states.")
ARCH_PDF = ("Answers should cite the source document and relevant section. Draft documents should be "
            "distinguished from approved documents, and the system should prefer approved material "
            "when versions conflict.")

M1 = {1: {"label": "v1", "status": "Draft"}}
M2 = {1: {"label": "v2", "status": "Approved"}}
MP = {1: {"label": "v1", "status": "Approved Date: 2026-05-01"}}
MA = {1: {"label": "v2", "status": "Approved Date: 2026-02-15"}}
M13 = {1: {"label": "v1", "status": "Draft"}, 2: {"label": "v3", "status": "Approved"}}

S, U, W = "supported", "unsupported", "wrong_source"
CASES = [
    ("ERR-5023 answer", "Error ERR-5023 occurs due to the nightly reindex job failing to acquire the chunk table lock [1].", {1: ERR}, None, S),
    ("invented MongoDB claim", "MongoDB is used for storage [1].", {1: V3}, {1: {"label": "v3", "status": "Approved"}}, U),
    ("PDF: restricted sentence", "Restricted documents must not appear in snippets or citations for unauthorized users [1].", {1: POLICY}, MP, S),
    ("PDF: purpose, long answer", "The document defines how organizational documents are classified, owned, approved, indexed, retained, and retired, applying to various types of documents like technical specifications, business procedures, project records, training materials, support documentation, and internal policies [1].", {1: POLICY}, MP, S),
    ("PDF: invented encryption rule", "The policy requires every document to be encrypted [1].", {1: POLICY}, MP, U),
    ("PDF: invented retention number", "Documents are retained for exactly seven years [1].", {1: POLICY}, MP, U),
    ("status true: the draft", "The draft uses keyword search only [1].", {1: V1}, M1, S),
    ("status false: the approved version", "The approved version uses keyword search only [1].", {1: V1}, M1, U),
    ("version true: According to v1", "According to v1, the system is a monolithic FastAPI service [1].", {1: V1}, M1, S),
    ("version false: According to v2", "According to v2, the system is a monolithic FastAPI service [1].", {1: V1}, M1, U),
    ("wrong status: draft vs approved", "According to the draft document, the system is a FastAPI service with a separate ingestion worker [1].", {1: V2}, M2, U),
    ("status true: approved document", "According to the approved document, the system has a separate ingestion worker [1].", {1: V2}, M2, S),
    ("content words draft/approved", "Draft documents should be distinguished from approved documents [1].", {1: ARCH_PDF}, MA, S),
    ("two sources, right citation", "Redis is used for caching [2].", {1: V1, 2: V3}, M13, S),
    ("two sources, wrong citation", "Redis is used for caching [1].", {1: V1, 2: V3}, M13, W),
]

ok = 0
for label, answer, sources, meta, expected in CASES:
    t0 = time.time()
    res = verify_answer(answer, sources, meta)
    verdicts = [r["verdict"] for r in res]
    good = bool(verdicts) and all(v == expected for v in verdicts)
    ok += good
    print(f"{'PASS' if good else 'FAIL'}  {time.time() - t0:5.1f}s  want {expected:<12} got {verdicts}  {label}", flush=True)
    if not good:
        for r in res:
            print("       ", r["verdict"], r["scores"], r.get("note"), "|", r["claim"][:80])
print(f"\n{ok} of {len(CASES)} as expected")
