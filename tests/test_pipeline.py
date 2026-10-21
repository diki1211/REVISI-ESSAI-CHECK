import pytest

from autograde import io, ledger, pipeline
from autograde.normalize import make_sim

STUB = lambda a, b: 1.0 if a == b else (0.70 if {a, b} == {"makanan", "glukosa"} else 0.0)


@pytest.fixture
def ctx():
    return pipeline.Context.load("Q1", params={"tau_h": 0.8, "tau_l": 0.6, "delta": 0.5, "lambda": 0.0},
                                 reasoner="sparql", cosine=STUB)


def test_run_answer_gold_mode_writes_everything(ctx, tmp_path):
    text = io.load_yaml(io.ROOT / "tests" / "fixtures" / "worked_example.yaml")["text"]
    res = pipeline.run_answer(ctx, "Q1_A07", text, "gold", tmp_path, use_llm_feedback=False)
    assert res["score"].score == pytest.approx(70.0) and res["score"].sparql_score == pytest.approx(70.0)
    for name in ["ledger.json", "ledger.csv", "ledger.ttl", "answer.ttl", "score.json", "feedback.json",
                 "sentences.json", "student_triples.json", "extraction_log.jsonl"]:
        assert (tmp_path / name).exists(), name


def test_parity_failure_raises(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "recompute_sparql", lambda *a: 12.3)
    with pytest.raises(pipeline.ParityError):
        pipeline.run_answer(ctx, "Q1_A07", "Tumbuhan menyerap sinar matahari.", "gold", tmp_path, use_llm_feedback=False)


def test_completed_runs_skips_files_and_unfinished_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "runs_dir", lambda: tmp_path)
    (tmp_path / ".DS_Store").write_text("x")
    (tmp_path / "20260101-000000_gold_all").mkdir()  # stopped before run.json was written
    done = tmp_path / "20260102-000000_gold_all"
    done.mkdir()
    (done / "run.json").write_text("{}")
    assert pipeline.completed_runs() == [done]


def test_broader_similarity_must_be_partial(ctx):
    import dataclasses
    bad = dataclasses.replace(ctx, broader_similarity=0.9)
    with pytest.raises(ValueError, match="partial band"):
        pipeline.grade(bad, "Q1_A07", [])


def test_skos_preset_finds_the_broader_concept(ctx, tmp_path):
    import rdfviz
    text = io.load_yaml(io.ROOT / "tests" / "fixtures" / "worked_example.yaml")["text"]
    pipeline.run_answer(ctx, "Q1_A07", text, "gold", tmp_path, use_llm_feedback=False)
    g = rdfviz.merged_graph(rdfviz.answer_graph_paths("Q1", tmp_path))
    rows = rdfviz.run_query(g, rdfviz.ANSWER_QUERIES["Kredit parsial karena konsep lebih umum"])
    assert rows.to_dict("records") == [{"entry": "ans:L_Q1_A07_R4", "reference": "key:Q1_R4",
                                        "keyConcept": "key:Glukosa", "studentConcept": "key:Makanan"}]
    for name, query in rdfviz.ANSWER_QUERIES.items():
        rdfviz.run_query(g, query)  # every preset still parses and runs against the new namespaces
