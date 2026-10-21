"""Lecturer corrections (deck slide 1.4): data/human/overrides.yaml -> corrected copies of a run's ledgers.

Used by `python -m autograde override` and by the app's lecturer review page. The original ledger.* and
score.json are never changed, corrected scores are never used by `evaluate` (they contain human judgement), and
every override records who made it, when, why, and the system's original status.
"""
from datetime import date

import pandas as pd

from autograde import gold, io, ledger, premise
from autograde.models import LedgerEntry
from autograde.score import score

STATUSES = ("MATCHED", "PARTIAL", "MISSING", "CONTRADICTED")
CORRECTED_FILES = ("ledger_corrected.json", "ledger_corrected.csv", "ledger_corrected.ttl", "score_corrected.json")


class OverrideError(ValueError):
    pass


def overrides_path():
    return io.ROOT / "data" / "human" / "overrides.yaml"


def load_overrides():
    path = overrides_path()
    return (io.load_yaml(path) or []) if path.exists() else []


def check(ov):
    missing = [k for k in ("answer_id", "reference_id", "status", "reason", "by", "date") if not str(ov.get(k) or "").strip()]
    if missing:
        raise OverrideError(f"override {ov.get('answer_id')}/{ov.get('reference_id')}: missing {', '.join(missing)}")
    if ov["status"] not in STATUSES:
        raise OverrideError(f"override {ov['answer_id']}/{ov['reference_id']}: unknown status {ov['status']!r}")


def save_corrections(answer_id, corrections, entries, by, on=None):
    """Replace this answer's overrides with `corrections` ({reference_id: (status, reason)}).

    A correction equal to the system's own status is dropped, so choosing the original status again removes the
    override. Overrides for other answers are kept as they are. Returns the overrides now stored for the answer."""
    system = {e.reference_id: e.status for e in entries}
    on = str(on or date.today())
    mine = []
    for ref_id, (status, reason) in corrections.items():
        if ref_id not in system:
            raise OverrideError(f"{answer_id}: no ledger entry for {ref_id}")
        if status == system[ref_id]:
            continue
        ov = {"answer_id": answer_id, "reference_id": ref_id, "status": status, "reason": (reason or "").strip(),
              "by": (by or "").strip(), "date": on}
        check(ov)
        mine.append(ov)
    order = {e.reference_id: i for i, e in enumerate(entries)}
    mine.sort(key=lambda o: order[o["reference_id"]])
    others = [o for o in load_overrides() if o["answer_id"] != answer_id]
    io.save_yaml(others + mine, overrides_path())
    return mine


def question_of(run_dir, answer_id):
    scores = pd.read_csv(run_dir / "scores.csv", dtype=str)
    return scores.set_index("answer_id").loc[answer_id, "question_id"]


def load_entries(run_dir, answer_id, suffix=""):
    return [LedgerEntry(**e) for e in io.load_json(run_dir / answer_id / f"ledger{suffix}.json")]


def apply_answer(run_dir, answer_id, overrides, params):
    """Write the corrected ledger and score for one answer (or remove them when it has no overrides)."""
    d = run_dir / answer_id
    if not overrides:
        for name in CORRECTED_FILES:
            (d / name).unlink(missing_ok=True)
        return None
    from autograde import pipeline
    qid = question_of(run_dir, answer_id)
    fixed = ledger.apply_overrides(load_entries(run_dir, answer_id), overrides, params)
    ledger.write(d, qid, fixed, suffix="_corrected", gaps=premise.gaps(gold.load(qid)[2], fixed))
    sc = score(answer_id, fixed, params)
    sc.sparql_score = ledger.recompute_sparql(d / "ledger_corrected.ttl", io.question_dir(qid) / "gold.ttl",
                                              params["lambda"])
    if abs(sc.score - sc.sparql_score) >= 1e-9:
        raise pipeline.ParityError(f"{answer_id}: corrected score parity failed")
    io.save_json(sc.model_dump(), d / "score_corrected.json")
    return sc


def apply_run(run_id, answer_ids=None):
    """Apply overrides.yaml to a run. Returns [{answer_id, original, corrected}] (corrected None = removed/skipped)."""
    from autograde import pipeline
    run_dir = pipeline.runs_dir() / run_id
    params = io.load_json(run_dir / "run.json")["params"]
    overrides = load_overrides()
    for ov in overrides:
        check(ov)
    targets = sorted(set(answer_ids) if answer_ids is not None else {o["answer_id"] for o in overrides})
    out = []
    for answer_id in targets:
        d = run_dir / answer_id
        if not d.exists():
            out.append({"answer_id": answer_id, "original": None, "corrected": None, "skipped": True})
            continue
        sc = apply_answer(run_dir, answer_id, [o for o in overrides if o["answer_id"] == answer_id], params)
        out.append({"answer_id": answer_id, "original": io.load_json(d / "score.json")["score"],
                    "corrected": sc.score if sc else None, "skipped": False})
    return out


def queue(run_id):
    """One row per answer in a run: what needs the lecturer's attention and what has been corrected."""
    from autograde import pipeline
    run_dir = pipeline.runs_dir() / run_id
    scores = pd.read_csv(run_dir / "scores.csv", dtype={"answer_id": str, "question_id": str})
    corrected = {o["answer_id"] for o in load_overrides()}
    rows = []
    for a in scores.itertuples():
        entries = load_entries(run_dir, a.answer_id)
        trace = run_dir / a.answer_id / "trace.json"
        gaps = len(io.load_json(trace).get("premise_gaps", [])) if trace.exists() else 0
        sc_corr = run_dir / a.answer_id / "score_corrected.json"
        rows.append({"answer_id": a.answer_id, "question_id": a.question_id, "score": a.score,
                     "partial": sum(e.status == "PARTIAL" for e in entries),
                     "contradicted": sum(e.status == "CONTRADICTED" for e in entries), "premise_gaps": gaps,
                     "corrected_score": io.load_json(sc_corr)["score"] if sc_corr.exists() else None,
                     "has_overrides": a.answer_id in corrected})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["needs_review"] = (df.partial + df.contradicted + df.premise_gaps) > 0
    return df
