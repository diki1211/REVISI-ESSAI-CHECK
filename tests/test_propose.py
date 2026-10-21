"""Drafting gold triples from the reference answer: rule (offline) and LLM (stubbed); never writes gold.yaml."""
import json
import shutil

import pytest

from autograde import gold, io, llm, propose
from autograde.cli import main


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A copy of the project files propose needs, so nothing in the real data folder changes."""
    for name in ("config", "ontology"):
        shutil.copytree(io.ROOT / name, tmp_path / name)
    shutil.copytree(io.question_dir("Q1"), tmp_path / "data" / "questions" / "Q1")
    monkeypatch.setattr(io, "ROOT", tmp_path)
    monkeypatch.setattr(llm, "cache_dir", lambda: tmp_path / "cache")
    return tmp_path


def test_rule_draft_recovers_q1_key():
    draft = propose.propose("Q1", "rule")
    got = [(t["s"], t["p"], t["o"], t["in_gold"]) for t in draft["triples"]]
    assert got == [(["Tumbuhan"], "menggunakan", "Cahaya", "R1"), (["Fotosintesis"], "mengonsumsi", "CO2", "R2"),
                   (["Fotosintesis"], "mengonsumsi", "Air", "R3"), (["Fotosintesis"], "menghasilkan", "Glukosa", "R4"),
                   (["Fotosintesis"], "menghasilkan", "Oksigen", "R5")]
    assert draft["comparison"] == {"proposed": 5, "in_gold": 5, "gold_total": 5, "gold_covered": 5,
                                   "precision": 1.0, "recall": 1.0, "weighted_recall": 1.0}
    assert all(t["criterion"] is None and t["weight"] == 1.0 for t in draft["triples"])  # the lecturer decides
    assert draft["triples"][0]["source"].startswith("Tumbuhan menggunakan cahaya matahari")


def test_rule_skips_negation_and_matches_english_inflection():
    preds = io.load_predicates()
    sents = [("X_s1", "Fotosintesis tidak menghasilkan karbon dioksida.")]
    props, log = propose.propose_rule(sents, {"CO2": {"aliases": ["karbon dioksida"]}}, preds, "id")
    assert props == [] and log[0]["reason"] == "negated"
    sents = [("X_s1", "DHCP has largely replaced RARP and BOOTP.")]
    props, _ = propose.propose_rule(sents, {"DHCP": {}, "RARP": {"aliases": ["rarp", "bootp"]}}, preds, "en")
    assert [(p["s"], p["p"], p["o"]) for p in props] == [("DHCP", "replaces", "RARP")]


def test_unknown_spans_become_new_concepts():
    props, _ = propose.propose_rule([("X_s1", "Klorofil menyerap cahaya merah dan cahaya biru.")], {},
                                    io.load_predicates(), "id")
    assert [(p["s"], p["o"], p["o_new"]) for p in props] == [("Klorofil", "CahayaMerah", True),
                                                             ("Klorofil", "CahayaBiru", True)]


def test_write_never_touches_gold_yaml(root):
    before = (root / "data" / "questions" / "Q1" / "gold.yaml").read_bytes()
    out, md = propose.write(propose.propose("Q1", "rule"))
    assert out == root / "data" / "questions" / "Q1" / "gold_proposed.yaml" and md.exists()
    assert (root / "data" / "questions" / "Q1" / "gold.yaml").read_bytes() == before
    saved = io.load_yaml(out)
    assert saved["status"] == "draft" and "Never read by grading" in saved["note"]
    assert "| P1 | Tumbuhan | menggunakan | Cahaya |" in md.read_text()
    assert [r.id for r in gold.load("Q1")[2]] == ["R1", "R2", "R3", "R4", "R5"]  # grading still reads gold.yaml


def test_new_question_without_gold(root):
    d = root / "data" / "questions" / "Q2"
    d.mkdir()
    (d / "reference_answer.md").write_text("Respirasi menghasilkan energi.", encoding="utf-8")
    io.save_yaml({"question_id": "Q2", "criteria": [{"id": "K1", "description": "hasil"}]}, d / "rubric.yaml")
    draft = propose.propose("Q2", "rule")
    assert draft["comparison"] is None
    assert [(t["s"], t["p"], t["o"]) for t in draft["triples"]] == [(["Respirasi"], "menghasilkan", "Energi")]
    assert draft["new_concepts"] == {"Respirasi": {"aliases": ["respirasi"]}, "Energi": {"aliases": ["energi"]}}


def test_llm_draft_checked_and_weighted(root):
    reply = {"triples": [
        {"sentence_ids": ["S2"], "subject": "Fotosintesis", "predicate": "mengonsumsi", "object": "karbon dioksida",
         "criterion": "K1_Bahan", "importance": "essential"},
        {"sentence_ids": ["S2"], "subject": "Fotosintesis", "predicate": "menghasilkan", "object": "oksigen",
         "criterion": "K2_Produk", "importance": "supporting"},
        {"sentence_ids": ["S1"], "subject": "Tumbuhan", "predicate": "menghasilkan", "object": "pati",
         "criterion": "K2_Produk", "importance": "optional"},              # not in the cited sentence
        {"sentence_ids": ["S1"], "subject": "Tumbuhan", "predicate": "other", "object": "cahaya matahari",
         "criterion": "K3_Energi", "importance": "optional"}]}
    seen = {}

    def backend(system, user, schema, cfg):
        seen.update(system=system, user=user, schema=schema)
        return json.dumps(reply)

    draft = propose.propose("Q1", "llm", backend=backend)
    assert [(t["o"], t["criterion"], t["weight"], t["in_gold"]) for t in draft["triples"]] == \
        [("CO2", "K1_Bahan", 2.0, "R2"), ("Oksigen", "K2_Produk", 1.0, "R5")]
    assert sorted(x["reason"] for x in draft["log"]) == ["not_grounded", "other_predicate"]
    assert "K1_Bahan: Menyebutkan bahan fotosintesis" in seen["user"]
    crit_enum = seen["schema"]["properties"]["triples"]["items"]["properties"]["criterion"]["enum"]
    assert crit_enum == ["K1_Bahan", "K2_Produk", "K3_Energi"]
    assert draft["comparison"]["precision"] == 1.0 and draft["comparison"]["recall"] == 0.4
    assert draft["proposed_by"].endswith("(AI draft)")


def test_accepted_triples_validate_as_gold():
    draft = propose.propose("Q1", "rule")
    snippet = propose.as_gold_yaml(draft, {"P2", "P5"})
    assert [(t["id"], t["o"]) for t in snippet["triples"]] == [("R1", "CO2"), ("R2", "Oksigen")]
    d = io.question_dir("Q1")
    g = {**io.load_yaml(d / "gold.yaml"), "triples": [{**t, "criterion": "K1_Bahan"} for t in snippet["triples"]]}
    rubric = {"question_id": "Q1", "criteria": [{"id": "K1_Bahan", "description": "x"}]}
    assert len(gold.validate(g, rubric, {"mengonsumsi", "menghasilkan"})) == 2


def test_cli_no_write(capsys, monkeypatch):
    monkeypatch.setattr(propose, "write", lambda *a: pytest.fail("--no-write must not write"))
    main(["propose", "--question", "Q1", "--no-write"])
    assert "5/5 already in gold.yaml" in capsys.readouterr().out


def test_unknown_method():
    with pytest.raises(propose.ProposalError, match="unknown method"):
        propose.propose("Q1", "magic")
