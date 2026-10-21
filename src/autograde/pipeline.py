"""Orchestrates one answer, one question, or a whole split; writes outputs/runs/<run_id>/<answer_id>/."""
import json
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from autograde import extract, feedback, gold, io, ledger, reason, segment
from autograde.match import Relations, match
from autograde.normalize import ConceptIndex, Embedder, fill_concepts, make_sim
from autograde.score import score


class ParityError(RuntimeError):
    pass


@dataclass
class Context:
    qid: str
    gold_raw: dict
    rubric: dict
    refs: list
    index: ConceptIndex
    sim: object
    rel: Relations
    params: dict
    reasoner: str
    broader_similarity: float

    @classmethod
    def load(cls, qid, params=None, reasoner=None, cosine=None):
        gold_raw, rubric, refs = gold.load(qid)
        if not (io.question_dir(qid) / "gold.ttl").exists():
            gold.build(qid)
        cfg = io.load_config()
        broader = float(cfg.get("broader_similarity", 0.70))
        sim = make_sim(cosine or Embedder().cosine, gold.ancestors(gold_raw["concepts"]), broader)
        return cls(qid, gold_raw, rubric, refs, ConceptIndex(gold_raw["concepts"]), sim, Relations.from_ontology(),
                   params or io.load_params(), reasoner or cfg["reasoner"], broader)


def grade(ctx, answer_id, students, params=None):
    """Matching, reasoning, ledger and score for already-extracted triples (no files written).

    Returns (students, entries, score, trace); trace holds σ for every pair, the aligned pairs given to the
    reasoner, and the contradictions it inferred."""
    params = params or ctx.params
    if not params["tau_l"] <= ctx.broader_similarity < params["tau_h"]:
        raise ValueError(f"broader_similarity {ctx.broader_similarity} must lie in the partial band "
                         f"[{params['tau_l']}, {params['tau_h']}) so a broader concept earns partial credit")
    students = fill_concepts(students, ctx.index)
    results, sigmas, aligned = match(ctx.refs, students, params, ctx.sim, ctx.rel)
    contra = reason.contradictions(ctx.qid, ctx.refs, students, aligned, ctx.reasoner)
    entries = ledger.build(answer_id, ctx.refs, results, sigmas, contra, students, params)
    trace = {"sigmas": sigmas, "aligned": aligned, "contradictions": sorted(contra)}
    return students, entries, score(answer_id, entries, params), trace


def extract_triples(ctx, answer_id, sentences, mode):
    if mode == "llm":
        return extract.extract_llm(answer_id, sentences, language=ctx.rubric.get("language", "id"))
    if mode == "gold":
        return extract.extract_gold(answer_id), []
    raise ValueError(f"unknown mode {mode!r}")


def run_answer(ctx, answer_id, text, mode, out_dir, use_llm_feedback=True):
    sentences = segment.split(answer_id, text)
    students, log = extract_triples(ctx, answer_id, sentences, mode)
    students, entries, sc, trace = grade(ctx, answer_id, students)
    ledger.write(out_dir, ctx.qid, entries)
    ledger.answer_graph(answer_id, students, sentences, ctx.qid, trace).serialize(out_dir / "answer.ttl", format="turtle")
    sc.sparql_score = ledger.recompute_sparql(out_dir / "ledger.ttl", io.question_dir(ctx.qid) / "gold.ttl",
                                              ctx.params["lambda"])
    if abs(sc.score - sc.sparql_score) >= 1e-9:
        raise ParityError(f"{answer_id}: Python score {sc.score} != SPARQL score {sc.sparql_score}")
    fb = feedback.generate(answer_id, entries, ctx.refs, ctx.rubric, sentences, sc.score, use_llm=use_llm_feedback)
    io.save_json(sentences, out_dir / "sentences.json")
    io.save_json([t.model_dump() for t in students], out_dir / "student_triples.json")
    io.save_json(sc.model_dump(), out_dir / "score.json")
    io.save_json(fb.model_dump(), out_dir / "feedback.json")
    with open(out_dir / "extraction_log.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in log)
    io.save_json({"sigmas": [[t, r, s] for (t, r), s in sorted(trace["sigmas"].items())],
                  "aligned": trace["aligned"], "contradictions": trace["contradictions"]}, out_dir / "trace.json")
    return {"sentences": sentences, "students": students, "entries": entries, "score": sc, "feedback": fb, "log": log,
            "trace": trace, "out_dir": out_dir}


def runs_dir():
    return io.ROOT / "outputs" / "runs"


def completed_runs():
    """Finished runs, newest first; skips stray files (e.g. macOS .DS_Store) and runs that stopped half-way."""
    if not runs_dir().exists():
        return []
    return sorted((p for p in runs_dir().iterdir() if p.is_dir() and (p / "run.json").exists()), reverse=True)


def run_split(question, mode, split, include_synthetic=False, use_llm_feedback=True, answer_ids=None, run_id=None,
              include_saf=False, annotated_only=False):
    answers = io.load_answers(include_synthetic, include_saf)
    if annotated_only:
        answers = answers[answers.answer_id.map(lambda a: io.annotation_path(a) is not None)]
    if question != "all":
        answers = answers[answers.question_id == question]
    if split != "all":
        answers = answers[answers.split == split]
    if answer_ids:
        answers = answers[answers.answer_id.isin(answer_ids)]
    if answers.empty:
        raise ValueError("no answers selected (real answers live in data/answers/answers.csv; use --synthetic for demo data)")
    run_id = run_id or f"{datetime.now():%Y%m%d-%H%M%S}_{mode}_{split}"
    run_dir = runs_dir() / run_id
    contexts, rows = {}, []
    for a in answers.itertuples():
        ctx = contexts.setdefault(a.question_id, Context.load(a.question_id))
        res = run_answer(ctx, a.answer_id, a.text, mode, run_dir / a.answer_id, use_llm_feedback)
        rows.append({"answer_id": a.answer_id, "question_id": a.question_id, "split": a.split,
                     "source": a.source, "synthetic": bool(a.synthetic), "score": res["score"].score,
                     "sparql_score": res["score"].sparql_score})
        print(f"{a.answer_id}: {res['score'].score:.1f}")
    pd.DataFrame(rows).to_csv(run_dir / "scores.csv", index=False)
    io.save_json({"run_id": run_id, "mode": mode, "split": split, "question": question,
                  "params": io.load_params(), "params_frozen": io.frozen_path().exists(),
                  "reasoner": io.load_config()["reasoner"], "include_synthetic": include_synthetic,
                  "include_saf": include_saf,
                  "created": datetime.now().isoformat(timespec="seconds")}, run_dir / "run.json")
    return run_dir
