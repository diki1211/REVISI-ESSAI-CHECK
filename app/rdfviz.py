"""Graphviz DOT builders, RDF graph loading and preset SPARQL queries for the demo app (read-only)."""
import re

import pandas as pd
from rdflib import OWL, RDF, RDFS, Graph, Literal

from autograde import io
from autograde.io import AG

STATUS_COLOR = {"MATCHED": "#2e7d32", "PARTIAL": "#b26a00", "MISSING": "#757575", "CONTRADICTED": "#c62828"}
PREFIXES = io.SPARQL_PREFIXES + "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n" \
                                 "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"


def esc(text):
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def short(node):
    """Compact form of an RDF term for tables: ag:X, prov:X, or the literal value."""
    if isinstance(node, Literal):
        return node.toPython()
    s = str(node)
    for prefix, ns in [*((p + ":", str(ns)) for p, ns in io.NAMESPACES.items()),
                       ("rdfs:", str(RDFS)), ("owl:", str(OWL)), ("rdf:", str(RDF))]:
        if s.startswith(ns):
            return prefix + s[len(ns):]
    return s


def name(node):
    return io.local_name(node)


# ---------- ontology ----------

def ontology_classes_dot(g):
    lines = ["digraph { rankdir=BT; node [shape=box, style=\"rounded,filled\", fillcolor=\"#eef3f8\", fontname=Helvetica];"]
    classes = {c for c in g.subjects(RDF.type, OWL.Class) if str(c).startswith(str(AG))}
    for c in sorted(classes):
        label = next((str(l) for l in g.objects(c, RDFS.label)), "")
        lines.append(f'"{name(c)}" [label="{name(c)}\\n({esc(label)})"];')
        parents = [p for p in g.objects(c, RDFS.subClassOf) if p in classes]
        for p in parents:
            lines.append(f'"{name(c)}" -> "{name(p)}" [label="subClassOf", fontsize=9];')
        if not parents:
            lines.append(f'"{name(c)}" -> "owl:Thing" [style=dotted, arrowsize=0.5];')
    for a, b in disjoint_pairs(g):
        lines.append(f'"{a}" -> "{b}" [dir=none, color="#c62828", style=dashed, label="disjoint", fontcolor="#c62828", fontsize=9, constraint=false];')
    return "\n".join(lines + ["}"])


def disjoint_pairs(g):
    pairs = []
    for d in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members = [name(m) for m in g.items(next(g.objects(d, OWL.members)))]
        pairs += [(members[i], members[j]) for i in range(len(members)) for j in range(i + 1, len(members))]
    pairs += [(name(a), name(b)) for a, b in g.subject_objects(OWL.disjointWith)]
    return pairs


def relations_dot(g, only=None):
    """Predicate individuals with ag:equivalentPredicate (blue) and ag:incompatibleWith (red) links."""
    rels = sorted(name(r) for r in g.subjects(RDF.type, AG.Relation))
    if only is not None:
        rels = [r for r in rels if r in only]
    lines = ["graph { node [shape=ellipse, style=filled, fillcolor=\"#fff7e0\", fontname=Helvetica]; edge [fontsize=9];"]
    lines += [f'"{r}";' for r in rels]
    for prop, color, style, label in ((AG.equivalentPredicate, "#1565c0", "solid", "≡ equivalentPredicate"),
                                      (AG.incompatibleWith, "#c62828", "dashed", "⊥ incompatibleWith")):
        for a, b in g.subject_objects(prop):
            if name(a) in rels and name(b) in rels:
                lines.append(f'"{name(a)}" -- "{name(b)}" [color="{color}", style={style}, label="{label}", fontcolor="{color}"];')
    return "\n".join(lines + ["}"])


def properties_table(g):
    chars = {OWL.FunctionalProperty: "functional", OWL.SymmetricProperty: "symmetric",
             OWL.TransitiveProperty: "transitive"}
    rows = []
    for kind, label in ((OWL.ObjectProperty, "object"), (OWL.DatatypeProperty, "data")):
        for p in sorted(g.subjects(RDF.type, kind)):
            rows.append({"Properti": short(p), "Jenis": label,
                         "Domain": ", ".join(short(d) for d in g.objects(p, RDFS.domain)),
                         "Range": ", ".join(short(r) for r in g.objects(p, RDFS.range)),
                         "Karakteristik": ", ".join(v for k, v in chars.items() if (p, RDF.type, k) in g)})
    return pd.DataFrame(rows)


# ---------- gold graph ----------

def gold_concept_dot(refs, concepts=None):
    """Concept-level view: one edge per reference triple (alternative accepted subjects dashed), plus the
    lecturer's concept hierarchy (skos:broader, teal)."""
    lines = ["digraph { rankdir=LR; node [shape=box, style=\"rounded,filled\", fillcolor=\"#e8f5e9\", fontname=Helvetica]; edge [fontsize=10];"]
    for r in refs:
        for i, s in enumerate(r.s):
            style = "solid" if i == 0 else "dashed"
            lines.append(f'"{esc(s)}" -> "{esc(r.o)}" [label="{esc(r.p)}  ({r.id}, w={r.weight:g})", style={style}];')
    for c, spec in (concepts or {}).items():
        for b in (spec or {}).get("broader") or []:
            lines.append(f'"{esc(b)}" [fillcolor="#e0f2f1"];')
            lines.append(f'"{esc(c)}" -> "{esc(b)}" [label="skos:broader", color="#0d9488", fontcolor="#0d9488", style=dashed];')
    return "\n".join(lines + ["}"])


def gold_reified_dot(qid, refs):
    """RDF view: each reference triple is a resource with hasSubject/hasPredicate/hasObject, criterion and weight."""
    lines = ["digraph { rankdir=LR; node [fontname=Helvetica, fontsize=10]; edge [fontsize=9];"]
    for r in refs:
        node = f"key:{qid}_{r.id}"
        lines.append(f'"{node}" [shape=box, style=filled, fillcolor="#e3f2fd", label="{node}\\na ag:ReferenceTriple"];')
        for s in r.s:
            lines.append(f'"{node}" -> "key:{esc(s)}" [label="ag:hasSubject"];')
        lines.append(f'"{node}" -> "ag:{esc(r.p)}" [label="ag:hasPredicate"];')
        lines.append(f'"{node}" -> "key:{esc(r.o)}" [label="ag:hasObject"];')
        lines.append(f'"{node}" -> "key:{qid}_{esc(r.criterion)}" [label="ag:criterion"];')
        lines.append(f'"w_{node}" [shape=plaintext, label="\\"{r.weight:g}\\"^^xsd:decimal"];')
        lines.append(f'"{node}" -> "w_{node}" [label="ag:weight"];')
        lines.append(f'"ag:{esc(r.p)}" [shape=ellipse, style=filled, fillcolor="#fff7e0"];')
    return "\n".join(lines + ["}"])


# ---------- one graded answer ----------

def triple_text(t):
    neg = "NOT " if t.negated else ""
    return f"{t.s_text} —{neg}{t.p}→ {t.o_text}"


def alignment_dot(refs, students, entries, trace):
    """Student triples (left) linked to reference triples (right) by the ledger's evidence and the reasoner."""
    status = {e.reference_id: e for e in entries}
    lines = ["digraph { rankdir=LR; nodesep=0.25; node [fontname=Helvetica, fontsize=10, shape=box, style=\"rounded,filled\"]; edge [fontsize=9];",
             'subgraph cluster_s { label="Jawaban mahasiswa (ag:StudentTriple)"; color="#90a4ae";']
    for t in students:
        concept = lambda c: f"[{c}]" if c else "[?]"
        lines.append(f'"{t.id}" [fillcolor="#eceff1", label="{esc(t.id.rsplit("_", 1)[1])}: {esc(triple_text(t))}\\n'
                     f'{concept(t.s_concept)} … {concept(t.o_concept)}"];')
    if not students:
        lines.append('"(tidak ada triple)" [fillcolor="#eceff1"];')
    lines += ["}", 'subgraph cluster_r { label="Kunci jawaban (ag:ReferenceTriple)"; color="#90a4ae";']
    for r in refs:
        e = status[r.id]
        lines.append(f'"{r.id}" [fillcolor="{STATUS_COLOR[e.status]}", fontcolor=white, '
                     f'label="{r.id}: {esc(r.s[0])} —{esc(r.p)}→ {esc(r.o)}\\n{e.status} · m={e.credit:g} · w={e.weight:g}"];')
    lines.append("}")
    sig = trace["sigmas"]
    for e in entries:
        if e.matched_by:
            lines.append(f'"{e.matched_by}" -> "{e.reference_id}" [color="{STATUS_COLOR[e.status]}", penwidth=2, '
                         f'label="matchedBy (σ={e.sigma:.2f})"];')
    for t_id, r_id in trace["contradictions"]:
        lines.append(f'"{t_id}" -> "{r_id}" [color="{STATUS_COLOR["CONTRADICTED"]}", penwidth=2, style=bold, '
                     f'label="contradicts (SWRL)", fontcolor="{STATUS_COLOR["CONTRADICTED"]}"];')
    shown = {(e.matched_by, e.reference_id) for e in entries} | set(map(tuple, trace["contradictions"]))
    for t_id, r_id in trace["aligned"]:
        if (t_id, r_id) not in shown:  # aligned concepts but a different, compatible predicate
            lines.append(f'"{t_id}" -> "{r_id}" [color="#9e9e9e", style=dotted, label="aligned σ={sig[t_id, r_id]:.2f}"];')
    return "\n".join(lines + ["}"])


def sigma_table(refs, students, sigmas):
    return pd.DataFrame([[sigmas[t.id, r.id] for r in refs] for t in students],
                        index=[f"{t.id.rsplit('_', 1)[1]}: {triple_text(t)}" for t in students],
                        columns=[r.id for r in refs])


# ---------- RDF graphs and SPARQL ----------

def merged_graph(paths):
    g = io.bind_namespaces(Graph())
    for triple in io.ontology_graph():
        g.add(triple)
    for p in paths:
        if p.exists():
            g.parse(p)
    return g


def answer_graph_paths(qid, out_dir):
    return [io.question_dir(qid) / "gold.ttl", out_dir / "answer.ttl", out_dir / "ledger.ttl"]


def run_graph_paths(run_dir, question_ids):
    paths = [io.question_dir(q) / "gold.ttl" for q in sorted(question_ids)]
    for d in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        paths += [d / "answer.ttl", d / "ledger.ttl"]
    return paths


def run_query(g, query):
    """SELECT/ASK -> DataFrame, CONSTRUCT/DESCRIBE -> Turtle text. Local graph only: SERVICE is refused."""
    if re.search(r"\bSERVICE\b", query, re.I):
        raise ValueError("SERVICE (federated queries to remote endpoints) is disabled in this demo")
    result = g.query(query)
    if result.type == "SELECT":
        return pd.DataFrame([[short(v) if v is not None else None for v in row] for row in result],
                            columns=[str(v) for v in result.vars])
    if result.type == "ASK":
        return pd.DataFrame({"ASK": [bool(result.askAnswer)]})
    out = io.bind_namespaces(Graph())
    for t in result.graph:
        out.add(t)
    return out.serialize(format="turtle")


ANSWER_QUERIES = {
    "Hitung ulang skor (Pers. 6)": PREFIXES + """
# The audit query: the score comes only from the ledger credits and the gold weights.
SELECT ?answer ((100 * (SUM(?w * ?c) - ?lambda * SUM(?w * ?k))) / SUM(?w) AS ?score)
WHERE {
  VALUES ?lambda { 0.0 }                       # λ (change to 0.5 for the penalty variant)
  ?e a ag:LedgerEntry ; ag:answer ?answer ; ag:reference ?r ; ag:credit ?c ; ag:contradiction ?k .
  ?r ag:weight ?w .
}
GROUP BY ?answer ?lambda""",
    "Status per triple acuan": PREFIXES + """
SELECT ?reference ?criterion ?weight ?status ?credit ?evidence
WHERE {
  ?e a ag:LedgerEntry ; ag:reference ?reference ; ag:status ?status ; ag:credit ?credit .
  ?reference ag:criterion ?criterion ; ag:weight ?weight .
  OPTIONAL { { ?e ag:matchedBy ?evidence } UNION { ?e ag:contradictedBy ?evidence } }
}
ORDER BY ?reference""",
    "Bukti: kalimat sumber tiap entri (PROV-O)": PREFIXES + """
SELECT ?reference ?status ?studentTriple ?sentence ?text
WHERE {
  ?e a ag:LedgerEntry ; ag:reference ?reference ; ag:status ?status .
  { ?e ag:matchedBy ?studentTriple } UNION { ?e ag:contradictedBy ?studentTriple }
  ?studentTriple prov:wasDerivedFrom ?sentence .
  ?sentence rdfs:label ?text .
}
ORDER BY ?reference""",
    "Triple acuan yang hilang, per kriteria": PREFIXES + """
SELECT ?criterion ?description ?reference ?subject ?predicate ?object
WHERE {
  ?e ag:status ag:Hilang ; ag:reference ?reference .
  ?reference ag:criterion ?criterion ; ag:hasPredicate ?predicate ; ag:hasObject ?object .
  OPTIONAL { ?criterion rdfs:comment ?description }
  ?reference ag:hasSubject ?subject .
}
ORDER BY ?criterion ?reference""",
    "Aturan kontradiksi SWRL, ditulis ulang sebagai SPARQL": PREFIXES + """
# Rules 1-3 over the alignment that Python asserted. Should give the same pairs Pellet inferred.
CONSTRUCT { ?t ag:contradicts ?r }
WHERE {
  ?t a ag:StudentTriple ; ag:hasPredicate ?pt ; ag:alignedSubject ?r ; ag:alignedObject ?r .
  ?r a ag:ReferenceTriple ; ag:hasPredicate ?pr .
  { ?t ag:negated false . ?pt (ag:incompatibleWith|^ag:incompatibleWith) ?pr . }
  UNION
  { ?t ag:negated true . ?pt (ag:equivalentPredicate|^ag:equivalentPredicate)* ?pr . }
}""",
    "Kontradiksi yang disimpulkan Pellet": PREFIXES + """
SELECT ?studentTriple ?reference ?studentPredicate ?referencePredicate ?negated
WHERE {
  ?studentTriple ag:contradicts ?reference ; ag:hasPredicate ?studentPredicate ; ag:negated ?negated .
  ?reference ag:hasPredicate ?referencePredicate .
}""",
    "Konsep jawaban yang tidak ada di tabel alias": PREFIXES + """
SELECT ?studentTriple ?role ?text
WHERE {
  ?studentTriple a ag:StudentTriple ; ?role ?concept .
  VALUES ?role { ag:hasSubject ag:hasObject }
  ?concept rdfs:label ?text .     # only unknown concepts carry their raw text as a label
}""",
    "Hierarki konsep (skos:broader+)": PREFIXES + """
# The lecturer's concept hierarchy; + follows skos:broader transitively (Glukosa -> Makanan -> ...).
SELECT ?concept ?broader
WHERE { ?concept skos:broader+ ?broader . }
ORDER BY ?concept""",
    "Kredit parsial karena konsep lebih umum": PREFIXES + """
# Partial entries where the student named a BROADER concept than the key (e.g. "makanan" for Glukosa).
SELECT ?entry ?reference ?keyConcept ?studentConcept
WHERE {
  ?entry ag:status ag:Parsial ; ag:reference ?reference ; ag:matchedBy ?t .
  { ?reference ag:hasObject ?keyConcept . ?t ag:hasObject ?studentConcept . }
  UNION
  { ?reference ag:hasSubject ?keyConcept . ?t ag:hasSubject ?studentConcept . }
  ?keyConcept skos:broader+ ?studentConcept .
}""",
    "Predikat setara (property path)": PREFIXES + """
SELECT DISTINCT ?predicate ?equivalent
WHERE {
  ?predicate a ag:Relation .
  ?predicate (ag:equivalentPredicate|^ag:equivalentPredicate)+ ?equivalent .
  FILTER (?predicate != ?equivalent)
}
ORDER BY ?predicate""",
}

RUN_QUERIES = {
    "Distribusi status per triple acuan": PREFIXES + """
SELECT ?reference (COUNT(?e) AS ?answers)
       (SUM(IF(?status = ag:Cocok, 1, 0)) AS ?matched) (SUM(IF(?status = ag:Parsial, 1, 0)) AS ?partial)
       (SUM(IF(?status = ag:Hilang, 1, 0)) AS ?missing) (SUM(IF(?status = ag:Kontradiksi, 1, 0)) AS ?contradicted)
WHERE { ?e a ag:LedgerEntry ; ag:reference ?reference ; ag:status ?status . }
GROUP BY ?reference
ORDER BY ?reference""",
    "Skor semua jawaban (hitung ulang)": PREFIXES + """
SELECT ?answer ((100 * SUM(?w * ?c)) / SUM(?w) AS ?score)
WHERE { ?e a ag:LedgerEntry ; ag:answer ?answer ; ag:reference ?r ; ag:credit ?c . ?r ag:weight ?w . }
GROUP BY ?answer
ORDER BY DESC(?score)""",
    "Jawaban yang bertentangan dengan kunci": PREFIXES + """
SELECT ?answer ?reference ?studentTriple ?text
WHERE {
  ?e ag:status ag:Kontradiksi ; ag:answer ?answer ; ag:reference ?reference ; ag:contradictedBy ?studentTriple .
  ?studentTriple prov:wasDerivedFrom ?s . ?s rdfs:label ?text .
}""",
    "Kriteria yang paling sering terlewat": PREFIXES + """
SELECT ?criterion (COUNT(?e) AS ?missingEntries)
WHERE { ?e ag:status ag:Hilang ; ag:reference ?r . ?r ag:criterion ?criterion . }
GROUP BY ?criterion
ORDER BY DESC(?missingEntries)""",
}
