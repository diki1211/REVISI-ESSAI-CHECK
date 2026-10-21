import pytest

from autograde import calibrate, io, pipeline
from test_pipeline import STUB


def test_calibrate_writes_once(tmp_path, monkeypatch):
    orig = pipeline.Context.load.__func__
    monkeypatch.setattr(pipeline.Context, "load",
                        classmethod(lambda cls, q, **k: orig(cls, q, reasoner="sparql", cosine=STUB)))
    out = tmp_path / "frozen.yaml"
    calibrate.calibrate(include_synthetic=True, mode="gold", out=out)
    frozen = io.load_yaml(out)
    assert set(frozen["params"]) == {"tau_h", "tau_l", "delta", "lambda"}
    assert frozen["params"]["tau_l"] < frozen["params"]["tau_h"]
    assert all(r["tau_l"] < r["tau_h"] for r in frozen["grid"]) and len(frozen["grid"]) == 12
    assert frozen["synthetic"] is True
    with pytest.raises(FileExistsError):
        calibrate.calibrate(include_synthetic=True, mode="gold", out=out)
