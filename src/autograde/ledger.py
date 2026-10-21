"""One LedgerEntry per reference triple; JSON/CSV/TTL output; SPARQL score recompute; lecturer overrides."""
import csv
from decimal import Decimal

from rdflib import RDF, RDFS, XSD, Graph, Literal

from autograde.gold import ref_iri
from autograde import io
from autograde.io import AG, ANS, KEY, PROV, save_json
from autograde.match import order_key
from autograde.models import STATUS_IRI_NAME, LedgerEntry

RECOMPUTE_QUERY = io.SPARQL_PREFIXES + """
SELECT ?ans ((100 * (SUM(?w * ?c) - ?lambda * SUM(?w * ?k))) / SUM(?w) AS ?raw)
WHERE { ?e a ag:LedgerEntry ; ag:answer ?ans ; ag:reference ?r ;
           ag:credit ?c ; ag:contradiction ?k .
        ?r ag:weight ?w . }
GROUP BY ?ans ?lambda
"""


def build(answer_id, refs, results, sigmas, contra, students, params):
    by_id = {t.id: t for t in students}
    entries = []
    for r in refs:
        res = results[r.id]
        against = [by_id[t] for t, ref in contra if ref == r.id]
        base = dict(entry_id=f"L_{answer_id}_{r.id}", answer_id=answer_id, reference_id=r.id,
                    criterion=r.criterion, weight=r.weight)
        if against:
            t = min(against, key=order_key)
            entries.append(LedgerEntry(**base, status="CONTRADICTED", credit=0.0, contradiction=True,
                                       matched_by=None, contradicted_by=t.id, sigma=sigmas[t.id, r.id],
                                       sentence_ids=t.sentence_ids, needs_review=False))
            continue
        status = "MATCHED" if res.credit == 1.0 else "PARTIAL" if res.credit > 0 else "MISSING"
        entries.append(LedgerEntry(**base, status=status, credit=res.credit, contradiction=False,
                                   matched_by=res.matched_by, contradicted_by=None, sigma=res.sigma,
                                   sentence_ids=by_id[res.matched_by].sentence_ids if res.matched_by else [],
                                   needs_review=status == "PARTIAL"))
    return entries


def _dec(x):
    return Literal(str(Decimal(str(x))), datatype=XSD.decimal)


def to_graph(qid, entries):
    g = io.bind_namespaces(Graph())
    for e in entries:
        node = ANS[e.entry_id]
        g.add((node, RDF.type, AG.LedgerEntry))
        g.add((node, AG.answer, ANS[e.answer_id]))
        g.add((node, AG.reference, ref_iri(qid, e.reference_id)))
        if e.matched_by:
            g.add((node, AG.matchedBy, ANS[e.matched_by]))
        if e.contradicted_by:
            g.add((node, AG.contradictedBy, ANS[e.contradicted_by]))
        g.add((node, AG.status, AG[STATUS_IRI_NAME[e.status]]))
        g.add((node, AG.credit, _dec(e.credit)))
        g.add((node, AG.contradiction, _dec(int(e.contradiction))))
        if e.override:
            g.add((node, RDFS.comment, Literal(f"override by {e.override['by']}: {e.override['reason']}")))
    return g


def answer_graph(answer_id, students, sentences, qid=None, trace=None):
    """Student triples with provenance (the deck's jawaban.ttl), plus the reasoner's input and output when
    a trace is given: the alignedSubject/alignedObject pairs Python asserted and the inferred ag:contradicts."""
    g = io.bind_namespaces(Graph())
    g.add((ANS[answer_id], RDF.type, AG.Answer))
    for sid, text in sentences:
        g.add((ANS[sid], RDF.type, AG.Sentence))
        g.add((ANS[sid], RDFS.label, Literal(text)))
    for t in students:
        node = ANS[t.id]
        g.add((node, RDF.type, AG.StudentTriple))
        for prop, concept, text, suffix in ((AG.hasSubject, t.s_concept, t.s_text, "s"),
                                            (AG.hasObject, t.o_concept, t.o_text, "o")):
            c = KEY[concept] if concept else ANS[f"{t.id}_{suffix}"]  # unknown concept: a node for this triple
            g.add((node, prop, c))
            g.add((c, RDF.type, AG.Concept))
            if not concept:
                g.add((c, RDFS.label, Literal(text, lang="id")))
        g.add((node, AG.hasPredicate, AG[t.p]))
        g.add((node, AG.negated, Literal(t.negated)))
        g.add((node, AG.inAnswer, ANS[answer_id]))
        for sid in t.sentence_ids:
            g.add((node, PROV.wasDerivedFrom, ANS[sid]))
    for t_id, r_id in (trace or {}).get("aligned", []):
        g.add((ANS[t_id], AG.alignedSubject, ref_iri(qid, r_id)))
        g.add((ANS[t_id], AG.alignedObject, ref_iri(qid, r_id)))
    for t_id, r_id in (trace or {}).get("contradictions", []):
        g.add((ANS[t_id], AG.contradicts, ref_iri(qid, r_id)))
    return g


def write(out_dir, qid, entries, suffix=""):
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [e.model_dump() for e in entries]
    save_json(rows, out_dir / f"ledger{suffix}.json")
    with open(out_dir / f"ledger{suffix}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for row in rows:
            w.writerow({**row, "sentence_ids": " ".join(row["sentence_ids"]), "override": row["override"] or ""})
    to_graph(qid, entries).serialize(out_dir / f"ledger{suffix}.ttl", format="turtle")


def recompute_sparql(ledger_ttl, gold_ttl, lam):
    """Score from the RDF files alone, clamped at 0 like Eq. 6."""
    g = Graph()
    g.parse(ledger_ttl)
    g.parse(gold_ttl)
    rows = list(g.query(RECOMPUTE_QUERY, initBindings={"lambda": _dec(lam)}))
    if len(rows) != 1:
        raise ValueError(f"expected one answer in {ledger_ttl}, got {len(rows)}")
    return max(0.0, float(rows[0].raw.toPython()))


def apply_overrides(entries, overrides, params):
    """Corrected copies of entries; the originals are untouched. Credit follows the new status."""
    by_ref = {e.reference_id: e for e in entries}
    out = {e.reference_id: e for e in entries}
    for ov in overrides:
        if ov["reference_id"] not in by_ref:
            raise ValueError(f"override for {ov['answer_id']}: no ledger entry for {ov['reference_id']}")
        old = by_ref[ov["reference_id"]]
        status = ov["status"]
        credits = {"MATCHED": 1.0, "PARTIAL": params["delta"], "MISSING": 0.0, "CONTRADICTED": 0.0}
        if status not in credits:
            raise ValueError(f"unknown status {status!r}")
        credit = credits[status]
        out[old.reference_id] = old.model_copy(update={
            "status": status, "credit": credit, "contradiction": status == "CONTRADICTED", "needs_review": False,
            "override": {"by": ov["by"], "date": str(ov["date"]), "reason": ov["reason"], "original_status": old.status}})
    return [out[e.reference_id] for e in entries]
