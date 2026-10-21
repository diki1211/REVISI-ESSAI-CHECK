"""Graph-level comparison metrics (B3 exact triple, G1 graph F1, G2 graph edit similarity)."""
import pytest

from autograde import graphsim


def test_worked_example(worked):
    m = graphsim.all_metrics(worked["refs"], worked["students"], worked["rel"])
    # exact ids: R1 (menyerap ≡ menggunakan), R2 and R5 found; Makanan is not Glukosa, Air is missing -> 6/10
    assert m["B3 exact triple"] == pytest.approx(60.0)
    assert m["G1 graph F1"] == pytest.approx(100 * 2 * 0.75 * 0.6 / 1.35)  # 3 of 4 student edges are key edges
    # key 7 nodes + 5 edges, student 6 + 4; delete Air and its edge (2), relabel Glukosa -> Makanan (1),
    # move the product edge from Fotosintesis to Tumbuhan (2)
    assert m["G2 graph edit similarity"] == pytest.approx(100 * (1 - 5 / 22))


def test_accepted_subject_renamed(worked):
    edges = graphsim.student_edges(worked["students"], worked["refs"], worked["rel"])
    assert ("Fotosintesis", "mengonsumsi", "CO2") in edges  # "tumbuhan mengonsumsi" uses R2's accepted subject
    assert ("Tumbuhan", "menyerap", "Cahaya") in edges     # R1 lists Tumbuhan first


def test_identical_and_empty_graphs(worked):
    from autograde.models import StudentTriple
    perfect = [StudentTriple(id=f"A_t{i}", answer_id="A", s_text=r.s[0], p=r.p, o_text=r.o, s_concept=r.s[0],
                             o_concept=r.o, sentence_ids=["A_s1"]) for i, r in enumerate(worked["refs"], 1)]
    assert graphsim.all_metrics(worked["refs"], perfect, worked["rel"]) == \
        {"B3 exact triple": 100.0, "G1 graph F1": 100.0, "G2 graph edit similarity": 100.0}
    assert graphsim.all_metrics(worked["refs"], [], worked["rel"]) == \
        {"B3 exact triple": 0.0, "G1 graph F1": 0.0, "G2 graph edit similarity": 0.0}


def test_negated_and_unknown(worked):
    from autograde.models import StudentTriple
    negated = [t.model_copy(update={"negated": True}) for t in worked["students"]]
    assert graphsim.exact_triple_score(worked["refs"], negated, worked["rel"]) == 0.0
    unknown = StudentTriple(id="A_t1", answer_id="A", s_text="daun", p="menghasilkan", o_text="gula pasir",
                            sentence_ids=["A_s1"])
    assert graphsim.student_edges([unknown], worked["refs"], worked["rel"]) == [("?daun", "menghasilkan", "?gula pasir")]


def test_extra_edges_lower_f1_not_recall(worked):
    from autograde.models import StudentTriple
    extra = worked["students"] + [StudentTriple(id="Q1_A07_t9", answer_id="Q1_A07", s_text="tumbuhan", p="menyerap",
                                                o_text="air tanah", s_concept="Tumbuhan", sentence_ids=["Q1_A07_s2"])]
    rel, refs = worked["rel"], worked["refs"]
    assert graphsim.exact_triple_score(refs, extra, rel) == graphsim.exact_triple_score(refs, worked["students"], rel)
    assert graphsim.graph_f1(refs, extra, rel) < graphsim.graph_f1(refs, worked["students"], rel)
