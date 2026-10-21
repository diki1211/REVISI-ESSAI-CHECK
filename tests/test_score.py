import pytest

from autograde import ledger
from autograde.match import contradictions, match
from autograde.score import score


def ledger_for(worked, students):
    refs, p = worked["refs"], worked["params"]
    results, sigmas, _ = match(refs, students, p, worked["sim"], worked["rel"])
    contra = contradictions(refs, students, sigmas, p, worked["rel"])
    return ledger.build("Q1_A07", refs, results, sigmas, contra, students, p)


def test_worked_example_70(worked):
    s = score("Q1_A07", ledger_for(worked, worked["students"]), worked["params"])
    assert s.score == pytest.approx(70.0) and s.sum_weighted_credit == 7 and s.sum_weights == 10


def test_contradiction_variant_50_and_40(worked):
    entries = ledger_for(worked, worked["variant"])
    assert score("A", entries, {**worked["params"], "lambda": 0.0}).score == pytest.approx(50.0)
    assert score("A", entries, {**worked["params"], "lambda": 0.5}).score == pytest.approx(40.0)


def test_clamped_at_zero():
    from autograde.models import LedgerEntry
    e = LedgerEntry(entry_id="L", answer_id="A", reference_id="R1", criterion="K", weight=2, status="CONTRADICTED",
                    credit=0, contradiction=True, matched_by=None, contradicted_by="A_t1", sigma=1.0,
                    sentence_ids=["A_s1"], needs_review=False)
    assert score("A", [e], {"lambda": 1.0}).score == 0.0
