"""Grid search for tau_h, tau_l on the pooled pilot split (all questions); writes frozen.yaml once."""
from datetime import datetime

from autograde import gold, io, pipeline, segment
from autograde.evaluate import human_totals


def calibrate(include_synthetic=False, mode="llm", cosine=None, out=None):
    out = out or (io.ROOT / "outputs" / "synthetic" / "frozen.yaml" if include_synthetic else io.frozen_path())
    if out.exists():
        raise FileExistsError(f"{out} already exists: parameters are frozen (Agent Rule 3)")
    answers = io.load_answers(include_synthetic)
    pilot = answers[answers.split == "pilot"].sort_values("answer_id")
    question_of = dict(zip(pilot.answer_id, pilot.question_id))
    # SPARQL reasoner: parity-tested against Pellet, and fast enough for the whole grid
    contexts = {q: pipeline.Context.load(q, reasoner="sparql", cosine=cosine) for q in sorted(set(pilot.question_id))}
    weights = {q: gold.criterion_weights(c.refs) for q, c in contexts.items()}
    scores = io.load_human_scores(include_synthetic)
    human = human_totals(scores[scores.answer_id.isin(pilot.answer_id)], weights, question_of)
    pilot = pilot[pilot.answer_id.isin(human.index)]
    if pilot.empty:
        raise ValueError("no pilot answers with human scores")
    students = {a.answer_id: pipeline.extract_triples(contexts[a.question_id], a.answer_id,
                                                      segment.split(a.answer_id, a.text), mode)[0]
                for a in pilot.itertuples()}
    base, grid = io.load_params(), io.load_config()["calibration_grid"]
    rows = []
    for tau_h in grid["tau_h"]:
        for tau_l in grid["tau_l"]:
            if tau_l >= tau_h:
                continue
            params = {**base, "tau_h": tau_h, "tau_l": tau_l}
            errs = [abs(pipeline.grade(contexts[a.question_id], a.answer_id, students[a.answer_id], params)[2].score
                        - human[a.answer_id]) for a in pilot.itertuples()]
            rows.append({"tau_h": tau_h, "tau_l": tau_l, "mae": round(float(sum(errs) / len(errs)), 6)})
    best = min(rows, key=lambda r: r["mae"])  # first in grid order on ties
    io.save_yaml({"params": {**base, "tau_h": best["tau_h"], "tau_l": best["tau_l"]},
                  "calibrated_at": datetime.now().isoformat(timespec="seconds"), "mode": mode,
                  "n_pilot": len(pilot), "synthetic": include_synthetic,
                  "note": "delta and lambda are fixed by decision (docs/DECISIONS.md), not tuned", "grid": rows}, out)
    return out
