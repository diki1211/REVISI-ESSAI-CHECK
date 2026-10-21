import importlib.util
import time

import pytest

from autograde import io, reason
from autograde.match import Relations, contradictions
from autograde.models import ReferenceTriple, StudentTriple

# Relations: a ≡ b ≡ c (2-hop chain a..c), a incompatibleWith x, y unrelated.
CASES = [  # (name, ref predicate, [(student predicate, negated, aligned)], expected contradicting triple numbers)
    ("incompatible", "a", [("x", False, True)], {1}),
    ("incompatible symmetric", "x", [("a", False, True)], {1}),
    ("negated incompatible", "a", [("x", True, True)], set()),
    ("negated same", "a", [("a", True, True)], {1}),
    ("negated equivalent 2-hop", "a", [("c", True, True)], {1}),
    ("equivalent not negated", "a", [("c", False, True)], set()),
    ("unaligned", "a", [("x", False, False)], set()),
    ("negated unrelated", "a", [("y", True, True)], set()),
    ("missing", "a", [], set()),
    ("mixed", "b", [("a", False, True), ("x", False, True), ("c", True, True)], {3}),
]


@pytest.fixture(scope="module")
def test_ontology(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("build_ontology", io.ROOT / "ontology" / "build_ontology.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.RELATIONS, mod.EQUIVALENT, mod.INCOMPATIBLE = ["a", "b", "c", "x", "y"], [("a", "b"), ("b", "c")], [("a", "x")]
    path = tmp_path_factory.mktemp("onto") / "autograde.owl"
    mod.build().save(str(path), format="rdfxml")
    mp = pytest.MonkeyPatch()
    mp.setattr(io, "ontology_path", lambda: path)
    io.ontology_graph.cache_clear()
    yield path
    mp.undo()
    io.ontology_graph.cache_clear()


def case_inputs(i, ref_p, students):
    answer = f"C{i}_A"
    ref = ReferenceTriple(id="R1", s="A", p=ref_p, o="B", criterion="K", weight=1)
    sts = [StudentTriple(id=f"{answer}_t{j}", answer_id=answer, s_text="a", p=p, o_text="b", negated=neg,
                         sentence_ids=[f"{answer}_s1"]) for j, (p, neg, _) in enumerate(students, 1)]
    aligned = [(t.id, "R1") for t, (_, _, al) in zip(sts, students) if al]
    return [ref], sts, aligned


def expected(i, nums):
    return {(f"C{i}_A_t{n}", "R1") for n in nums}


@pytest.mark.pellet
def test_parity_pellet_sparql_python(test_ontology):
    pellet = reason.PelletReasoner()
    rel = Relations.from_ontology()
    start = time.time()
    for i, (name, ref_p, students, want) in enumerate(CASES):
        refs, sts, aligned = case_inputs(i, ref_p, students)
        sigmas = {(t.id, "R1"): (1.0 if (t.id, "R1") in aligned else 0.0) for t in sts}
        py = contradictions(refs, sts, sigmas, {"tau_h": 0.8}, rel)
        sp = reason.contradictions_sparql("Q9", refs, sts, aligned)
        pe = pellet.contradictions("Q9", refs, sts, aligned)
        assert py == sp == pe == expected(i, want), name
    assert pellet.residue() == []  # no individuals left over from earlier answers
    assert (time.time() - start) / len(CASES) < 10


def test_sparql_alone(test_ontology):
    for i, (name, ref_p, students, want) in enumerate(CASES):
        refs, sts, aligned = case_inputs(i, ref_p, students)
        assert reason.contradictions_sparql("Q9", refs, sts, aligned) == expected(i, want), name
