"""Graph-level similarity between a student's graph and the key graph — comparison metrics, never the score.

The system score (Eq. 6) is a weighted recall over the ledger. These metrics answer a different question, "how
alike are the two graphs as a whole?", and are reported next to the baselines in `evaluate`:

- B3 exact triple: weighted recall with exact concept ids only (no embeddings, no skos:broader, no partial credit).
- G1 graph F1: harmonic mean of weighted recall (as B3) and precision over the student's own edges, so extra
  edges lower it. Unlike Eq. 6 it therefore punishes extra (possibly correct) statements; that is the point of
  reporting it as a contrast.
- G2 graph edit similarity: 1 − GED / (|V_key| + |E_key| + |V_student| + |E_student|), with unit costs; nodes match
  on concept id and edges on equivalent predicates (the ontology's equivalentPredicate closure).

Student graphs come from the stored triples (concepts already filled from the alias table). Negated triples are
left out: they do not assert the relation. A concept the alias table does not know is its own node ("?text").
"""
import networkx as nx

from autograde.normalize import norm_text


def node_id(concept, text):
    return concept or f"?{norm_text(text)}"


def pred_class(p, rel):
    """One name per equivalence class, so equivalent predicates compare equal."""
    return min({p, *rel.eq.get(p, ())})


def key_edges(refs):
    return [(r.s[0], r.p, r.o, r.weight) for r in refs]


def student_edges(students, refs, rel):
    """(subject node, predicate, object node) for non-negated triples. A subject that a key triple accepts as an
    alternative ("Tumbuhan" for "Fotosintesis") is renamed to that triple's first subject, as in matching."""
    out = []
    for t in students:
        if t.negated:
            continue
        s, o = node_id(t.s_concept, t.s_text), node_id(t.o_concept, t.o_text)
        for r in refs:
            if s in r.s and o == r.o and rel.is_eq(r.p, t.p):
                s = r.s[0]
                break
        out.append((s, t.p, o))
    return list(dict.fromkeys(out))


def ref_hit(r, edges, rel):
    return any(s in r.s and o == r.o and rel.is_eq(r.p, p) for s, p, o in edges)


def exact_triple_score(refs, students, rel):
    edges = student_edges(students, refs, rel)
    return 100 * sum(r.weight for r in refs if ref_hit(r, edges, rel)) / sum(r.weight for r in refs)


def graph_f1(refs, students, rel):
    edges = student_edges(students, refs, rel)
    if not edges:
        return 0.0
    recall = exact_triple_score(refs, students, rel) / 100
    precision = sum(any(s in r.s and o == r.o and rel.is_eq(r.p, p) for r in refs) for s, p, o in edges) / len(edges)
    return 0.0 if precision + recall == 0 else 100 * 2 * precision * recall / (precision + recall)


def to_nx(edges, rel):
    g = nx.DiGraph()
    for s, p, o, *_ in edges:
        g.add_node(s, label=s)
        g.add_node(o, label=o)
        if g.has_edge(s, o):
            g[s][o]["preds"] |= {pred_class(p, rel)}
        else:
            g.add_edge(s, o, preds={pred_class(p, rel)})
    return g


def graph_edit_similarity(refs, students, rel, timeout=5):
    """100 · (1 − GED / size). Exact for these small graphs; after `timeout` seconds the best bound found so far
    is used (an upper bound on GED, so the similarity can only be underestimated)."""
    g1, g2 = to_nx(key_edges(refs), rel), to_nx(student_edges(students, refs, rel), rel)
    size = g1.number_of_nodes() + g1.number_of_edges() + g2.number_of_nodes() + g2.number_of_edges()
    if size == 0:
        return 100.0
    ged = nx.graph_edit_distance(g1, g2, node_match=lambda a, b: a["label"] == b["label"],
                                 edge_match=lambda a, b: bool(a["preds"] & b["preds"]), timeout=timeout)
    if ged is None:  # timed out before any path: deleting and inserting everything is always possible
        ged = size
    return 100 * (1 - ged / size)


METRICS = {"B3 exact triple": exact_triple_score, "G1 graph F1": graph_f1,
           "G2 graph edit similarity": graph_edit_similarity}


def all_metrics(refs, students, rel):
    return {name: f(refs, students, rel) for name, f in METRICS.items()}
