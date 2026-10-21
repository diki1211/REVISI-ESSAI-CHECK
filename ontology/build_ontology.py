"""Generate the starter ontology/autograde.owl (RDF/XML) from plan Section 6.

The ontology is meant to be opened, checked and refined in Protégé 5.6.4 (SWRLTab).
Re-running this script overwrites autograde.owl, so stop using it once the file is edited in Protégé.

    python ontology/build_ontology.py
"""
from pathlib import Path

import owlready2 as o

HERE = Path(__file__).resolve().parent
IRI = "http://example.org/autograde/ontology#"  # schema namespace (prefix ag:)

# Every predicate id in config/predicates.yaml except `other` must exist here.
# Q1 (Indonesian; validate with the lecturer) and the SAF subset (English; AI-drafted).
RELATIONS = ["menggunakan", "menyerap", "mengonsumsi", "menghasilkan",
             "is_a", "uses", "utilizes", "requires", "has", "lacks", "assigns", "provides", "replaces",
             "transmits", "allows", "enables", "prevents", "decreases", "increases",
             "causes", "determines", "follows", "precedes", "reduces"]
EQUIVALENT = [("menyerap", "menggunakan"), ("utilizes", "uses"), ("enables", "allows"), ("provides", "assigns")]
INCOMPATIBLE = [("menghasilkan", "mengonsumsi"), ("has", "lacks"), ("allows", "prevents"),
                ("decreases", "increases"), ("causes", "prevents"), ("follows", "precedes")]

LABELS = {  # Indonesian rdfs:label per class (Protégé can render labels instead of IRIs)
    "Concept": "Konsep", "Relation": "Relasi", "Triple": "Triple", "ReferenceTriple": "Triple Acuan",
    "StudentTriple": "Triple Jawaban", "Criterion": "Kriteria", "Answer": "Jawaban", "Sentence": "Kalimat",
    "LedgerEntry": "Entri Ledger", "Status": "Status",
}

RULES = [
    # Rule 1: incompatible predicate, not negated
    "StudentTriple(?t) ^ ReferenceTriple(?r) ^ hasPredicate(?t, ?pt) ^ hasPredicate(?r, ?pr) ^ "
    "incompatibleWith(?pt, ?pr) ^ negated(?t, false) ^ alignedSubject(?t, ?r) ^ alignedObject(?t, ?r) "
    "-> contradicts(?t, ?r)",
    # Rule 2: explicit negation of the same predicate
    "StudentTriple(?t) ^ ReferenceTriple(?r) ^ hasPredicate(?t, ?p) ^ hasPredicate(?r, ?p) ^ "
    "negated(?t, true) ^ alignedSubject(?t, ?r) ^ alignedObject(?t, ?r) -> contradicts(?t, ?r)",
    # Rule 3: negation of an equivalent predicate
    "StudentTriple(?t) ^ ReferenceTriple(?r) ^ hasPredicate(?t, ?pt) ^ hasPredicate(?r, ?pr) ^ "
    "equivalentPredicate(?pt, ?pr) ^ negated(?t, true) ^ alignedSubject(?t, ?r) ^ alignedObject(?t, ?r) "
    "-> contradicts(?t, ?r)",
]


def build(world=None):
    world = world or o.World()
    onto = world.get_ontology(IRI)
    prov = onto.get_namespace("http://www.w3.org/ns/prov#")
    with onto:
        class Concept(o.Thing): pass
        class Relation(o.Thing): pass
        class Triple(o.Thing): pass
        class ReferenceTriple(Triple): pass
        class StudentTriple(Triple): pass
        class Criterion(o.Thing): pass
        class Answer(o.Thing): pass
        class Sentence(o.Thing): pass
        class LedgerEntry(o.Thing): pass
        class Status(o.Thing): pass

        class hasSubject(o.ObjectProperty): domain = [Triple]; range = [Concept]  # not functional: accepted subjects
        class hasPredicate(o.ObjectProperty, o.FunctionalProperty): domain = [Triple]; range = [Relation]
        class hasObject(o.ObjectProperty, o.FunctionalProperty): domain = [Triple]; range = [Concept]
        class criterion(o.ObjectProperty, o.FunctionalProperty): domain = [ReferenceTriple]; range = [Criterion]
        class equivalentPredicate(o.ObjectProperty, o.SymmetricProperty, o.TransitiveProperty):
            domain = [Relation]; range = [Relation]
        class incompatibleWith(o.ObjectProperty, o.SymmetricProperty): domain = [Relation]; range = [Relation]
        class alignedSubject(o.ObjectProperty): domain = [StudentTriple]; range = [ReferenceTriple]
        class alignedObject(o.ObjectProperty): domain = [StudentTriple]; range = [ReferenceTriple]
        class contradicts(o.ObjectProperty): domain = [StudentTriple]; range = [ReferenceTriple]
        class inAnswer(o.ObjectProperty, o.FunctionalProperty): domain = [StudentTriple]; range = [Answer]
        class answer(o.ObjectProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [Answer]
        class reference(o.ObjectProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [ReferenceTriple]
        class matchedBy(o.ObjectProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [StudentTriple]
        class contradictedBy(o.ObjectProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [StudentTriple]
        class status(o.ObjectProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [Status]

        class weight(o.DataProperty, o.FunctionalProperty): domain = [ReferenceTriple]; range = [float]
        class negated(o.DataProperty, o.FunctionalProperty): domain = [StudentTriple]; range = [bool]
        class credit(o.DataProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [float]
        class contradiction(o.DataProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [float]

    with prov:
        class wasDerivedFrom(o.ObjectProperty):
            namespace = prov
            domain = [onto.StudentTriple]; range = [onto.Sentence]

    with onto:
        for cls, label in LABELS.items():
            onto[cls].label = [o.locstr(label, lang="id")]
        o.AllDisjoint([ReferenceTriple, StudentTriple])
        o.AllDifferent([Status(name) for name in ("Cocok", "Parsial", "Hilang", "Kontradiksi")])
        rel = {name: Relation(name) for name in RELATIONS}
        for a, b in EQUIVALENT:
            rel[a].equivalentPredicate.append(rel[b])
        for a, b in INCOMPATIBLE:
            rel[a].incompatibleWith.append(rel[b])
        for text in RULES:
            o.Imp().set_as_rule(text)
    return onto


if __name__ == "__main__":
    onto = build()
    onto.save(str(HERE / "autograde.owl"), format="rdfxml")
    (HERE / "rules.swrl.txt").write_text(
        "\n\n".join(f"# Rule {i}\n{r}" for i, r in enumerate(RULES, 1)) + "\n", encoding="utf-8")
    print("wrote", HERE / "autograde.owl")
