# scripts/verify_four.py
from app.verify import verify_answer, split_claims

SOURCES = {
    1: "(test report page 2, text not included)",
    2: "We decided to introduce vector search because keyword search missed conceptual questions from users.",
    3: "The system is a monolithic FastAPI service. Retrieval uses keyword search only.",
}
ANSWER = "[3] The system is a monolithic FastAPI service. Retrieval uses keyword search only. [3]"

print("claims found:", len(split_claims(ANSWER)))
for r in verify_answer(ANSWER, SOURCES):
    print(r["verdict"], r["cited"], r["scores"])
    print(" ", r["claim"])