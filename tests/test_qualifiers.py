from app.verify import split_qualifiers, meta_mismatch, split_claims, verify_answer

def test_leading_version_is_removed_and_recorded():
    text, v, s = split_qualifiers("According to v2, the system stores embeddings.")
    assert text == "The system stores embeddings." and v == ["v2"] and s == []

def test_subject_status_is_replaced():
    text, v, s = split_qualifiers("The draft uses keyword search only.")
    assert text == "The system uses keyword search only." and s == ["draft"] and v == []

def test_status_words_in_content_are_left_alone():
    claim = "Draft documents should be distinguished from approved documents."
    assert split_qualifiers(claim) == (claim, [], [])

def test_versions_in_paths_and_numbers_are_ignored():
    for t in ("POST /api/v1/query asks a question.", "TLS version 1.2 is required."):
        assert split_qualifiers(t)[1] == []

def test_mismatch_detects_wrong_status_and_version():
    meta = {1: {"label": "v2", "status": "Approved"}}
    assert meta_mismatch(["v1"], [], [1], meta)
    assert meta_mismatch([], ["draft"], [1], meta)
    assert not meta_mismatch(["v2"], ["approved"], [1], meta)
    assert not meta_mismatch(["v1"], [], [], meta)        # no citation: nothing to compare
    assert not meta_mismatch(["v1"], [], [1], None)       # no metadata given

def test_status_stored_with_a_date_still_matches():
    meta = {1: {"label": "v2", "status": "Approved Date: 2026-02-15"}}
    assert not meta_mismatch([], ["approved"], [1], meta)

def test_attribution_sentence_is_not_split():
    claims = split_claims("According to the draft document, the system has a separate ingestion worker [1].")
    assert len(claims) == 1 and claims[0]["cited"] == [1]

def test_wrong_status_is_unsupported_without_calling_the_model():
    meta = {1: {"label": "v2", "status": "Approved"}}
    r = verify_answer("According to the draft document, the system has a separate ingestion worker [1].",
                      {1: "The system has a separate ingestion worker."}, meta)
    assert r[0]["verdict"] == "unsupported" and r[0]["note"]
