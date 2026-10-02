from app.verify import split_compound, split_claims

def test_list_sentence_is_split_with_the_lead_repeated():
    parts = split_compound(
        "The system uses PostgreSQL with pgvector, Redis, a reranking stage and Celery workers.")
    assert len(parts) == 4
    assert parts[1] == "The system uses Redis"
    assert parts[3] == "The system uses Celery workers"

def test_two_full_clauses_are_split():
    parts = split_compound(
        "Documents are chunked by heading; embeddings are stored in the database.")
    assert len(parts) == 2

def test_unclear_sentence_is_not_split():
    assert len(split_compound("The API reads and writes data.")) == 1

def test_each_sub_claim_keeps_the_citation():
    claims = split_claims("The system uses Redis and Celery workers [2].")
    assert [c["cited"] for c in claims] == [[2], [2]]
    assert claims[1]["text"] == "The system uses Celery workers."