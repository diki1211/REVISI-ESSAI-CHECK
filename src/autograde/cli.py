"""python -m autograde <command> (plan Section 8)."""
import argparse
import sys

from autograde import io


def cmd_gold(args):
    from autograde import gold
    path, refs = gold.build(args.question)
    print(f"{len(refs)} reference triples -> {path}\nreview table -> docs/gold_{args.question}_review.md")


def cmd_extract(args):
    from autograde import pipeline, segment
    answers = io.load_answers(args.synthetic, args.saf)
    answers = answers[answers.question_id == args.question]
    if args.answers:
        answers = answers[answers.answer_id.isin(args.answers.split(","))]
    ctx = pipeline.Context.load(args.question)
    out = io.ROOT / "outputs" / "extract" / args.question / args.mode
    for a in answers.itertuples():
        students, log = pipeline.extract_triples(ctx, a.answer_id, segment.split(a.answer_id, a.text), args.mode)
        io.save_json([t.model_dump() for t in students], out / f"{a.answer_id}.json")
        print(f"{a.answer_id}: {len(students)} triples, {len(log)} dropped")


def cmd_run(args):
    from autograde import pipeline
    run_dir = pipeline.run_split(args.question, args.mode, args.split, args.synthetic,
                                 use_llm_feedback=not args.template_feedback, include_saf=args.saf,
                                 annotated_only=args.annotated_only)
    print(f"run -> {run_dir}")


def cmd_calibrate(args):
    from autograde import calibrate
    print(f"frozen parameters -> {calibrate.calibrate(include_synthetic=args.synthetic, mode=args.mode)}")


def cmd_evaluate(args):
    from autograde import evaluate
    print(f"report -> {evaluate.evaluate(args.run, gold_run_id=args.gold_run)}")


def cmd_recompute(args):
    from autograde import ledger, pipeline
    d = pipeline.runs_dir() / args.run / args.answer
    run = io.load_json(pipeline.runs_dir() / args.run / "run.json")
    qid = _question_of(args.run, args.answer)
    sparql = ledger.recompute_sparql(d / "ledger.ttl", io.question_dir(qid) / "gold.ttl", run["params"]["lambda"])
    stored = io.load_json(d / "score.json")["score"]
    ok = abs(sparql - stored) < 1e-9
    print(f"{args.answer}: SPARQL {sparql:.4f} | stored {stored:.4f} | {'OK' if ok else 'MISMATCH'}")
    sys.exit(0 if ok else 1)


def _question_of(run_id, answer_id):
    import pandas as pd
    from autograde import pipeline
    scores = pd.read_csv(pipeline.runs_dir() / run_id / "scores.csv", dtype=str)
    return scores.set_index("answer_id").loc[answer_id, "question_id"]


def cmd_override(args):
    from autograde import ledger, pipeline
    from autograde.models import LedgerEntry
    from autograde.score import score
    run_dir = pipeline.runs_dir() / args.run
    params = io.load_json(run_dir / "run.json")["params"]
    overrides = io.load_yaml(io.ROOT / "data" / "human" / "overrides.yaml") or []
    for answer_id in sorted({o["answer_id"] for o in overrides}):
        d = run_dir / answer_id
        if not d.exists():
            print(f"{answer_id}: not in run {args.run}, skipped")
            continue
        qid = _question_of(args.run, answer_id)
        entries = [LedgerEntry(**e) for e in io.load_json(d / "ledger.json")]
        fixed = ledger.apply_overrides(entries, [o for o in overrides if o["answer_id"] == answer_id], params)
        ledger.write(d, qid, fixed, suffix="_corrected")
        sc = score(answer_id, fixed, params)
        sc.sparql_score = ledger.recompute_sparql(d / "ledger_corrected.ttl", io.question_dir(qid) / "gold.ttl",
                                                  params["lambda"])
        if abs(sc.score - sc.sparql_score) >= 1e-9:
            raise pipeline.ParityError(f"{answer_id}: corrected score parity failed")
        io.save_json(sc.model_dump(), d / "score_corrected.json")
        print(f"{answer_id}: {io.load_json(d / 'score.json')['score']:.1f} -> {sc.score:.1f} (corrected)")


def cmd_audit_template(args):
    from autograde import evaluate
    print(f"audit template -> {evaluate.audit_template(args.run)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m autograde")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("gold", help="validate gold.yaml and write gold.ttl + review table")
    s.add_argument("--question", required=True)
    s.set_defaults(func=cmd_gold)
    s = sub.add_parser("extract", help="extract student triples only")
    s.add_argument("--question", required=True)
    s.add_argument("--mode", choices=["llm", "gold"], required=True)
    s.add_argument("--answers", help="comma-separated answer ids")
    s.add_argument("--synthetic", action="store_true", help="include data/synthetic answers")
    s.add_argument("--saf", action="store_true", help="include the SAF subset (data/external/saf)")
    s.set_defaults(func=cmd_extract)
    s = sub.add_parser("run", help="grade answers and write a run")
    s.add_argument("--question", required=True, help="question id or 'all'")
    s.add_argument("--mode", choices=["llm", "gold"], required=True)
    s.add_argument("--split", choices=["pilot", "test", "all"], required=True)
    s.add_argument("--synthetic", action="store_true", help="include data/synthetic answers")
    s.add_argument("--saf", action="store_true", help="include the SAF subset (data/external/saf)")
    s.add_argument("--template-feedback", action="store_true", help="skip the LLM for feedback")
    s.add_argument("--annotated-only", action="store_true", help="only answers with triple annotations (offline)")
    s.set_defaults(func=cmd_run)
    s = sub.add_parser("calibrate", help="grid search on the pooled pilot split -> config/frozen.yaml")
    s.add_argument("--mode", choices=["llm", "gold"], default="llm")
    s.add_argument("--synthetic", action="store_true", help="demo only: writes outputs/synthetic/frozen.yaml")
    s.set_defaults(func=cmd_calibrate)
    s = sub.add_parser("evaluate", help="metrics for a test-split run")
    s.add_argument("--run", required=True)
    s.add_argument("--gold-run", help="gold-mode run of the same answers, for the ablation row")
    s.set_defaults(func=cmd_evaluate)
    s = sub.add_parser("recompute", help="SPARQL audit of one stored score")
    s.add_argument("--run", required=True)
    s.add_argument("--answer", required=True)
    s.set_defaults(func=cmd_recompute)
    s = sub.add_parser("override", help="apply data/human/overrides.yaml to a run")
    s.add_argument("--run", required=True)
    s.set_defaults(func=cmd_override)
    s = sub.add_parser("audit-template", help="blank evidence_audit.csv for the lecturer")
    s.add_argument("--run", required=True)
    s.set_defaults(func=cmd_audit_template)
    args = p.parse_args(argv)
    args.func(args)
