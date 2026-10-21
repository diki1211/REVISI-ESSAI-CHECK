"""Equation (6): S = 100 * max(0, Σ w·m − λ Σ w·κ) / Σ w."""
from autograde.models import ScoreResult


def score(answer_id, entries, params):
    sum_w = sum(e.weight for e in entries)
    sum_wm = sum(e.weight * e.credit for e in entries)
    penalty = params["lambda"] * sum(e.weight * float(e.contradiction) for e in entries)
    return ScoreResult(answer_id=answer_id, score=100 * max(0.0, sum_wm - penalty) / sum_w,
                       sum_weighted_credit=sum_wm, sum_penalty=penalty, sum_weights=sum_w, params=dict(params))
