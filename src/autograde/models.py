"""Typed schemas for every intermediate file (plan Section 5.4)."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Status = Literal["MATCHED", "PARTIAL", "MISSING", "CONTRADICTED"]
# Ledger status -> ag:Status individual used in ledger.ttl (deck slide 3.2)
STATUS_IRI_NAME = {"MATCHED": "Cocok", "PARTIAL": "Parsial", "MISSING": "Hilang", "CONTRADICTED": "Kontradiksi"}


class ReferenceTriple(BaseModel):
    id: str
    s: list[str]  # accepted subject concepts
    p: str
    o: str
    criterion: str
    weight: float = Field(gt=0)

    @field_validator("s", mode="before")
    @classmethod
    def _coerce_subjects(cls, v):
        return [v] if isinstance(v, str) else v


class StudentTriple(BaseModel):
    id: str  # e.g. Q1_A07_t3
    answer_id: str
    s_text: str
    p: str  # predicate id after alias normalization
    o_text: str
    negated: bool = False
    sentence_ids: list[str]  # e.g. ["Q1_A07_s2"]
    s_concept: str | None = None
    o_concept: str | None = None


class LedgerEntry(BaseModel):
    entry_id: str  # L_<answer>_<ref>
    answer_id: str
    reference_id: str
    criterion: str
    weight: float
    status: Status
    credit: float  # m_i
    contradiction: bool  # kappa_i
    matched_by: str | None
    contradicted_by: str | None
    sigma: float | None
    sentence_ids: list[str]
    needs_review: bool
    override: dict | None = None


class ScoreResult(BaseModel):
    answer_id: str
    score: float
    sum_weighted_credit: float
    sum_penalty: float
    sum_weights: float
    params: dict
    sparql_score: float | None = None


class FeedbackClaim(BaseModel):
    text: str
    kind: Literal["correct", "missing", "contradiction", "partial"]
    ledger_entry_ids: list[str]


class Feedback(BaseModel):
    answer_id: str
    claims: list[FeedbackClaim]
    summary: str
    source: Literal["llm", "template"] = "template"
