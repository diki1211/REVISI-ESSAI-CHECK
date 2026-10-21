"""Rule 4 (argument logic): a conclusion credited without the premises the lecturer says it rests on.

gold.yaml may give a reference triple `requires: [R2, R3]`. After the ledger is built, a credited conclusion
(MATCHED or PARTIAL) whose required premise is not credited (MISSING or CONTRADICTED) is a premise gap.

A gap is a diagnostic for feedback and lecturer review. It never changes credit, status or the score (Eq. 6),
and a MISSING premise still only means "not found in the answer" (open-world assumption).
This module is the plain-Python reference; reason.py runs the same rule as SWRL (Pellet) or SPARQL.
"""
from autograde.models import PremiseGap

CREDITED = ("MATCHED", "PARTIAL")


def links(refs):
    """(conclusion id, premise id) pairs in gold order."""
    return [(r.id, p) for r in refs for p in r.requires]


def gap_pairs(refs, entries):
    by_ref = {e.reference_id: e for e in entries}
    return {(c, p) for c, p in links(refs)
            if by_ref[c].status in CREDITED and by_ref[p].status not in CREDITED}


def to_gaps(pairs, refs, entries):
    """PremiseGap records for (conclusion id, premise id) pairs, in gold order."""
    by_ref = {e.reference_id: e for e in entries}
    return [PremiseGap(entry_id=by_ref[c].entry_id, reference_id=c, premise_entry_id=by_ref[p].entry_id,
                       premise_id=p, premise_status=by_ref[p].status)
            for c, p in links(refs) if (c, p) in pairs]


def gaps(refs, entries):
    return to_gaps(gap_pairs(refs, entries), refs, entries)
