"""SAF subset: gold files validate, annotations load, English extraction prompt, holistic scores."""
import json

import pandas as pd
import pytest

from autograde import evaluate, extract, gold, io, llm, pipeline

SAF_QUESTIONS = ["SAF_CSMA", "SAF_DHCP", "SAF_DLL", "SAF_PIGGY", "SAF_SYNC"]
STUB = lambda a, b: 1.0 if a == b else 0.0


def test_all_questions_validate():
    assert set(SAF_QUESTIONS) <= set(io.question_ids())
    for q in io.question_ids():
        _, rubric, refs = gold.load(q)
        assert refs and rubric.get("language", "id") in ("id", "en")


def test_saf_answers_and_scores_line_up():
    answers = io.load_answers(include_saf=True)
    saf = answers[answers.source == "saf"]
    scores = io.load_human_scores(include_saf=True)
    assert set(SAF_QUESTIONS) <= set(saf.question_id) and set(saf.split) == {"pilot", "test"}
    assert set(saf.question_id) <= set(io.question_ids())  # every imported question has a key
    assert set(saf.answer_id) == set(scores[scores.criterion == io.TOTAL].answer_id)
    assert io.load_answers().empty or "saf" not in set(io.load_answers().source)  # only on request


def test_holistic_total_used_directly():
    scores = pd.DataFrame({"answer_id": ["A"], "rater_id": ["SAF"], "criterion": [io.TOTAL], "score_0_100": [75.0]})
    assert evaluate.human_totals(scores, {"Q": {"K1": 1}}, {"A": "Q"})["A"] == 75.0


def test_english_extraction_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "cache_dir", lambda: tmp_path)
    seen = {}

    def backend(system, user, schema, cfg):
        seen.update(system=system, user=user, enum=schema["properties"]["triples"]["items"]["properties"]["predicate"]["enum"])
        return json.dumps({"triples": [{"sentence_ids": ["S1"], "subject": "diameter", "predicate": "shrinks",
                                        "object": "factor of 10", "negated": False}]})
    kept, _ = extract.extract_llm("SAF_CSMA_X001", [("SAF_CSMA_X001_s1", "The diameter shrinks by a factor of 10.")],
                                  backend=backend, language="en")
    assert "written in English" in seen["system"] and "UDP is a transport protocol" in seen["user"]
    assert "lacks" in seen["enum"] and "menggunakan" not in seen["enum"] and "other" in seen["enum"]
    assert kept[0].p == "decreases"


def test_annotated_contradiction_is_stored_as_rdf(tmp_path):
    ctx = pipeline.Context.load("SAF_CSMA", reasoner="sparql", cosine=STUB)
    text = io.load_answers(include_saf=True).set_index("answer_id").text["SAF_CSMA_V002"]
    res = pipeline.run_answer(ctx, "SAF_CSMA_V002", text, "gold", tmp_path, use_llm_feedback=False)
    assert res["entries"][0].status == "CONTRADICTED" and res["score"].score == 0.0
    ttl = (tmp_path / "answer.ttl").read_text()
    assert "ag:contradicts key:SAF_CSMA_R1" in ttl and "ag:alignedSubject key:SAF_CSMA_R1" in ttl


@pytest.mark.parametrize("answer_id", sorted(p.stem for p in (io.SAF_DIR / "annotations").glob("*.yaml")))
def test_annotations_load_and_say_who_wrote_them(answer_id):
    assert "AI" in io.load_yaml(io.annotation_path(answer_id))["annotated_by"]
    extract.extract_gold(answer_id)
