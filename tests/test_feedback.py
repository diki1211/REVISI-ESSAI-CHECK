import json

import pytest

from autograde import feedback, llm
from test_score import ledger_for

SENTS = [("Q1_A07_s1", "Tumbuhan menyerap sinar matahari dan menghasilkan makanan serta oksigen."),
         ("Q1_A07_s2", "Tumbuhan juga mengonsumsi karbon dioksida.")]


@pytest.fixture(autouse=True)
def tmp_cache(monkeypatch, tmp_path):
    counter = iter(range(1000))
    monkeypatch.setattr(llm, "cache_dir", lambda: tmp_path / str(next(counter)))


@pytest.fixture
def entries(worked):
    return ledger_for(worked, worked["students"])


def gen(worked, entries, replies):
    it = iter(replies)
    return feedback.generate("Q1_A07", entries, worked["refs"], worked["rubric"], SENTS, 70.0,
                             backend=lambda *a: json.dumps(next(it)))


GOOD = {"summary": "Skor 70,0. Bagus.", "claims": [
    {"text": "Kamu menyebut CO2 dan O2 dengan benar.", "kind": "correct", "ledger_entry_ids": ["L_Q1_A07_R2", "L_Q1_A07_R5"]},
    {"text": "Air (H2O) belum disebut.", "kind": "missing", "ledger_entry_ids": ["L_Q1_A07_R3"]}]}


def test_valid_llm_feedback_with_chemical_names(worked, entries):
    fb = gen(worked, entries, [GOOD])
    assert fb.source == "llm" and len(fb.claims) == 2


@pytest.mark.parametrize("bad, msg", [
    ({**GOOD, "claims": [{**GOOD["claims"][0], "ledger_entry_ids": ["L_Q1_A07_R9"]}]}, "unknown entry"),
    ({**GOOD, "claims": [{**GOOD["claims"][1], "kind": "correct"}]}, "is 'correct' but L_Q1_A07_R3 is MISSING"),
    ({**GOOD, "summary": "Skor kamu seharusnya 95."}, "numbers other than the score"),
])
def test_validator_rejects(worked, entries, bad, msg):
    from autograde.models import Feedback
    errors = feedback.validate(Feedback(answer_id="Q1_A07", **bad), entries, 70.0)
    assert any(msg in e for e in errors)


def test_retry_then_accept(worked, entries):
    tampered = {**GOOD, "summary": "Skor 100."}
    assert gen(worked, entries, [tampered, GOOD]).source == "llm"


def test_two_failures_fall_back_to_template(worked, entries):
    tampered = {**GOOD, "summary": "Skor 100."}
    fb = gen(worked, entries, [tampered, tampered])
    assert fb.source == "template"
    assert feedback.validate(fb, entries, 70.0) == []


def test_template_without_api_key(worked, entries, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "load_dotenv", lambda *a: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    fb = feedback.generate("Q1_A07", entries, worked["refs"], worked["rubric"], SENTS, 70.0)
    assert fb.source == "template"
    assert [c.kind for c in fb.claims] == ["missing", "partial", "correct"]
    assert fb.summary.startswith("Skor: 70.0")
    assert feedback.validate(fb, entries, 70.0) == []
