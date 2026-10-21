from autograde.match import Relations, contradictions, match
from autograde.models import ReferenceTriple, StudentTriple
from autograde.normalize import make_sim


def test_worked_example_credits(worked):
    results, _, _ = match(worked["refs"], worked["students"], worked["params"], worked["sim"], worked["rel"])
    assert {k: v.credit for k, v in results.items()} == worked["fx"]["expected_credit"]
    assert results["R1"].matched_by == "Q1_A07_t1"  # menyerap ≡ menggunakan via the ontology
    assert results["R4"].matched_by == "Q1_A07_t2" and results["R4"].sigma == 0.70
    assert results["R3"].matched_by is None and results["R3"].sigma is None


def test_contradiction_variant(worked):
    results, sigmas, aligned = match(worked["refs"], worked["variant"], worked["params"], worked["sim"], worked["rel"])
    assert results["R2"].credit == 0.0
    assert ("Q1_A07_t4", "R2") in aligned
    assert contradictions(worked["refs"], worked["variant"], sigmas, worked["params"], worked["rel"]) == {("Q1_A07_t4", "R2")}


def test_known_different_concepts_sigma_zero(worked):
    _, sigmas, _ = match(worked["refs"], worked["students"], worked["params"], worked["sim"], worked["rel"])
    assert sigmas["Q1_A07_t3", "R4"] == 0.0  # oksigen vs Glukosa


REL = Relations(eq={"p": {"p"}}, inc=set())
P = {"tau_h": 0.8, "tau_l": 0.6, "delta": 0.5}
REF = ReferenceTriple(id="R1", s="A", p="p", o="B", criterion="K", weight=1)
SIM = make_sim(lambda a, b: 1.0 if a == b else 0.0)


def st(i, sent, neg=False):
    return StudentTriple(id=f"X_t{i}", answer_id="X", s_text="a", p="p", o_text="b", negated=neg,
                         sentence_ids=[f"X_s{sent}"], s_concept="A", o_concept="B")


def test_tie_break_lowest_sentence_then_triple():
    results, _, _ = match([REF], [st(1, 3), st(2, 2), st(3, 2)], P, SIM, REL)
    assert results["R1"].matched_by == "X_t2"


def test_negated_never_gets_credit():
    results, sigmas, _ = match([REF], [st(1, 1, neg=True)], P, SIM, REL)
    assert results["R1"].credit == 0.0
    assert contradictions([REF], [st(1, 1, neg=True)], sigmas, P, REL) == {("X_t1", "R1")}


def test_empty_student_graph():
    results, _, aligned = match([REF], [], P, SIM, REL)
    assert results["R1"].credit == 0.0 and aligned == []
