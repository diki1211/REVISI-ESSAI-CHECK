import copy

import pytest
from rdflib import RDF, Graph

from autograde import gold, io
from autograde.io import AG, KEY

RELS = {"menggunakan", "menyerap", "mengonsumsi", "menghasilkan"}


@pytest.fixture
def q1():
    d = io.question_dir("Q1")
    return io.load_yaml(d / "gold.yaml"), io.load_yaml(d / "rubric.yaml")


def test_valid_gold(q1):
    refs = gold.validate(*q1, RELS)
    assert [r.id for r in refs] == ["R1", "R2", "R3", "R4", "R5"]
    assert refs[1].s == ["Fotosintesis", "Tumbuhan"]


@pytest.mark.parametrize("mutate, msg", [
    (lambda g: g["triples"][0].update(weight=0), "greater than 0"),
    (lambda g: g["triples"][0].update(p="memakan"), "unknown predicate"),
    (lambda g: g["triples"].pop(0), "K3_Energi has no reference triple"),
    (lambda g: g["triples"][0].update(o="Klorofil"), "undeclared concept"),
])
def test_validation_errors(q1, mutate, msg):
    g, rubric = copy.deepcopy(q1[0]), q1[1]
    mutate(g)
    with pytest.raises(gold.GoldError, match=msg):
        gold.validate(g, rubric, RELS)


def test_predicate_vocab_checks():
    good = {"predicates": [{"id": "menggunakan", "aliases": ["memakai"]}, {"id": "other", "aliases": []}]}
    gold.check_predicates(good, RELS)
    with pytest.raises(gold.GoldError, match="missing from the ontology"):
        gold.check_predicates({"predicates": [{"id": "memasak", "aliases": []}]}, RELS)
    with pytest.raises(gold.GoldError, match="also predicate ids"):
        gold.check_predicates({"predicates": [{"id": "menggunakan", "aliases": ["menyerap"]},
                                              {"id": "menyerap", "aliases": []}]}, RELS)


def test_gold_ttl_round_trip(tmp_path, q1):
    refs = gold.validate(*q1, RELS)
    path = tmp_path / "gold.ttl"
    gold.to_graph("Q1", refs, q1[1]).serialize(path, format="turtle")
    g = Graph().parse(path)
    ids = sorted(io.local_name(s) for s in g.subjects(RDF.type, AG.ReferenceTriple))
    assert ids == [f"Q1_{r.id}" for r in refs]
    assert len(list(g.objects(KEY.Q1_R2, AG.hasSubject))) == 2
    assert str(KEY.Q1_R2).startswith("http://example.org/autograde/key/")
    assert str(AG.hasSubject).startswith("http://example.org/autograde/ontology#")
    assert len(g) == len(gold.to_graph("Q1", refs, q1[1]))


@pytest.mark.parametrize("broader, msg", [(["Buah"], "is not declared"), (["Tumbuhan"], "cycle")])
def test_hierarchy_validation(q1, broader, msg):
    g = copy.deepcopy(q1[0])
    g["concepts"]["Tumbuhan"] = {"aliases": [], "broader": ["Fotosintesis"]}
    g["concepts"]["Fotosintesis"] = {"aliases": [], "broader": broader}
    if broader == ["Buah"]:
        g["concepts"]["Tumbuhan"] = None
    with pytest.raises(gold.GoldError, match=msg):
        gold.validate(g, q1[1], RELS)


def test_gold_ttl_has_skos_hierarchy(q1):
    from rdflib.namespace import SKOS
    g = gold.to_graph("Q1", gold.validate(*q1, RELS), q1[1], q1[0]["concepts"])
    assert (KEY.Glukosa, SKOS.broader, KEY.Makanan) in g
    assert gold.ancestors(q1[0]["concepts"])["Glukosa"] == {"Makanan"}
