"""Lecturer review: overrides.yaml written per answer, corrected copies recomputed, originals untouched."""
import pytest
from rdflib import Graph

from autograde import io, pipeline, review
from autograde.cli import main
from autograde.io import AG, ANS
from test_pipeline import STUB


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(review, "overrides_path", lambda: tmp_path / "human" / "overrides.yaml")
    orig = pipeline.Context.load.__func__
    monkeypatch.setattr(pipeline.Context, "load",
                        classmethod(lambda cls, q, **k: orig(cls, q, reasoner="sparql", cosine=STUB)))
    return pipeline.run_split("Q1", "gold", "all", include_synthetic=True, use_llm_feedback=False, run_id="t")


def test_queue_flags_answers_to_review(run):
    q = review.queue("t").set_index("answer_id")
    a07 = q.loc["Q1_A07"]
    assert (a07.partial, a07.contradicted, a07.premise_gaps, bool(a07.needs_review)) == (1, 0, 1, True)
    assert a07.score == pytest.approx(70.0) and a07.corrected_score is None and not a07.has_overrides


def test_save_and_apply_keeps_original(run):
    entries = review.load_entries(run, "Q1_A07")
    before = (run / "Q1_A07" / "ledger.json").read_bytes()
    mine = review.save_corrections("Q1_A07", {"R3": ("MATCHED", "air disebut tersirat"), "R1": ("MATCHED", "")},
                                   entries, by="Dosen A", on="2026-10-21")
    assert mine == [{"answer_id": "Q1_A07", "reference_id": "R3", "status": "MATCHED",
                     "reason": "air disebut tersirat", "by": "Dosen A", "date": "2026-10-21"}]  # R1 unchanged: dropped
    [row] = review.apply_run("t", ["Q1_A07"])
    assert (row["original"], row["corrected"]) == (pytest.approx(70.0), pytest.approx(90.0))
    assert (run / "Q1_A07" / "ledger.json").read_bytes() == before
    assert io.load_json(run / "Q1_A07" / "score.json")["score"] == pytest.approx(70.0)
    corrected = io.load_json(run / "Q1_A07" / "score_corrected.json")
    assert corrected["score"] == pytest.approx(corrected["sparql_score"])
    g = Graph().parse(run / "Q1_A07" / "ledger_corrected.ttl")
    assert (ANS.L_Q1_A07_R4, AG.lacksPremise, None) not in g  # R3 now credited: the premise gap is closed
    assert review.queue("t").set_index("answer_id").loc["Q1_A07", "corrected_score"] == pytest.approx(90.0)


def test_other_answers_kept_and_reset_removes(run):
    a07, a08 = review.load_entries(run, "Q1_A07"), review.load_entries(run, "Q1_A08")
    review.save_corrections("Q1_A07", {"R3": ("MATCHED", "x")}, a07, by="D")
    review.save_corrections("Q1_A08", {"R1": ("MISSING", "tidak relevan")}, a08, by="D")
    review.apply_run("t")
    assert {o["answer_id"] for o in review.load_overrides()} == {"Q1_A07", "Q1_A08"}
    review.save_corrections("Q1_A07", {"R3": ("MISSING", "")}, a07, by="D")  # back to the system's status
    [row] = review.apply_run("t", ["Q1_A07"])
    assert row["corrected"] is None and not (run / "Q1_A07" / "score_corrected.json").exists()
    assert [o["answer_id"] for o in review.load_overrides()] == ["Q1_A08"]


@pytest.mark.parametrize("corr, by, msg", [({"R3": ("MATCHED", "")}, "D", "missing reason"),
                                           ({"R3": ("MATCHED", "x")}, "", "missing by"),
                                           ({"R3": ("BENAR", "x")}, "D", "unknown status"),
                                           ({"R9": ("MATCHED", "x")}, "D", "no ledger entry")])
def test_invalid_corrections_rejected(run, corr, by, msg):
    with pytest.raises(review.OverrideError, match=msg):
        review.save_corrections("Q1_A07", corr, review.load_entries(run, "Q1_A07"), by=by)
    assert review.load_overrides() == []


def test_cli_override_uses_same_path(run, capsys):
    review.save_corrections("Q1_A07", {"R3": ("MATCHED", "x")}, review.load_entries(run, "Q1_A07"), by="D")
    io.save_yaml(review.load_overrides() + [{"answer_id": "Q1_X99", "reference_id": "R1", "status": "MATCHED",
                                             "reason": "x", "by": "D", "date": "2026-10-21"}],
                 review.overrides_path())
    main(["override", "--run", "t"])
    out = capsys.readouterr().out
    assert "Q1_A07: 70.0 -> 90.0 (corrected)" in out and "Q1_X99: not in run t, skipped" in out
