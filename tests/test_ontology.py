import owlready2 as o
import pytest

from autograde.io import ontology_path

CLASSES = ["Concept", "Relation", "Triple", "ReferenceTriple", "StudentTriple", "Criterion",
           "Answer", "Sentence", "LedgerEntry", "Status"]
OBJECT_PROPS = ["hasSubject", "hasPredicate", "hasObject", "criterion", "equivalentPredicate",
                "incompatibleWith", "alignedSubject", "alignedObject", "contradicts", "inAnswer",
                "answer", "reference", "matchedBy", "contradictedBy", "status"]
DATA_PROPS = ["weight", "negated", "credit", "contradiction"]


@pytest.fixture(scope="module")
def onto():
    return o.World().get_ontology(ontology_path().as_uri()).load()


def test_classes_and_properties_exist(onto):
    for name in CLASSES + OBJECT_PROPS + DATA_PROPS:
        assert onto[name] is not None, name
    assert onto.StudentTriple in onto.Triple.subclasses()
    assert onto.world["http://www.w3.org/ns/prov#wasDerivedFrom"] is not None


def test_characteristics(onto):
    eq = onto.equivalentPredicate
    assert o.SymmetricProperty in eq.is_a and o.TransitiveProperty in eq.is_a
    assert o.SymmetricProperty in onto.incompatibleWith.is_a
    assert o.FunctionalProperty in onto.hasPredicate.is_a
    assert o.FunctionalProperty not in onto.hasSubject.is_a  # several accepted subjects


def test_three_rules_present(onto):
    rules = [str(r) for r in onto.world.rules()]
    assert len(rules) == 3
    assert sum("negated(?t, false)" in r for r in rules) == 1
    assert sum("negated(?t, true)" in r for r in rules) == 2


def test_status_individuals(onto):
    names = {"Cocok", "Parsial", "Hilang", "Kontradiksi"}
    assert {i.name for i in onto.Status.instances()} == names
    assert any({e.name for e in d.entities} == names for d in onto.different_individuals())


def test_triples_disjoint(onto):
    assert any(set(d.entities) == {onto.ReferenceTriple, onto.StudentTriple} for d in onto.disjoint_classes())


def test_indonesian_labels(onto):
    for name in CLASSES:
        assert [l.lang for l in onto[name].label] == ["id"], name
    assert [str(l) for l in onto.StudentTriple.label] == ["Triple Jawaban"]
