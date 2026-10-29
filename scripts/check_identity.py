from app.verify import _entailment

CLAIM = "Restricted documents must not appear in snippets or citations for unauthorized users."
NEXT = "Missing ownership should trigger a review queue."
PURPOSE = ("This policy defines how organizational documents are classified, owned, approved, "
           "indexed, retained, and retired.")
ERR_SRC = ("Error ERR-5023 means the nightly reindex job could not acquire the chunk table lock. "
           "Retry after the lock_timeout_ms window expires.")

PAIRS = [
    ("control: ERR-5023 answer vs its source", ERR_SRC,
     "Error ERR-5023 occurs due to the nightly reindex job failing to acquire the chunk table lock."),
    ("identical sentence as premise", CLAIM, CLAIM),
    ("sentence + the next sentence", CLAIM + " " + NEXT, CLAIM),
    ("sentence with heading in front", "Ownership and Classification. " + CLAIM, CLAIM),
    ("claim without the negation", "Restricted documents appear in snippets for authorized users.",
     "Restricted documents appear in snippets for authorized users."),
    ("purpose sentence, identical", PURPOSE, PURPOSE),
    ("purpose sentence, 'The document' wording", PURPOSE,
     "The document defines how organizational documents are classified, owned, approved, indexed, retained, and retired."),
    ("simple identical test", "The system uses Redis for caching.", "The system uses Redis for caching."),
]

scores = _entailment([(p, c) for _, p, c in PAIRS])
for (label, _, _), s in zip(PAIRS, scores):
    print(f"{float(s):.2f}  {label}")