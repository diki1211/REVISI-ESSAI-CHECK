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
    for name in ["Ontologi", "Soal & Kunci", "Penjelajah Graf", "Konsol SPARQL", "Evaluasi"]:
        page(at, name)


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
