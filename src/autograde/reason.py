"""SWRL reasoning under Pellet, or the same logic as SPARQL over rdflib.

Stage 1, contradictions (Eq. 5, Rules 1-3): before the ledger, from aligned student/reference pairs.
Stage 2, premise gaps (Rule 4): after the ledger, from entry statuses and the gold `requires` links.
"""
from rdflib import RDF, Graph, Literal

from autograde import io, premise
from autograde.io import AG, ANS, KEY
from autograde.models import STATUS_IRI_NAME

CONTRADICTS_QUERY = io.SPARQL_PREFIXES + """
CONSTRUCT { ?t ag:contradicts ?r }
WHERE {
  ?t a ag:StudentTriple ; ag:hasPredicate ?pt ; ag:alignedSubject ?r ; ag:alignedObject ?r .
  ?r a ag:ReferenceTriple ; ag:hasPredicate ?pr .
  # negation is matched inside each branch: a FILTER there cannot see variables bound outside the group
  { ?t ag:negated false . ?pt (ag:incompatibleWith|^ag:incompatibleWith) ?pr . }        # Rule 1
  UNION
  { ?t ag:negated true . ?pt (ag:equivalentPredicate|^ag:equivalentPredicate)* ?pr . }   # Rules 2-3
}
"""


PREMISE_QUERY = io.SPARQL_PREFIXES + """
CONSTRUCT { ?ec ag:lacksPremise ?ep }
WHERE {
  ?ec a ag:LedgerEntry ; ag:reference ?c ; ag:answer ?a ; ag:status ?sc .
  ?sc ag:isCredited true .
  ?c ag:requiresPremise ?p .
  ?ep a ag:LedgerEntry ; ag:reference ?p ; ag:answer ?a ; ag:status ?sp .
  ?sp ag:isCredited false .
}
"""  # Rule 4


def _ref_name(qid, ref_id):
    return f"{qid}_{ref_id}"


def _strip(qid, name):
    return name[len(qid) + 1:]


def contradictions_sparql(qid, refs, students, aligned):
    g = Graph()
    for triple in io.ontology_graph():
        g.add(triple)
    for r in refs:
        node = KEY[_ref_name(qid, r.id)]
        g.add((node, RDF.type, AG.ReferenceTriple))
        g.add((node, AG.hasPredicate, AG[r.p]))
    for t in students:
        g.add((ANS[t.id], RDF.type, AG.StudentTriple))
        g.add((ANS[t.id], AG.hasPredicate, AG[t.p]))
        g.add((ANS[t.id], AG.negated, Literal(t.negated)))
    for t_id, r_id in aligned:
        g.add((ANS[t_id], AG.alignedSubject, KEY[_ref_name(qid, r_id)]))
        g.add((ANS[t_id], AG.alignedObject, KEY[_ref_name(qid, r_id)]))
    result = g.query(CONTRADICTS_QUERY).graph
    return {(io.local_name(t), _strip(qid, io.local_name(r))) for t, _, r in result}


def premise_gaps_sparql(qid, refs, entries):
    from autograde import ledger
    g = Graph()
    for triple in io.ontology_graph():
        g.add(triple)
    for c, p in premise.links(refs):
        g.add((KEY[_ref_name(qid, c)], AG.requiresPremise, KEY[_ref_name(qid, p)]))
    for triple in ledger.to_graph(qid, entries):
        g.add(triple)
    ref_of = {e.entry_id: e.reference_id for e in entries}
    return {(ref_of[io.local_name(ec)], ref_of[io.local_name(ep)]) for ec, _, ep in g.query(PREMISE_QUERY).graph}


class PelletReasoner:
    """Loads autograde.owl once; each answer lives in its own ontology that is destroyed afterwards."""

    def __init__(self):
        import owlready2

        self.o = owlready2
        owlready2.JAVA_EXE = io.java_exe()
        if not owlready2.JAVA_EXE:
            raise RuntimeError("Java not found; install Java 25+ or set reasoner: sparql in config.yaml")
        self.world = owlready2.World()
        self.base = self.world.get_ontology(io.ontology_path().as_uri()).load()

    def contradictions(self, qid, refs, students, aligned):
        answer = students[0].answer_id if students else "empty"
        run = self.world.get_ontology(f"http://example.org/autograde/run/{answer}#")
        try:
            with run:
                ind = {}
                for r in refs:
                    ind[r.id] = self.base.ReferenceTriple(_ref_name(qid, r.id), namespace=run)
                    ind[r.id].hasPredicate = self.base[r.p]
                for t in students:
                    ind[t.id] = self.base.StudentTriple(t.id, namespace=run)
                    ind[t.id].hasPredicate = self.base[t.p]
                    ind[t.id].negated = t.negated  # always asserted: open world never satisfies negated(?t, false)
                for t_id, r_id in aligned:
                    ind[t_id].alignedSubject.append(ind[r_id])
                    ind[t_id].alignedObject.append(ind[r_id])
            self.o.sync_reasoner_pellet(self.world, infer_property_values=True, infer_data_property_values=True,
                                        debug=0)
            return {(t.id, _strip(qid, r.name)) for t in students for r in ind[t.id].contradicts}
        finally:
            run.destroy()
            self.world.get_ontology("http://inferrences/").destroy()

    def premise_gaps(self, qid, refs, entries):
        answer = entries[0].answer_id if entries else "empty"
        run = self.world.get_ontology(f"http://example.org/autograde/run/{answer}/premises#")
        try:
            with run:
                ref = {r.id: self.base.ReferenceTriple(_ref_name(qid, r.id), namespace=run) for r in refs}
                for c, p in premise.links(refs):
                    ref[c].requiresPremise.append(ref[p])
                ans = self.base.Answer(answer, namespace=run)
                ent = {}
                for e in entries:
                    ent[e.entry_id] = self.base.LedgerEntry(e.entry_id, namespace=run)
                    ent[e.entry_id].reference = ref[e.reference_id]
                    ent[e.entry_id].answer = ans
                    ent[e.entry_id].status = self.base[STATUS_IRI_NAME[e.status]]
            self.o.sync_reasoner_pellet(self.world, infer_property_values=True, infer_data_property_values=True,
                                        debug=0)
            ref_of = {e.entry_id: e.reference_id for e in entries}
            return {(ref_of[e.entry_id], ref_of[x.name]) for e in entries for x in ent[e.entry_id].lacksPremise}
        finally:
            run.destroy()
            self.world.get_ontology("http://inferrences/").destroy()

    def residue(self):
        """Individuals left in the world besides the base ontology's own (should be none)."""
        return [i for i in self.world.individuals() if i.namespace.ontology is not self.base]


_pellet = None


def contradictions(qid, refs, students, aligned, reasoner=None):
    global _pellet
    reasoner = reasoner or io.load_config()["reasoner"]
    if reasoner == "sparql":
        return contradictions_sparql(qid, refs, students, aligned)
    if reasoner != "pellet":
        raise ValueError(f"unknown reasoner {reasoner!r}")
    _pellet = _pellet or PelletReasoner()
    return _pellet.contradictions(qid, refs, students, aligned)


def premise_gaps(qid, refs, entries, reasoner=None):
    """(conclusion id, premise id) pairs inferred by Rule 4. Questions without `requires` skip the reasoner."""
    global _pellet
    if not premise.links(refs):
        return set()
    reasoner = reasoner or io.load_config()["reasoner"]
    if reasoner == "sparql":
        return premise_gaps_sparql(qid, refs, entries)
    if reasoner != "pellet":
        raise ValueError(f"unknown reasoner {reasoner!r}")
    _pellet = _pellet or PelletReasoner()
    return _pellet.premise_gaps(qid, refs, entries)
