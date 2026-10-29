from app.verify import split_claims, verify_answer

SOURCE = (
    "Data Governance and Document Lifecycle Policy\n"
    "Status: Approved Date: 2026-05-01\n"
    "Author: Data Governance Office\n"
    "Purpose and Scope\n"
    "This policy defines how organizational documents are classified, owned, approved, "
    "indexed, retained, and retired. It applies to technical specifications, business "
    "procedures, project records, training materials, support documentation, and internal policies."
)
ANSWERS = [
    "The document defines how organizational documents are classified, owned, approved, indexed, retained, and retired, applying to various types of documents like technical specifications, business procedures, project records, training materials, support documentation, and internal policies [2].",
    "The document defines how organizational documents are classified, owned, approved, indexed, retained, and retired [2].",
    "The policy applies to technical specifications, business procedures, project records, training materials, support documentation, and internal policies [2].",
]
for a in ANSWERS:
    print(a[:90] + "...")
    print("  claims after splitting:", len(split_claims(a)))
    for r in verify_answer(a, {2: SOURCE}):
        print(f"  {r['verdict']:<12} {r['scores']}  {r['claim'][:70]}")
