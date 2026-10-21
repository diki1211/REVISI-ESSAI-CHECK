import json

import pytest

from autograde import baselines, gold, llm


@pytest.fixture
def q1():
    g, rubric, refs = gold.load("Q1")
    return g["concepts"], rubric, refs


def test_b1_ignores_predicate(q1):
    concepts, _, refs = q1
    # predicates are wrong ("tidak menghasilkan"), keywords still present -> B1 still gives credit
    text = "Fotosintesis tidak menghasilkan oksigen dan glukosa."
    assert baselines.b1_keyword(text, refs, concepts) == pytest.approx(40.0)
    assert baselines.b1_keyword("Tanaman dan sinar matahari.", refs, concepts) == pytest.approx(20.0)


def test_b2_clamped_and_cached(q1, monkeypatch, tmp_path):
    _, rubric, refs = q1
    monkeypatch.setattr(llm, "cache_dir", lambda: tmp_path)
    assert baselines.b2_llm("Q1", "x", refs, rubric, backend=lambda *a: json.dumps({"score": 130})) == 100.0
