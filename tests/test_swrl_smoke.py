"""Phase 1 step-5 ABox: one reference triple, one incompatible student triple, aligned."""
import owlready2 as o
import pytest

from autograde.io import java_exe, ontology_path

pytestmark = pytest.mark.pellet


def run(aligned=True, negated=False):
    o.JAVA_EXE = java_exe()
    world = o.World()
    base = world.get_ontology(ontology_path().as_uri()).load()
    abox = world.get_ontology("http://example.org/autograde/test#")
    with abox:
        r = base.ReferenceTriple("R2")
        r.hasPredicate = base.mengonsumsi
        t = base.StudentTriple("t1")
        t.hasPredicate = base.menghasilkan
        t.negated = negated
        if aligned:
            t.alignedSubject = [r]
            t.alignedObject = [r]
    o.sync_reasoner_pellet(world, infer_property_values=True, infer_data_property_values=True, debug=0)
    return [x.name for x in t.contradicts]


def test_contradiction_inferred():
    assert run() == ["R2"]


def test_no_contradiction_without_alignment():
    assert run(aligned=False) == []  # open world: absence is not a contradiction


def test_negated_incompatible_is_not_contradiction():
    assert run(negated=True) == []
