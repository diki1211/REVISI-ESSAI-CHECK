"""Offline demo: every page renders; grading with annotations + template feedback; SPARQL console. No API key."""
import pytest
from streamlit.testing.v1 import AppTest

from autograde import io

pytestmark = pytest.mark.embeddings


@pytest.fixture
def at(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(str(io.ROOT / "app" / "streamlit_app.py"), default_timeout=180).run()
    assert not at.exception, at.exception
    return at


def page(at, name):
    at.sidebar.radio[0].set_value(name).run()
    assert not at.exception, at.exception


def grade(at, qid, answer_prefix):
    at.selectbox[0].set_value(qid).run()
    answer = next(o for o in at.selectbox[1].options if o.startswith(answer_prefix))
    at.selectbox[1].set_value(answer).run()
    at.button[0].click().run()
    assert not at.exception, at.exception


def test_static_pages(at):
    for name in ["Ontologi", "Soal & Kunci", "Usulan Kunci", "Tinjauan Dosen", "Penjelajah Graf", "Konsol SPARQL",
                 "Evaluasi"]:
        page(at, name)


def test_propose_page_rule_draft(at):
    page(at, "Usulan Kunci")
    at.selectbox(key="prop_q").set_value("Q1").run()
    at.button(key="prop_run").click().run()
    assert not at.exception, at.exception
    assert any(m.label == "Kunci yang terliput (recall)" and m.value == "5/5 (1.0)" for m in at.metric)


@pytest.fixture
def clear_cache():
    yield
    import streamlit as st
    st.cache_resource.clear()  # contexts built with the stub embedding must not leak into other tests
    st.cache_data.clear()


def test_review_page_lists_answers_to_review(monkeypatch, tmp_path, clear_cache):
    from autograde import pipeline, review
    from test_pipeline import STUB
    monkeypatch.setattr(pipeline, "runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(review, "overrides_path", lambda: tmp_path / "overrides.yaml")
    orig = pipeline.Context.load.__func__
    monkeypatch.setattr(pipeline.Context, "load",
                        classmethod(lambda cls, q, **k: orig(cls, q, reasoner="sparql", cosine=STUB)))
    pipeline.run_split("Q1", "gold", "all", include_synthetic=True, use_llm_feedback=False, run_id="t")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(str(io.ROOT / "app" / "streamlit_app.py"), default_timeout=180).run()
    page(at, "Tinjauan Dosen")
    assert "Q1_A07" in at.selectbox(key="rev_answer").options
    at.selectbox(key="rev_answer").set_value("Q1_A07").run()
    assert not at.exception, at.exception
    assert any("Aturan 4" in w.value for w in at.warning)
    assert next(m.value for m in at.metric if m.label == "Skor sistem") == "70.0"


def test_grade_q1_and_sparql(at):
    grade(at, "Q1", "Q1_A07")
    assert any("✓ sama" in str(m.delta) for m in at.metric)
    at.button(key="run_ans").click().run()  # first preset: score recompute
    assert not at.exception, at.exception
    assert at.dataframe[-1].value.iloc[0]["score"] == pytest.approx(next(
        float(m.value) for m in at.metric if m.label == "Skor sistem"))


def test_grade_saf_contradiction(at):
    grade(at, "SAF_CSMA", "SAF_CSMA_V002")
    assert next(m.value for m in at.metric if m.label == "Skor sistem") == "0.0"
    assert any("ag:contradicts" in c.value for c in at.code)
