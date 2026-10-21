"""gold.yaml -> validated ReferenceTriples -> gold.ttl (reified ag:ReferenceTriple individuals)."""
from collections import defaultdict

from pydantic import ValidationError
from rdflib import RDF, RDFS, XSD, Graph, Literal
from rdflib.namespace import SKOS

from autograde import io
from autograde.io import AG, KEY
from autograde.models import ReferenceTriple


class GoldError(ValueError):
    pass


def ref_iri(qid, ref_id):
    return KEY[f"{qid}_{ref_id}"]


def criterion_iri(qid, criterion):
    return KEY[f"{qid}_{criterion}"]


def broader_links(concepts):
    """{concept: [broader concepts]} from gold.yaml's optional `broader:` lists."""
    return {c: list((spec or {}).get("broader") or []) for c, spec in concepts.items()}


def ancestors(concepts):
    """Transitive closure of skos:broader: {concept: every more general concept}."""
    links, out = broader_links(concepts), {}
    for c in links:
        seen, stack = set(), list(links[c])
        while stack:
            b = stack.pop()
            if b not in seen:
                seen.add(b)
                stack.extend(links.get(b, []))
        out[c] = seen
    return out


def check_predicates(predicates, relations):
    ids = [p["id"] for p in predicates["predicates"]]
    missing = [p for p in ids if p != "other" and p not in relations]
    if missing:
        raise GoldError(f"predicates.yaml ids missing from the ontology: {missing}")
    aliases = [a for p in predicates["predicates"] for a in p.get("aliases", [])]
    clash = sorted(set(aliases) & set(ids))
    if clash:
        raise GoldError(f"aliases that are also predicate ids: {clash}")
    dup = sorted({a for a in aliases if aliases.count(a) > 1})
    if dup:
        raise GoldError(f"aliases listed under several predicates: {dup}")


def validate(gold, rubric, relations):
    if gold.get("question_id") != rubric.get("question_id"):
        raise GoldError("gold.yaml and rubric.yaml disagree on question_id")
    criteria = {c["id"] for c in rubric["criteria"]}
    concepts = set(gold.get("concepts") or {})
    refs, errors = [], []
    for raw in gold.get("triples") or []:
        try:
            ref = ReferenceTriple(**raw)
        except ValidationError as e:
            errors.append(f"{raw.get('id')}: {e.errors()[0]['msg']}")
            continue
        if ref.p not in relations:
            errors.append(f"{ref.id}: unknown predicate {ref.p!r}")
        if ref.criterion not in criteria:
            errors.append(f"{ref.id}: unknown criterion {ref.criterion!r}")
        for c in [*ref.s, ref.o]:
            if c not in concepts:
                errors.append(f"{ref.id}: undeclared concept {c!r}")
        refs.append(ref)
    ids = [r.id for r in refs]
    if len(ids) != len(set(ids)):
        errors.append("duplicate reference triple ids")
    for c in sorted(criteria - {r.criterion for r in refs}):
        errors.append(f"criterion {c} has no reference triple")
    for c, broader in broader_links(gold.get("concepts") or {}).items():
        for b in broader:
            if b not in concepts:
                errors.append(f"concept {c}: broader concept {b!r} is not declared")
    if not errors:
        for c, above in ancestors(gold.get("concepts") or {}).items():
            if c in above:
                errors.append(f"concept {c} is its own broader concept (cycle)")
    if errors:
        raise GoldError("; ".join(errors))
    return refs


def load(qid):
    """Validated (gold_raw, rubric, refs) for a question."""
    d = io.question_dir(qid)
    gold, rubric = io.load_yaml(d / "gold.yaml"), io.load_yaml(d / "rubric.yaml")
    relations, _, _ = io.ontology_relations()
    check_predicates(io.load_predicates(), relations)
    return gold, rubric, validate(gold, rubric, relations)


def criterion_weights(refs):
    w = defaultdict(float)
    for r in refs:
        w[r.criterion] += r.weight
    return dict(w)


def to_graph(qid, refs, rubric, concepts=None):
    g = io.bind_namespaces(Graph())
    lang = rubric.get("language", "id")
    for c in rubric["criteria"]:
        g.add((criterion_iri(qid, c["id"]), RDF.type, AG.Criterion))
        g.add((criterion_iri(qid, c["id"]), RDFS.comment, Literal(c["description"], lang=lang)))
    for c, broader in broader_links(concepts or {}).items():  # the lecturer's concept hierarchy (SKOS)
        g.add((KEY[c], RDF.type, AG.Concept))
        g.add((KEY[c], RDF.type, SKOS.Concept))
        for b in broader:
            g.add((KEY[c], SKOS.broader, KEY[b]))
    for r in refs:
        node = ref_iri(qid, r.id)
        g.add((node, RDF.type, AG.ReferenceTriple))
        for s in r.s:
            g.add((node, AG.hasSubject, KEY[s]))
            g.add((KEY[s], RDF.type, AG.Concept))
        g.add((node, AG.hasPredicate, AG[r.p]))
        g.add((node, AG.hasObject, KEY[r.o]))
        g.add((KEY[r.o], RDF.type, AG.Concept))
        g.add((node, AG.criterion, criterion_iri(qid, r.criterion)))
        g.add((node, AG.weight, Literal(str(r.weight), datatype=XSD.decimal)))
    return g


def review_md(qid, gold, rubric, refs):
    desc = {c["id"]: c["description"] for c in rubric["criteria"]}
    lines = [f"# Gold triples for {qid} — lecturer review", "",
             f"Validated by: {gold.get('validated_by') or '________'}  ",
             f"Date: {gold.get('validated_on') or '________'}", "",
             "| ID | Subjek (diterima) | Predikat | Objek | Kriteria | Bobot | OK? |",
             "|---|---|---|---|---|---|---|"]
    for r in refs:
        lines.append(f"| {r.id} | {' / '.join(r.s)} | {r.p} | {r.o} | {r.criterion} ({desc[r.criterion]}) "
                     f"| {r.weight:g} | ☐ |")
    lines += ["", "## Konsep dan alias", ""]
    for c, v in (gold.get("concepts") or {}).items():
        broader = (v or {}).get("broader") or []
        lines.append(f"- **{c}**: {', '.join((v or {}).get('aliases', [])) or '—'}"
                     + (f" — lebih khusus dari (skos:broader): {', '.join(broader)}" if broader else ""))
    return "\n".join(lines) + "\n"


def build(qid):
    gold, rubric, refs = load(qid)
    out = io.question_dir(qid) / "gold.ttl"
    to_graph(qid, refs, rubric, gold.get("concepts")).serialize(out, format="turtle")
    (io.ROOT / "docs").mkdir(exist_ok=True)
    (io.ROOT / "docs" / f"gold_{qid}_review.md").write_text(review_md(qid, gold, rubric, refs), encoding="utf-8")
    return out, refs
