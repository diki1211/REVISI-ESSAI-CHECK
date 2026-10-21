"""Equations (3)-(5): pairwise match credit, best credit per reference triple, contradiction."""
from dataclasses import dataclass

from autograde import io


@dataclass(frozen=True)
class Relations:
    eq: dict  # predicate -> set of equivalent predicates (closure, includes itself)
    inc: set  # frozenset pairs

    @classmethod
    def from_ontology(cls):
        _, eq, inc = io.ontology_relations()
        return cls(eq, inc)

    def is_eq(self, p, q):
        return p == q or q in self.eq.get(p, ())

    def is_inc(self, p, q):
        return frozenset((p, q)) in self.inc


@dataclass(frozen=True)
class MatchResult:
    reference_id: str
    credit: float  # m_i
    matched_by: str | None
    sigma: float | None


def order_key(t):
    """Tie-break: lowest sentence index, then lowest triple index."""
    return int(t.sentence_ids[0].rsplit("_s", 1)[1]), int(t.id.rsplit("_t", 1)[1])


def sigma(ref, t, sim):
    s_sim = max(sim(c, c, t.s_concept, t.s_text) for c in ref.s)
    return min(s_sim, sim(ref.o, ref.o, t.o_concept, t.o_text))


def mu(ref, t, sig, params, rel):
    if not rel.is_eq(ref.p, t.p) or t.negated:
        return 0.0
    if sig >= params["tau_h"]:
        return 1.0
    if sig >= params["tau_l"]:
        return params["delta"]
    return 0.0


def match(refs, students, params, sim, rel):
    """(results by reference id, σ for every (t, r) pair, pairs aligned for the reasoner with σ >= tau_h)."""
    sigmas = {(t.id, r.id): sigma(r, t, sim) for r in refs for t in students}
    results = {}
    for r in refs:
        scored = [(mu(r, t, sigmas[t.id, r.id], params, rel), t) for t in students]
        best = max((m for m, _ in scored), default=0.0)
        if best > 0:
            t = min((t for m, t in scored if m == best), key=order_key)
            results[r.id] = MatchResult(r.id, best, t.id, sigmas[t.id, r.id])
        else:
            results[r.id] = MatchResult(r.id, 0.0, None, None)
    aligned = sorted(k for k, s in sigmas.items() if s >= params["tau_h"])
    return results, sigmas, aligned


def contradictions(refs, students, sigmas, params, rel):
    """Eq. (5) in plain Python: the reference for Pellet/SPARQL parity and the calibration fast path."""
    out = set()
    for r in refs:
        for t in students:
            if sigmas[t.id, r.id] < params["tau_h"]:
                continue
            if (rel.is_inc(r.p, t.p) and not t.negated) or (rel.is_eq(r.p, t.p) and t.negated):
                out.add((t.id, r.id))
    return out
