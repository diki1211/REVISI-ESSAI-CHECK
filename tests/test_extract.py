import json

import pytest

from autograde import extract, llm
from autograde.segment import split

PREDS = {"predicates": [
    {"id": "menggunakan", "description": "d", "aliases": ["memakai"]},
    {"id": "menghasilkan", "description": "d", "aliases": ["melepaskan"]},
    {"id": "other", "description": "d", "aliases": []}]}
SENTS = split("Q1_A07", "Fotosintesis terjadi di daun. Proses ini melepaskan oksigen. Tumbuhan memakai cahaya.")


@pytest.fixture(autouse=True)
def tmp_cache(monkeypatch, tmp_path):
    # a fresh cache per call: tests send the same prompt with different fake replies
    counter = iter(range(1000))
    monkeypatch.setattr(llm, "cache_dir", lambda: tmp_path / str(next(counter)))


def run(triples):
    backend = lambda *a: json.dumps({"triples": triples})
    return extract.extract_llm("Q1_A07", SENTS, backend=backend, predicates=PREDS, threshold=0.5)


def t(sids, s, p, o, neg=False):
    return {"sentence_ids": sids, "subject": s, "predicate": p, "object": o, "negated": neg}


def test_alias_mapped_and_ids_assigned():
    kept, log = run([t(["S3"], "tumbuhan", "memakai", "cahaya")])
    assert log == []
    assert kept[0].p == "menggunakan" and kept[0].id == "Q1_A07_t1"
    assert kept[0].sentence_ids == ["Q1_A07_s3"]


def test_hallucinated_object_dropped():
    kept, log = run([t(["S3"], "tumbuhan", "memakai", "air")])
    assert kept == [] and log[0]["reason"] == "not_grounded"


def test_subject_from_earlier_cited_sentence_kept():
    kept, _ = run([t(["S1", "S2"], "fotosintesis", "melepaskan", "oksigen")])
    assert kept[0].p == "menghasilkan" and kept[0].sentence_ids == ["Q1_A07_s1", "Q1_A07_s2"]
    kept, log = run([t(["S2"], "fotosintesis", "melepaskan", "oksigen")])
    assert kept == [] and log[0]["reason"] == "not_grounded"


def test_other_predicate_and_bad_sentence_dropped():
    kept, log = run([t(["S1"], "fotosintesis", "other", "daun"), t(["S9"], "a", "memakai", "b")])
    assert kept == [] and [l["reason"] for l in log] == ["other_predicate", "bad_sentence_id"]


def test_schema_enums():
    sch = extract.schema(["S1", "S2"], PREDS)
    item = sch["properties"]["triples"]["items"]["properties"]
    assert item["sentence_ids"]["items"]["enum"] == ["S1", "S2"]
    assert "memakai" in item["predicate"]["enum"] and "other" in item["predicate"]["enum"]


def test_empty_answer_skips_llm():
    assert extract.extract_llm("A", [], backend=lambda *a: pytest.fail("called")) == ([], [])


def test_gold_mode(tmp_path):
    path = tmp_path / "a.yaml"
    path.write_text("triples:\n  - {s: tumbuhan, p: memakai, o: cahaya, sentences: [3]}\n")
    [st] = extract.extract_gold("Q1_A07", path=path, predicates=PREDS)
    assert (st.p, st.sentence_ids, st.negated) == ("menggunakan", ["Q1_A07_s3"], False)
