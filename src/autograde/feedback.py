"""Feedback written only from the ledger; validated; deterministic template when the LLM fails or is absent."""
import json
import re
import unicodedata

from autograde import llm
from autograde.models import Feedback

KIND_STATUS = {"correct": "MATCHED", "partial": "PARTIAL", "missing": "MISSING", "contradiction": "CONTRADICTED"}
MAX_CLAIMS = 5
NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?(?![A-Za-z])")  # CO2, H2O, O2 are not numbers

SYSTEM = """You write short feedback in Indonesian for a student, using ONLY the grading ledger you are given.
- Every claim must cite the ledger entry ids it is based on, and its kind must match those entries' status
  (correct=MATCHED, partial=PARTIAL, missing=MISSING, contradiction=CONTRADICTED).
- At most 5 claims. Do not invent facts that are not in the ledger.
- The score is fixed and shown for context only. Never mention any other number."""


def display_score(score):
    return f"{score:.1f}"


def allowed_numbers(score):
    d = display_score(score)
    return {d, d.replace(".", ","), *([d[:-2]] if d.endswith(".0") else [])}


def triple_label(ref):
    return f"{ref.s[0]} {ref.p} {ref.o}"


# Added to SYSTEM only when Rule 4 found premise gaps, so cached prompts for other answers stay valid.
PREMISE_RULE = """
- kind "premise" is only for an entry listed with missing_premises: cite that entry and its missing premise
  entries, and explain that the conclusion is stated without the premise it rests on. This does not lower
  the score."""


def ledger_view(entries, refs, rubric, sentences, gaps=()):
    desc = {c["id"]: c["description"] for c in rubric["criteria"]}
    by_ref, text = {r.id: r for r in refs}, dict(sentences)
    rows = []
    for e in entries:
        row = {"entry_id": e.entry_id, "status": e.status, "criterion": desc[e.criterion],
               "reference_triple": triple_label(by_ref[e.reference_id]),
               "quoted_sentences": [text[s] for s in e.sentence_ids if s in text]}
        missing = [g.premise_entry_id for g in gaps if g.entry_id == e.entry_id]
        if missing:
            row["missing_premises"] = missing
        rows.append(row)
    return rows


def kinds(gaps=()):
    return [*KIND_STATUS, *(["premise"] if gaps else [])]


def schema(entries, gaps=()):
    claim = {"type": "object",
             "properties": {"text": {"type": "string"}, "kind": {"type": "string", "enum": kinds(gaps)},
                            "ledger_entry_ids": {"type": "array",
                                                 "items": {"type": "string", "enum": [e.entry_id for e in entries]}}},
             "required": ["text", "kind", "ledger_entry_ids"], "additionalProperties": False}
    return {"type": "object", "properties": {"claims": {"type": "array", "items": claim}, "summary": {"type": "string"}},
            "required": ["claims", "summary"], "additionalProperties": False}


def premise_errors(i, claim, gaps):
    """A premise claim cites at least one recorded gap (conclusion and premise) and nothing outside the gaps."""
    pairs = {(g.entry_id, g.premise_entry_id) for g in gaps}
    cited = set(claim.ledger_entry_ids)
    if not any(c in cited and p in cited for c, p in pairs):
        return [f"claim {i} is 'premise' but cites no recorded premise gap"]
    stray = sorted(cited - {x for pair in pairs for x in pair})
    return [f"claim {i} is 'premise' but {eid} is in no premise gap" for eid in stray]


def validate(fb, entries, score, gaps=()):
    status = {e.entry_id: e.status for e in entries}
    errors = []
    if len(fb.claims) > MAX_CLAIMS:
        errors.append(f"more than {MAX_CLAIMS} claims")
    for i, c in enumerate(fb.claims, 1):
        if not c.ledger_entry_ids:
            errors.append(f"claim {i} cites no ledger entry")
        for eid in c.ledger_entry_ids:
            if eid not in status:
                errors.append(f"claim {i} cites unknown entry {eid}")
            elif c.kind != "premise" and status[eid] != KIND_STATUS[c.kind]:
                errors.append(f"claim {i} is '{c.kind}' but {eid} is {status[eid]}")
        if c.kind == "premise" and all(eid in status for eid in c.ledger_entry_ids):
            errors += premise_errors(i, c, gaps)
    allowed = allowed_numbers(score)
    for text in [fb.summary, *(c.text for c in fb.claims)]:
        bad = [n for n in NUMBER.findall(unicodedata.normalize("NFKC", text)) if n not in allowed]
        if bad:
            errors.append(f"numbers other than the score: {bad}")
    return errors


TEMPLATES = [  # (kind, sentence) in display order
    ("contradiction", "Pernyataanmu bertentangan dengan kunci jawaban: {}."),
    ("missing", "Belum disebutkan: {}."),
    ("partial", "Sudah mendekati, tetapi istilahnya kurang tepat: {}."),
    ("correct", "Sudah benar: {}."),
]


PREMISE_TEMPLATE = ("Kesimpulan sudah disebut, tetapi premis yang mendasarinya belum ditemukan: {}. "
                    "Ini tidak mengurangi skor; lengkapi alasannya.")


def template(answer_id, entries, refs, score, gaps=()):
    by_ref = {r.id: r for r in refs}
    claims = []
    for kind, sentence in TEMPLATES:
        hits = [e for e in entries if e.status == KIND_STATUS[kind]]
        if hits:
            claims.append({"text": sentence.format("; ".join(triple_label(by_ref[e.reference_id]) for e in hits)),
                           "kind": kind, "ledger_entry_ids": [e.entry_id for e in hits]})
    if gaps:  # one claim for every gap, after the status claims (at most 5 claims in total)
        conclusions = list(dict.fromkeys(g.entry_id for g in gaps))
        parts = ["{} ← {}".format(triple_label(by_ref[next(g.reference_id for g in gaps if g.entry_id == c)]),
                                  ", ".join(triple_label(by_ref[g.premise_id]) for g in gaps if g.entry_id == c))
                 for c in conclusions]
        claims.append({"text": PREMISE_TEMPLATE.format("; ".join(parts)), "kind": "premise",
                       "ledger_entry_ids": list(dict.fromkeys(x for g in gaps for x in (g.entry_id, g.premise_entry_id)))})
    return Feedback(answer_id=answer_id, claims=claims, source="template",
                    summary=f"Skor: {display_score(score)}. Perhatikan bagian yang belum disebutkan atau bertentangan.")


def generate(answer_id, entries, refs, rubric, sentences, score, *, backend=None, use_llm=True, gaps=()):
    """LLM feedback, one retry with the validator's errors, then the template. `gaps`: Rule 4 premise gaps."""
    if use_llm:
        user = json.dumps({"score_display": display_score(score),
                           "ledger": ledger_view(entries, refs, rubric, sentences, gaps)}, ensure_ascii=False, indent=1)
        for _ in range(2):
            try:
                data = llm.complete_json(SYSTEM + (PREMISE_RULE if gaps else ""), user, schema(entries, gaps),
                                         backend=backend)
            except llm.LLMError:  # no key, refusal, API error: use the template
                break
            fb = Feedback(answer_id=answer_id, source="llm", **data)
            errors = validate(fb, entries, score, gaps)
            if not errors:
                return fb
            user += "\n\nYour previous feedback was rejected: " + "; ".join(errors)
    return template(answer_id, entries, refs, score, gaps)
