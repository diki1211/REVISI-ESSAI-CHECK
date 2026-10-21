"""Cyber law & security questions (HS1-HS3, KS1-KS3): keys validate, demo answers grade as designed (stub sim)."""
import pytest

from autograde import extract, gold, io, pipeline, propose

QUESTIONS = ["HS1", "HS2", "HS3", "KS1", "KS2", "KS3"]
STUB = lambda a, b: 1.0 if a == b else 0.0  # unknown concepts earn nothing: no embedding model needed


@pytest.mark.parametrize("qid", QUESTIONS)
def test_key_validates_and_is_flagged(qid):
    gold_raw, rubric, refs = gold.load(qid)
    assert gold_raw["drafted_by"] and gold_raw["validated_by"] is None  # AI draft until a lecturer validates it
    assert rubric["language"] == "id" and refs
    assert "Sumber:" in (io.question_dir(qid) / "question.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("qid", QUESTIONS)
def test_reference_answer_states_every_key_triple(qid):
    """Consistency check of the draft (not a finding): the rule draft of the reference answer recovers the key."""
    c = propose.propose(qid, "rule")["comparison"]
    assert c["recall"] == 1.0 and c["precision"] == 1.0


def grade(answer_id):
    qid = answer_id.split("_")[0]
    ctx = pipeline.Context.load(qid, reasoner="sparql", cosine=STUB)
    _, entries, sc, trace = pipeline.grade(ctx, answer_id, extract.extract_gold(answer_id))
    return {e.reference_id: e.status for e in entries}, sc.score, [(g.reference_id, g.premise_id) for g in trace["premise_gaps"]]


@pytest.mark.parametrize("answer_id, contradicted", [("HS1_S02", "R1"), ("HS3_S02", "R1"), ("KS1_S02", "R1"),
                                                     ("KS2_S02", "R7")])
def test_contradiction_demos(answer_id, contradicted):
    status, _, _ = grade(answer_id)
    assert [r for r, s in status.items() if s == "CONTRADICTED"] == [contradicted]


@pytest.mark.parametrize("answer_id, gap", [("HS3_S01", ("R1", "R3")), ("KS3_S01", ("R4", "R3"))])
def test_premise_gap_demos(answer_id, gap):
    _, _, gaps = grade(answer_id)
    assert gaps == [gap]


def test_complete_answer_without_embeddings():
    status, score, gaps = grade("KS2_S01")  # every concept is in the alias table
    assert score == pytest.approx(800 / 9) and status["R7"] == "MISSING" and gaps == []


def test_role_swap_is_missing_not_contradicted():
    status, score, _ = grade("HS2_S02")  # open world: a wrong subject is "not found", never a contradiction
    assert score == 0.0 and set(status.values()) == {"MISSING"}
