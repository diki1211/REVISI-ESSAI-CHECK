"""B1 keyword matching (style of [11]) and B2 LLM-only scoring (style of [6]); comparison only."""
import re

from autograde import io, llm
from autograde.normalize import norm_text


def surfaces(concept, concepts):
    return {norm_text(s) for s in [concept, *((concepts.get(concept) or {}).get("aliases") or [])]}


def b1_keyword(text, refs, concepts):
    """Credit when any accepted subject and the object appear anywhere in the answer; predicate ignored; Eq. 6, λ=0."""
    padded = f" {norm_text(text)} "
    found = lambda c: any(f" {s} " in padded for s in surfaces(c, concepts))
    hit = sum(r.weight for r in refs if any(found(s) for s in r.s) and found(r.o))
    return 100 * hit / sum(r.weight for r in refs)


B2_SYSTEM = """You are grading a short answer written in Indonesian against a lecturer's reference answer and
weighted rubric. Return a score from 0 to 100."""
B2_SCHEMA = {"type": "object", "properties": {"score": {"type": "number"}}, "required": ["score"],
             "additionalProperties": False}


def b2_llm(qid, text, refs, rubric, backend=None):
    """LLM-only score (the Rule 1 exception: reported as a baseline, never used by the system)."""
    from autograde.gold import criterion_weights
    d = io.question_dir(qid)
    weights = criterion_weights(refs)
    crit = "\n".join(f"- {c['description']} (bobot {weights[c['id']]:g})" for c in rubric["criteria"])
    read = lambda name: re.sub(r"<!--.*?-->", "", (d / name).read_text(encoding="utf-8"), flags=re.S).strip()
    user = (f"Soal:\n{read('question.md')}\n\nJawaban acuan:\n{read('reference_answer.md')}\n\n"
            f"Rubrik:\n{crit}\n\nJawaban mahasiswa:\n{text}")
    score = float(llm.complete_json(B2_SYSTEM, user, B2_SCHEMA, backend=backend)["score"])
    return min(100.0, max(0.0, score))
