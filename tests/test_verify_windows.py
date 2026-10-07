# tests/test_verify_windows.py
"""Evidence windows in verify.py. The real NLI model is replaced by a stand-in that
reproduces the failure measured on the PDF: a claim is recognised only when the premise
is short (<= 40 words); inside a long passage it scores ~0."""
import numpy as np
import pytest
from app import verify

POLICY = (
    "Data Governance and Document Lifecycle Policy Status: Approved Date: 2026-05-01. "
    "Every managed document should have a business owner and a classification label. "
    "Restricted documents must not appear in snippets or citations for unauthorized users. "
    "Missing ownership should trigger a review queue. "
    "Retention periods are set by the document owner. "
    "Archived documents are removed from the active index. "
    "Drafts must be marked so that readers can tell them from approved documents. "
    "Conflicting drafts and approved documents should resolve in favour of approved material.")


def _norm(t):
    return " ".join(t.lower().replace(".", " ").split())


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    calls = []

    def fake(pairs):
        calls.append(len(pairs))
        out = []
        for premise, claim in pairs:
            short = len(premise.split()) <= 40
            out.append(0.99 if short and _norm(claim) in _norm(premise) else 0.01)
        return np.array(out)

    monkeypatch.setattr(verify, "_entailment", fake)
    return calls


def test_sentence_inside_a_long_passage_is_now_supported():
    ans = "Restricted documents must not appear in snippets or citations for unauthorized users. [1]"
    r = verify.verify_answer(ans, {1: POLICY})
    assert r[0]["verdict"] == "supported"
    assert r[0]["scores"][1] >= 0.5
    assert "Restricted documents must not appear" in r[0]["support"][1]


def test_whole_passage_alone_would_have_failed():
    # documents the bug: the old behaviour scored only the full passage
    claim = "Restricted documents must not appear in snippets or citations for unauthorized users."
    assert float(verify._entailment([(POLICY, claim)])[0]) < 0.5


def test_false_claims_stay_unsupported():
    for bad in ["Restricted documents must appear in snippets for all users. [1]",
                "The policy requires every document to be encrypted. [1]",
                "Documents are retained for exactly seven years. [1]"]:
        assert verify.verify_answer(bad, {1: POLICY})[0]["verdict"] == "unsupported"


def test_wrong_source_still_detected():
    other = "Cats are small animals that sleep a lot during the day."
    ans = "Every managed document should have a business owner and a classification label. [1]"
    r = verify.verify_answer(ans, {1: other, 2: POLICY})[0]
    assert r["verdict"] == "wrong_source" and r["better_sources"] == [2]


def test_windows_are_capped_and_include_the_whole_passage():
    claim = "Retention periods are set by the document owner."
    w = verify.candidate_windows(POLICY, claim)
    assert w[0] == " ".join(POLICY.split())
    assert len(w) <= 1 + verify.WINDOW_TOPK
    assert any(claim in x for x in w[1:])        # the matching sentence made the cut


def test_single_short_source_adds_no_duplicate_window():
    w = verify.candidate_windows("Redis caches job queues.", "Redis caches job queues.")
    assert w == ["Redis caches job queues."]


def test_model_calls_are_bounded(fake_model):
    ans = "Retention periods are set by the document owner. [1] Drafts must be marked. [1]"
    verify.verify_answer(ans, {1: POLICY, 2: POLICY})
    # at most (1 whole + TOPK windows) pairs per source per claim, one model call per claim
    assert max(fake_model) <= 2 * (1 + verify.WINDOW_TOPK)


# ---- paragraph-level citations and staged scoring -------------------------------------
def test_one_citation_at_the_end_covers_the_whole_paragraph():
    ans = ("Retention periods are set by the document owner. "
           "Archived documents are removed from the active index. "
           "Drafts must be marked so that readers can tell them from approved documents. [1]")
    claims = verify.split_claims(ans)
    assert [c["cited"] for c in claims] == [[1], [1], [1]]
    r = verify.verify_answer(ans, {1: POLICY})
    assert [x["verdict"] for x in r] == ["supported"] * 3


def test_uncited_trailing_sentence_stays_uncited():
    claims = verify.split_claims("Redis caches job queues [1]. Celery runs the workers.")
    assert [c["cited"] for c in claims] == [[1], []]


def test_wrong_citation_number_is_still_caught():
    ans = ("Retention periods are set by the document owner. "
           "Archived documents are removed from the active index. [2]")
    r = verify.verify_answer(ans, {1: POLICY, 2: "Cats sleep a lot during the day."})
    assert [x["verdict"] for x in r] == ["wrong_source", "wrong_source"]
    assert r[0]["better_sources"] == [1]


def test_supported_claims_do_not_score_the_uncited_sources(fake_model):
    verify.verify_answer("Redis caches job queues. [1]",
                         {1: "Redis caches job queues.", 2: POLICY, 3: POLICY})
    assert fake_model == [1]          # one pair: cited source, whole passage only
