import numpy as np
import pandas as pd
import pytest

from autograde import evaluate, io, pipeline
from test_pipeline import STUB


def test_human_totals_weighted_mean_over_raters():
    scores = pd.DataFrame({"answer_id": ["A"] * 4, "rater_id": ["D1", "D1", "D2", "D2"],
                           "criterion": ["K1", "K2", "K1", "K2"], "score_0_100": [100, 0, 50, 0]})
    totals = evaluate.human_totals(scores, {"Q": {"K1": 3, "K2": 1}}, {"A": "Q"})
    assert totals["A"] == pytest.approx(75 * 3 / 4)
    with pytest.raises(ValueError, match="no human score"):
        evaluate.human_totals(scores, {"Q": {"K1": 3, "K3": 1}}, {"A": "Q"})


def test_icc_perfect_and_known_value():
    assert evaluate.icc_2_1([[1, 1], [2, 2], [3, 3]]) == pytest.approx(1.0)
    # Shrout & Fleiss (1979) example: ICC(2,1) = 0.29
    sf = [[9, 2, 5, 8], [6, 1, 3, 2], [8, 4, 6, 8], [7, 1, 2, 6], [10, 5, 6, 9], [6, 2, 4, 7]]
    assert evaluate.icc_2_1(sf) == pytest.approx(0.29, abs=0.005)


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "runs_dir", lambda: tmp_path)
    orig = pipeline.Context.load.__func__
    monkeypatch.setattr(pipeline.Context, "load",
                        classmethod(lambda cls, q, **k: orig(cls, q, reasoner="sparql", cosine=STUB)))
    run_dir = pipeline.run_split("Q1", "gold", "all", include_synthetic=True, use_llm_feedback=False, run_id="t")
    return run_dir


def test_evaluate_synthetic_and_deterministic(synthetic_run):
    fail_b2 = lambda *a: (_ for _ in ()).throw(evaluate.llm.LLMUnavailable("no key"))
    report = evaluate.evaluate("t", b2_backend=fail_b2)
    first = (synthetic_run / "metrics.csv").read_bytes()
    evaluate.evaluate("t", b2_backend=fail_b2)
    assert (synthetic_run / "metrics.csv").read_bytes() == first
    text = report.read_text()
    assert "SYNTHETIC DATA" in text and "B2 LLM-only not computed" in text
    metrics = pd.read_csv(synthetic_run / "metrics.csv")
    assert set(metrics.system) == {"System (gold mode)", "System (gold mode), λ = 0.5", "B1 keyword"}


def test_unfrozen_real_run_refused(synthetic_run):
    run = io.load_json(synthetic_run / "run.json")
    io.save_json({**run, "include_synthetic": False, "params_frozen": False}, synthetic_run / "run.json")
    with pytest.raises(evaluate.NotFrozenError):
        evaluate.evaluate("t")


def test_audit_template_and_metrics(synthetic_run, monkeypatch, tmp_path):
    template = pd.read_csv(evaluate.audit_template("t"), dtype=str).fillna("")
    led = template.row_type == "ledger"
    template.loc[led, "present_in_answer"] = "yes"
    template.loc[led & template.status.isin(["MATCHED", "PARTIAL"]), "evidence_correct"] = "yes"
    template.loc[template.row_type == "claim", "supported"] = "no"
    human = tmp_path / "root" / "data" / "human"
    human.mkdir(parents=True)
    template.to_csv(human / "evidence_audit.csv", index=False)
    monkeypatch.setattr(io, "ROOT", tmp_path / "root")
    m = evaluate.audit_metrics("t")
    hits = (led & template.status.isin(["MATCHED", "PARTIAL"])).sum()
    assert m["EP"] == (1.0, hits)
    assert m["ER"][0] == pytest.approx(hits / led.sum())
    assert m["FF"][0] == 0.0
