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
    # Rule 4: a credited conclusion whose required premise was not credited (diagnostic; never changes the score).
    # Every ledger entry has exactly one asserted status and every status asserts isCredited, so "not credited"
    # is a positive fact here: the open-world assumption is respected (no negation as failure).
    "LedgerEntry(?ec) ^ reference(?ec, ?c) ^ status(?ec, ?sc) ^ isCredited(?sc, true) ^ requiresPremise(?c, ?p) ^ "
    "LedgerEntry(?ep) ^ reference(?ep, ?p) ^ answer(?ec, ?a) ^ answer(?ep, ?a) ^ status(?ep, ?sp) ^ "
    "isCredited(?sp, false) -> lacksPremise(?ec, ?ep)",
]
CREDITED = {"Cocok": True, "Parsial": True, "Hilang": False, "Kontradiksi": False}  # status -> earns credit


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
        class requiresPremise(o.ObjectProperty): domain = [ReferenceTriple]; range = [ReferenceTriple]
        class lacksPremise(o.ObjectProperty): domain = [LedgerEntry]; range = [LedgerEntry]  # inferred by Rule 4

        class weight(o.DataProperty, o.FunctionalProperty): domain = [ReferenceTriple]; range = [float]
        class negated(o.DataProperty, o.FunctionalProperty): domain = [StudentTriple]; range = [bool]
        class credit(o.DataProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [float]
        class contradiction(o.DataProperty, o.FunctionalProperty): domain = [LedgerEntry]; range = [float]
        class isCredited(o.DataProperty, o.FunctionalProperty): domain = [Status]; range = [bool]

    with prov:
        class wasDerivedFrom(o.ObjectProperty):
            namespace = prov
            domain = [onto.StudentTriple]; range = [onto.Sentence]

    with onto:
        for cls, label in LABELS.items():
            onto[cls].label = [o.locstr(label, lang="id")]
        o.AllDisjoint([ReferenceTriple, StudentTriple])
        statuses = [Status(name) for name in CREDITED]
        o.AllDifferent(statuses)
        for st in statuses:
            st.isCredited = CREDITED[st.name]
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
