"""Rule 4: premise gaps (a credited conclusion without its credited premises). Never changes the score."""
import copy
import itertools
import json

import pytest
from rdflib import Graph

from autograde import feedback, gold, io, ledger, llm, pipeline, premise, reason
from autograde.io import AG, ANS, KEY
from autograde.models import Feedback, LedgerEntry, ReferenceTriple
from autograde.score import score
from test_feedback import SENTS
from test_gold import RELS
from test_pipeline import STUB
from test_score import ledger_for

STATUSES = ["MATCHED", "PARTIAL", "MISSING", "CONTRADICTED"]


def test_q1_declares_premises():
    _, _, refs = gold.load("Q1")
    assert premise.links(refs) == [("R4", "R2"), ("R4", "R3")]


@pytest.mark.parametrize("requires, msg", [(["R9"], "unknown reference triple"), (["R4"], "requires itself")])
def test_requires_validation(requires, msg):
    d = io.question_dir("Q1")
    g, rubric = copy.deepcopy(io.load_yaml(d / "gold.yaml")), io.load_yaml(d / "rubric.yaml")
    g["triples"][3]["requires"] = requires
    with pytest.raises(gold.GoldError, match=msg):
        gold.validate(g, rubric, RELS)


def test_requires_cycle_rejected():
    d = io.question_dir("Q1")
    g, rubric = copy.deepcopy(io.load_yaml(d / "gold.yaml")), io.load_yaml(d / "rubric.yaml")
    g["triples"][1]["requires"] = ["R4"]  # R4 requires R2 already
    with pytest.raises(gold.GoldError, match="premise cycle"):
        gold.validate(g, rubric, RELS)


def test_gold_ttl_has_requires_premise(worked):
    g = gold.to_graph("Q1", worked["refs"], worked["rubric"])
    assert (KEY.Q1_R4, AG.requiresPremise, KEY.Q1_R3) in g and (KEY.Q1_R4, AG.requiresPremise, KEY.Q1_R2) in g


def test_worked_example_gap(worked):
    entries = ledger_for(worked, worked["students"])  # R2 MATCHED, R3 MISSING, R4 PARTIAL
    gaps = premise.gaps(worked["refs"], entries)
    assert [(g.reference_id, g.premise_id, g.premise_status) for g in gaps] == [("R4", "R3", "MISSING")]
    assert gaps[0].entry_id == "L_Q1_A07_R4" and gaps[0].premise_entry_id == "L_Q1_A07_R3"


def test_contradicted_premise_is_a_gap(worked):
    entries = ledger_for(worked, worked["variant"])  # R2 CONTRADICTED
    assert {(g.premise_id, g.premise_status) for g in premise.gaps(worked["refs"], entries)} == \
        {("R2", "CONTRADICTED"), ("R3", "MISSING")}


@pytest.fixture
def ctx():
    return pipeline.Context.load("Q1", params={"tau_h": 0.8, "tau_l": 0.6, "delta": 0.5, "lambda": 0.0},
                                 reasoner="sparql", cosine=STUB)


def test_score_unchanged_by_premises(ctx, worked):
    import dataclasses
    plain = dataclasses.replace(ctx, refs=[r.model_copy(update={"requires": []}) for r in ctx.refs])
    _, with_req, s1, t1 = pipeline.grade(ctx, "Q1_A07", worked["students"])
    _, without, s2, t2 = pipeline.grade(plain, "Q1_A07", worked["students"])
    assert with_req == without and s1.score == s2.score == pytest.approx(70.0)
    assert len(t1["premise_gaps"]) == 1 and t2["premise_gaps"] == []


def test_run_answer_writes_lacks_premise(ctx, tmp_path):
    text = io.load_yaml(io.ROOT / "tests" / "fixtures" / "worked_example.yaml")["text"]
    res = pipeline.run_answer(ctx, "Q1_A07", text, "gold", tmp_path, use_llm_feedback=False)
    g = Graph().parse(tmp_path / "ledger.ttl")
    assert (ANS.L_Q1_A07_R4, AG.lacksPremise, ANS.L_Q1_A07_R3) in g
    assert ledger.recompute_sparql(tmp_path / "ledger.ttl", io.question_dir("Q1") / "gold.ttl", 0.0) == \
        pytest.approx(70.0)  # the extra links do not touch the SPARQL score
    assert io.load_json(tmp_path / "trace.json")["premise_gaps"][0]["premise_id"] == "R3"
    assert res["feedback"].claims[-1].kind == "premise"


def entries_for(answer, statuses):
    return [LedgerEntry(entry_id=f"L_{answer}_{r}", answer_id=answer, reference_id=r, criterion="K", weight=1,
                        status=st, credit=0.0, contradiction=st == "CONTRADICTED", matched_by=None,
                        contradicted_by=None, sigma=None, sentence_ids=[], needs_review=False)
            for r, st in statuses.items()]


REFS = [ReferenceTriple(id="R1", s="A", p="a", o="B", criterion="K", weight=1),
        ReferenceTriple(id="R2", s="A", p="a", o="C", criterion="K", weight=1),
        ReferenceTriple(id="R3", s="A", p="a", o="D", criterion="K", weight=1, requires=["R1", "R2"])]
CASES = list(itertools.product(STATUSES, STATUSES, STATUSES))  # (R1, R2, R3) statuses


def expected(st):
    if st[2] not in premise.CREDITED:
        return set()
    return {("R3", p) for p, s in zip(["R1", "R2"], st[:2]) if s not in premise.CREDITED}


def test_sparql_matches_python():
    for i, st in enumerate(CASES):
        entries = entries_for(f"P{i}_A", dict(zip(["R1", "R2", "R3"], st)))
        assert reason.premise_gaps_sparql("Q9", REFS, entries) == premise.gap_pairs(REFS, entries) == expected(st), st


def test_no_requires_skips_reasoner(monkeypatch):
    monkeypatch.setattr(reason, "premise_gaps_sparql", lambda *a: pytest.fail("reasoner called"))
    assert reason.premise_gaps("Q9", REFS[:2], entries_for("A", {"R1": "MATCHED", "R2": "MISSING"}), "sparql") == set()


@pytest.mark.pellet
def test_pellet_matches_python():
    pellet = reason.PelletReasoner()
    for i, st in enumerate(CASES[::4] + [("MISSING", "CONTRADICTED", "PARTIAL")]):
        entries = entries_for(f"P{i}_A", dict(zip(["R1", "R2", "R3"], st)))
        assert pellet.premise_gaps("Q9", REFS, entries) == expected(st), st
    assert pellet.residue() == []


@pytest.fixture
def tmp_cache(monkeypatch, tmp_path):
    counter = iter(range(1000))
    monkeypatch.setattr(llm, "cache_dir", lambda: tmp_path / str(next(counter)))


def test_template_premise_claim_validates(worked):
    entries = ledger_for(worked, worked["students"])
    gaps = premise.gaps(worked["refs"], entries)
    fb = feedback.template("Q1_A07", entries, worked["refs"], 70.0, gaps)
    assert [c.kind for c in fb.claims] == ["missing", "partial", "correct", "premise"]
    assert fb.claims[-1].ledger_entry_ids == ["L_Q1_A07_R4", "L_Q1_A07_R3"]
    assert "tidak mengurangi skor" in fb.claims[-1].text
    assert feedback.validate(fb, entries, 70.0, gaps) == []


def test_premise_claim_without_gap_rejected(worked):
    entries = ledger_for(worked, worked["students"])
    gaps = premise.gaps(worked["refs"], entries)
    bad = Feedback(answer_id="Q1_A07", summary="ok", claims=[
        {"text": "x", "kind": "premise", "ledger_entry_ids": ["L_Q1_A07_R5", "L_Q1_A07_R3"]}])
    assert any("no recorded premise gap" in e for e in feedback.validate(bad, entries, 70.0, gaps))
    assert any("no recorded premise gap" in e for e in feedback.validate(bad, entries, 70.0, []))
    stray = Feedback(answer_id="Q1_A07", summary="ok", claims=[
        {"text": "x", "kind": "premise", "ledger_entry_ids": ["L_Q1_A07_R4", "L_Q1_A07_R3", "L_Q1_A07_R1"]}])
    assert any("L_Q1_A07_R1 is in no premise gap" in e for e in feedback.validate(stray, entries, 70.0, gaps))


def test_llm_premise_claim_accepted(worked, tmp_cache):
    entries = ledger_for(worked, worked["students"])
    gaps = premise.gaps(worked["refs"], entries)
    reply = {"summary": "Skor 70,0.", "claims": [
        {"text": "Kamu menyebut glukosa, tetapi belum menjelaskan bahwa air dipakai.", "kind": "premise",
         "ledger_entry_ids": ["L_Q1_A07_R4", "L_Q1_A07_R3"]}]}
    seen = {}

    def backend(system, user, schema, cfg):
        seen.update(system=system, schema=schema, user=user)
        return json.dumps(reply)

    fb = feedback.generate("Q1_A07", entries, worked["refs"], worked["rubric"], SENTS, 70.0, backend=backend,
                           gaps=gaps)
    assert fb.source == "llm" and fb.claims[0].kind == "premise"
    assert 'kind "premise"' in seen["system"] and "missing_premises" in seen["user"]
    assert "premise" in seen["schema"]["properties"]["claims"]["items"]["properties"]["kind"]["enum"]


def test_no_gaps_keeps_prompt_unchanged(worked, tmp_cache):
    entries = ledger_for(worked, worked["students"])
    seen = {}

    def backend(system, user, schema, cfg):
        seen.update(system=system, schema=schema)
        return json.dumps({"summary": "ok", "claims": []})

    feedback.generate("Q1_A07", entries, worked["refs"], worked["rubric"], SENTS, 70.0, backend=backend)
    assert seen["system"] == feedback.SYSTEM
    assert "premise" not in seen["schema"]["properties"]["claims"]["items"]["properties"]["kind"]["enum"]
    assert score("A", entries, worked["params"]).score == pytest.approx(70.0)
