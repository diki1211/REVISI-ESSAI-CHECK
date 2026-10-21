import json

import pytest
from rdflib import Graph

from autograde import gold, io, ledger
from autograde.io import AG, ANS, KEY
from autograde.score import score
from test_score import ledger_for


@pytest.fixture
def gold_ttl(tmp_path, worked):
    path = tmp_path / "gold.ttl"
    gold.to_graph("Q1", worked["refs"], worked["rubric"]).serialize(path, format="turtle")
    return path


def test_statuses_and_traceability(worked):
    entries = {e.reference_id: e for e in ledger_for(worked, worked["students"])}
    assert [entries[r].status for r in ["R1", "R2", "R3", "R4", "R5"]] == \
        ["MATCHED", "MATCHED", "MISSING", "PARTIAL", "MATCHED"]
    assert entries["R4"].needs_review and not entries["R1"].needs_review
    assert entries["R3"].sentence_ids == [] and entries["R3"].matched_by is None
    assert entries["R2"].sentence_ids == ["Q1_A07_s2"]


def test_contradiction_entry(worked):
    e = {e.reference_id: e for e in ledger_for(worked, worked["variant"])}["R2"]
    assert (e.status, e.contradiction, e.contradicted_by, e.matched_by) == ("CONTRADICTED", True, "Q1_A07_t4", None)
    assert e.sentence_ids == ["Q1_A07_s2"]


@pytest.mark.parametrize("students, lam", [("students", 0.0), ("variant", 0.0), ("variant", 0.5)])
def test_sparql_recompute_matches(worked, tmp_path, gold_ttl, students, lam):
    entries = ledger_for(worked, worked[students])
    ledger.write(tmp_path, "Q1", entries)
    sparql = ledger.recompute_sparql(tmp_path / "ledger.ttl", gold_ttl, lam)
    assert abs(sparql - score("A", entries, {"lambda": lam}).score) < 1e-9


def test_ttl_shape(worked, tmp_path):
    ledger.write(tmp_path, "Q1", ledger_for(worked, worked["students"]))
    g = Graph().parse(tmp_path / "ledger.ttl")
    node = ANS.L_Q1_A07_R5
    assert (node, AG.reference, KEY.Q1_R5) in g and (node, AG.status, AG.Cocok) in g
    assert (node, AG.matchedBy, ANS.Q1_A07_t3) in g
    assert (tmp_path / "ledger.csv").read_text().count("\n") == 6


def test_answer_graph_provenance(worked):
    g = ledger.answer_graph("Q1_A07", worked["students"], [("Q1_A07_s1", "x"), ("Q1_A07_s2", "y")])
    assert (ANS.Q1_A07_t4, io.PROV.wasDerivedFrom, ANS.Q1_A07_s2) in g
    assert (ANS.Q1_A07_t4, AG.hasObject, KEY.CO2) in g
    assert (ANS.Q1_A07_t2, AG.hasObject, KEY.Makanan) in g  # in the alias table since the concept hierarchy
    unknown = ledger.answer_graph("X", [st.model_copy(update={"o_concept": None, "id": "X_t1"})
                                        for st in worked["students"][:1]], [])
    assert (ANS.X_t1, AG.hasObject, ANS.X_t1_o) in unknown  # an unknown concept stays in the answer namespace


def test_override_r3_gives_90(worked, tmp_path, gold_ttl):
    entries = ledger_for(worked, worked["students"])
    ledger.write(tmp_path, "Q1", entries)
    before = (tmp_path / "ledger.json").read_text()
    ov = [{"answer_id": "Q1_A07", "reference_id": "R3", "status": "MATCHED", "reason": "air disebut", "by": "DS",
           "date": "2026-10-21"}]
    fixed = ledger.apply_overrides(entries, ov, worked["params"])
    ledger.write(tmp_path, "Q1", fixed, suffix="_corrected")
    assert score("A", fixed, worked["params"]).score == pytest.approx(90.0)
    assert ledger.recompute_sparql(tmp_path / "ledger_corrected.ttl", gold_ttl, 0.0) == pytest.approx(90.0)
    assert (tmp_path / "ledger.json").read_text() == before
    r3 = json.loads((tmp_path / "ledger_corrected.json").read_text())[2]
    assert r3["override"] == {"by": "DS", "date": "2026-10-21", "reason": "air disebut", "original_status": "MISSING"}
    with pytest.raises(ValueError, match="no ledger entry"):
        ledger.apply_overrides(entries, [{**ov[0], "reference_id": "R9"}], worked["params"])
