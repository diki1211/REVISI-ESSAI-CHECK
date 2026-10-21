"""Semantic Explorer graph: built from a graded answer's saved files; the page escapes student text."""
import json

import explorer
from autograde import io, pipeline
from test_pipeline import STUB


def graded(tmp_path, qid, answer_id, text):
    ctx = pipeline.Context.load(qid, reasoner="sparql", cosine=STUB)
    pipeline.run_answer(ctx, answer_id, text, "gold", tmp_path / answer_id, use_llm_feedback=False)
    return ctx, tmp_path / answer_id


def test_contradiction_edge_and_reasoning(tmp_path):
    text = io.load_answers(include_saf=True).set_index("answer_id").text["SAF_CSMA_V002"]
    ctx, d = graded(tmp_path, "SAF_CSMA", "SAF_CSMA_V002", text)
    g = explorer.build(ctx, [d], ctx.params)
    kinds = {(e["from"], e["to"], e["kind"]) for e in g["edges"]}
    assert ("ans:SAF_CSMA_V002_t1", "key:SAF_CSMA_R1", "inferred") in kinds
    assert ("ag:decreases", "ag:increases", "ontology") in kinds
    reasoning = g["details"]["ans:SAF_CSMA_V002_t1"]["sections"][1]["items"][0]
    assert "Aturan 1" in reasoning and "incompatibleWith" in reasoning
    assert {e["from"] for e in g["edges"]} | {e["to"] for e in g["edges"]} <= {n["id"] for n in g["nodes"]}


def test_match_edges_for_worked_example(tmp_path):
    text = io.load_yaml(io.ROOT / "tests" / "fixtures" / "worked_example.yaml")["text"]
    ctx, d = graded(tmp_path, "Q1", "Q1_A07", text)
    g = explorer.build(ctx, [d], ctx.params)
    matches = {(e["from"], e["to"]) for e in g["edges"] if e["kind"] == "match"}
    assert ("ans:Q1_A07_t1", "key:Q1_R1") in matches  # menyerap ≡ menggunakan
    assert ("ans:Q1_A07_t2", "key:Q1_R4") in matches  # "makanan" is broader than Glukosa: partial
    assert ("key:Glukosa", "key:Makanan", "hierarchy") in {(e["from"], e["to"], e["kind"]) for e in g["edges"]}
    assert "lebih umum dari Glukosa" in " ".join(g["details"]["ans:Q1_A07_t2"]["sections"][1]["items"])
    assert "equivalentPredicate" in json.dumps(g["edges"])


def test_page_cannot_be_broken_by_student_text(tmp_path):
    ctx, d = graded(tmp_path, "Q1", "Q1_A07", "Tumbuhan menyerap sinar matahari.")
    g = explorer.build(ctx, [d], ctx.params)
    g["details"]["ans:Q1_A07"]["sections"][0]["items"] = ["</script><script>alert(1)</script>"]
    page = explorer.html(g)
    data = page.split("const D = ", 1)[1]
    assert "</script><script>alert" not in data and "<\\/script><script>alert(1)" in data
