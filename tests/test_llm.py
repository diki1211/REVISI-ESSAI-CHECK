import pytest

from autograde import llm

CFG = {"provider": "anthropic", "model": "m1", "effort": "medium", "max_tokens": 100}
SCHEMA = {"type": "object"}


def test_cache_hit_skips_backend(tmp_path):
    calls = []
    backend = lambda *a: calls.append(1) or '{"x": 1}'
    assert llm.complete_json("s", "u", SCHEMA, backend=backend, cfg=CFG, cache=tmp_path) == {"x": 1}
    assert llm.complete_json("s", "u", SCHEMA, backend=backend, cfg=CFG, cache=tmp_path) == {"x": 1}
    assert len(calls) == 1


def test_cache_key_includes_model(tmp_path):
    calls = []
    backend = lambda *a: calls.append(1) or "{}"
    llm.complete_json("s", "u", SCHEMA, backend=backend, cfg=CFG, cache=tmp_path)
    llm.complete_json("s", "u", SCHEMA, backend=backend, cfg={**CFG, "model": "m2"}, cache=tmp_path)
    assert len(calls) == 2


def test_retries_invalid_json(tmp_path):
    replies = iter(["not json", "{bad", '{"ok": true}'])
    assert llm.complete_json("s", "u", SCHEMA, backend=lambda *a: next(replies), cfg=CFG, cache=tmp_path) == {"ok": True}


def test_gives_up_after_two_retries(tmp_path):
    with pytest.raises(llm.LLMError):
        llm.complete_json("s", "u", SCHEMA, backend=lambda *a: "nope", cfg=CFG, cache=tmp_path)


def test_no_key_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(llm.io, "ROOT", tmp_path)  # no .env here
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(llm.LLMUnavailable):
        llm.anthropic_backend("s", "u", SCHEMA, CFG)
