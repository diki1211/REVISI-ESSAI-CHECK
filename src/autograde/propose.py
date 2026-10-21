"""Draft gold triples from the lecturer's reference answer, for the lecturer to review (Tahap 1).

Two methods:
- `rule`: deterministic and offline. Finds predicate surface forms from predicates.yaml in each sentence,
  takes the words before as the subject and the words after (split on coordination) as objects, and maps
  each span to a concept through the gold.yaml alias table when one exists.
- `llm`: Claude drafts triples with a criterion and an importance level, constrained to the controlled
  predicates and the rubric criteria; every subject and object must be grounded in the cited sentence.

The draft goes to data/questions/<qid>/gold_proposed.yaml and docs/gold_<qid>_proposed_review.md. It is never
written into gold.yaml and is never read by grading: the lecturer copies accepted triples by hand (Agent Rule 4
and the validation step of plan Phase 2). When a gold.yaml already exists, the draft is compared with it, which
measures how well the reference answer can be turned into triples automatically.
"""
import re
import unicodedata
from datetime import date

from autograde import extract, io, llm, segment
from autograde.match import Relations
from autograde.normalize import STOPWORDS, concept_label, content_tokens, norm_text

COORDINATION = {"dan", "serta", "atau", "and", "or", ","}
CLAUSE_MARKERS = {"lalu", "kemudian", "sehingga", "yang", "whereby", "where", "which", "then", "so", "while",
                  "sedangkan", ";", ":"}
NEGATION = {"tidak", "bukan", "tanpa", "not", "never", "no"}
IMPORTANCE_WEIGHT = {"essential": 2.0, "supporting": 1.0, "optional": 0.5}  # a suggestion; the lecturer decides
METHODS = ("rule", "llm")


class ProposalError(ValueError):
    pass


# ---------- inputs ----------

def read_md(path):
    return re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S).strip()


def inputs(qid):
    """(reference sentences, rubric, gold concepts or {}, language) for a question folder."""
    d = io.question_dir(qid)
    if not (d / "reference_answer.md").exists() or not (d / "rubric.yaml").exists():
        raise ProposalError(f"{d} needs reference_answer.md and rubric.yaml")
    rubric = io.load_yaml(d / "rubric.yaml")
    gold_raw = io.load_yaml(d / "gold.yaml") if (d / "gold.yaml").exists() else {}
    sentences = segment.split(f"{qid}_REF", read_md(d / "reference_answer.md"))
    return sentences, rubric, (gold_raw or {}).get("concepts") or {}, rubric.get("language", "id")


def concept_table(concepts):
    """Normalized surface -> concept id, from ids (as words) and aliases."""
    table = {}
    for cid, spec in concepts.items():
        for surface in [concept_label(cid), *((spec or {}).get("aliases") or [])]:
            if norm_text(surface):
                table.setdefault(norm_text(surface), cid)
    return table


def predicate_table(predicates, language):
    """Token tuple -> predicate id. English one-word forms also match -ed/-ing ("replaced", "assigning")."""
    table = {}
    for p in extract.for_language(predicates, language)["predicates"]:
        if p["id"] == "other":
            continue
        for surface in [p["id"].replace("_", " "), *p.get("aliases", [])]:
            words = tuple(norm_text(surface).split())
            if not words:
                continue
            table.setdefault(words, p["id"])
            if language == "en" and len(words) == 1 and len(words[0]) > 3 and words[0].endswith("s"):
                base = words[0][:-1]
                stem = base[:-1] if base.endswith("e") else base
                for form in (base, stem + "ed", stem + "ing"):
                    table.setdefault((form,), p["id"])
    return table


def tokens(text):
    """Lower-case word tokens, keeping commas, semicolons and colons as separate tokens."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.findall(r"[^\W_]+(?:[-'][^\W_]+)*|[,;:]", text)


# ---------- span -> concept ----------

def camel(words):
    parts = [x for w in words for x in re.split(r"[-']", w) if x]
    return "".join(x[:1].upper() + x[1:] for x in parts)


def resolve(span, table):
    """(concept id, is_new) for a token span: the earliest, then longest, known surface; else a new id."""
    words = [w for w in span if w not in {",", ";", ":"}]
    for start in range(len(words)):
        for end in range(len(words), start, -1):
            hit = table.get(" ".join(words[start:end]))
            if hit:
                return hit, False
    content = [w for w in words if w not in STOPWORDS]
    if not content:
        return None, False
    return camel(content[:3]), True


def strip_edges(span):
    while span and (span[0] in STOPWORDS | COORDINATION | CLAUSE_MARKERS):
        span = span[1:]
    while span and (span[-1] in STOPWORDS | COORDINATION | CLAUSE_MARKERS):
        span = span[:-1]
    return span


def split_items(span):
    items, cur = [], []
    for w in span:
        if w in COORDINATION:
            items.append(cur)
            cur = []
        else:
            cur.append(w)
    items.append(cur)
    return [strip_edges(i) for i in items if strip_edges(i)]


# ---------- rule method ----------

def find_predicates(words, table):
    """[(start, end, predicate id)], longest match first, left to right."""
    longest = max((len(k) for k in table), default=0)
    out, i = [], 0
    while i < len(words):
        for n in range(min(longest, len(words) - i), 0, -1):
            pid = table.get(tuple(words[i:i + n]))
            if pid:
                out.append((i, i + n, pid))
                i += n
                break
        else:
            i += 1
    return out


def propose_rule(sentences, concepts, predicates, language):
    """Deterministic draft. Returns (proposals, log of skipped spans)."""
    ctable, ptable = concept_table(concepts), predicate_table(predicates, language)
    proposals, log, subject = [], [], None
    for sid, text in sentences:
        words = tokens(text)
        hits = find_predicates(words, ptable)
        # an auxiliary right before another predicate ("has largely replaced"): no object words of its own
        hits = [h for k, h in enumerate(hits)
                if k + 1 >= len(hits) or len(content_tokens(" ".join(words[h[1]:hits[k + 1][0]]))) > 1
                or resolve(words[h[1]:hits[k + 1][0]], ctable)[0] in concepts]
        for k, (start, end, pid) in enumerate(hits):
            before = strip_edges(words[(hits[k - 1][1] if k else 0):start])
            if k == 0 and before:
                subject = (resolve(before, ctable), " ".join(before))
            stop = hits[k + 1][0] if k + 1 < len(hits) else len(words)
            obj = words[end:stop]
            marker = next((i for i, w in enumerate(obj) if w in CLAUSE_MARKERS), None)
            if marker is not None:
                clause = strip_edges(obj[marker + 1:])
                obj = obj[:marker]
                if clause and k + 1 < len(hits):  # "…, whereby a DHCP server assigns": next subject
                    subject = (resolve(clause, ctable), " ".join(clause))
            if start > 0 and words[start - 1] in NEGATION:
                log.append({"sentence_id": sid, "reason": "negated", "predicate": pid})
                continue
            if subject is None or subject[0][0] is None:
                log.append({"sentence_id": sid, "reason": "no_subject", "predicate": pid})
                continue
            for item in split_items(obj):
                (o_id, o_new), ((s_id, s_new), s_text) = resolve(item, ctable), subject
                if o_id is None or o_id == s_id:
                    continue
                proposals.append({"s": s_id, "p": pid, "o": o_id, "s_text": s_text, "o_text": " ".join(item),
                                  "s_new": s_new, "o_new": o_new, "sentence_ids": [sid], "criterion": None,
                                  "importance": None})
    return dedupe(proposals), log


# ---------- LLM method ----------

SYSTEM = """You draft reference (gold) triples from a lecturer's model answer written in {language}.
The lecturer reviews every triple before it is used; you only propose.

Rules:
- One triple per fact the model answer states. Split coordinated statements into one triple each.
- subject and object copy words from the cited sentences; prefer the short noun phrase that names the concept.
- predicate must be one of the listed predicate ids or aliases; use "other" when none fits.
- Skip negated statements and examples given only as illustrations.
- criterion is the rubric criterion the fact gives evidence for.
- importance: "essential" for facts needed for full marks, "supporting" for facts that strengthen the answer,
  "optional" for examples or extra detail."""


def llm_schema(labels, predicates, criteria):
    triple = {"type": "object",
              "properties": {"sentence_ids": {"type": "array", "items": {"type": "string", "enum": labels}},
                             "subject": {"type": "string"},
                             "predicate": {"type": "string", "enum": extract.predicate_values(predicates)},
                             "object": {"type": "string"},
                             "criterion": {"type": "string", "enum": criteria},
                             "importance": {"type": "string", "enum": list(IMPORTANCE_WEIGHT)}},
              "required": ["sentence_ids", "subject", "predicate", "object", "criterion", "importance"],
              "additionalProperties": False}
    return {"type": "object", "properties": {"triples": {"type": "array", "items": triple}},
            "required": ["triples"], "additionalProperties": False}


def llm_prompt(sentences, predicates, rubric):
    preds = "\n".join(f"- {p['id']}: {p['description']}" + (f" (alias: {', '.join(p['aliases'])})" if p.get("aliases") else "")
                      for p in predicates["predicates"])
    crit = "\n".join(f"- {c['id']}: {c['description']}" for c in rubric["criteria"])
    numbered = "\n".join(f"S{i}: {text}" for i, (_, text) in enumerate(sentences, 1))
    return f"Predicates:\n{preds}\n\nRubric criteria:\n{crit}\n\nModel answer:\n{numbered}"


def propose_llm(sentences, concepts, predicates, language, rubric, *, backend=None, threshold=None):
    """Claude's draft, checked like student extraction (predicate vocabulary, grounding). Returns (proposals, log)."""
    if not sentences:
        return [], []
    predicates = extract.for_language(predicates, language)
    threshold = threshold if threshold is not None else io.load_config()["grounding_threshold"]
    labels = [f"S{i}" for i in range(1, len(sentences) + 1)]
    by_label = dict(zip(labels, sentences))
    data = llm.complete_json(SYSTEM.format(language=extract.LANGUAGES[language]),
                             llm_prompt(sentences, predicates, rubric),
                             llm_schema(labels, predicates, [c["id"] for c in rubric["criteria"]]), backend=backend)
    aliases, ctable = extract.alias_map(predicates), concept_table(concepts)
    proposals, log = [], []
    for raw in data.get("triples", []):
        drop = lambda reason: log.append({"reason": reason, "triple": raw})
        if not raw.get("sentence_ids") or any(l not in by_label for l in raw["sentence_ids"]):
            drop("bad_sentence_id")
            continue
        pid = aliases.get(str(raw.get("predicate", "")).lower())
        if pid in (None, "other"):
            drop("unknown_predicate" if pid is None else "other_predicate")
            continue
        cited = " ".join(by_label[l][1] for l in raw["sentence_ids"])
        if not extract.grounded(raw["subject"], cited, threshold) or not extract.grounded(raw["object"], cited, threshold):
            drop("not_grounded")
            continue
        (s_id, s_new), (o_id, o_new) = resolve(tokens(raw["subject"]), ctable), resolve(tokens(raw["object"]), ctable)
        if s_id is None or o_id is None or s_id == o_id:
            drop("no_concept")
            continue
        proposals.append({"s": s_id, "p": pid, "o": o_id, "s_text": raw["subject"], "o_text": raw["object"],
                          "s_new": s_new, "o_new": o_new, "sentence_ids": [by_label[l][0] for l in raw["sentence_ids"]],
                          "criterion": raw["criterion"], "importance": raw["importance"]})
    return dedupe(proposals), log


# ---------- comparison, output ----------

def dedupe(proposals):
    seen, out = set(), []
    for p in proposals:
        if (p["s"], p["p"], p["o"]) not in seen:
            seen.add((p["s"], p["p"], p["o"]))
            out.append(p)
    return out


def gold_match(p, refs, rel):
    """Id of the gold triple this proposal states (equivalent predicate, an accepted subject, same object)."""
    return next((r.id for r in refs if p["o"] == r.o and p["s"] in r.s and rel.is_eq(r.p, p["p"])), None)


def compare(proposals, refs, rel):
    """Precision of the draft against gold.yaml and recall of gold.yaml, each also weighted by gold weights."""
    hits = [gold_match(p, refs, rel) for p in proposals]
    covered = {h for h in hits if h}
    total_w = sum(r.weight for r in refs)
    return {"proposed": len(proposals), "in_gold": sum(h is not None for h in hits), "gold_total": len(refs),
            "gold_covered": len(covered),
            "precision": round(sum(h is not None for h in hits) / len(proposals), 4) if proposals else None,
            "recall": round(len(covered) / len(refs), 4) if refs else None,
            "weighted_recall": round(sum(r.weight for r in refs if r.id in covered) / total_w, 4) if refs else None}


def propose(qid, method="rule", *, backend=None):
    """Draft for one question: {question_id, method, triples, new_concepts, comparison, log}. Writes nothing."""
    if method not in METHODS:
        raise ProposalError(f"unknown method {method!r} (use {' or '.join(METHODS)})")
    sentences, rubric, concepts, language = inputs(qid)
    predicates = io.load_predicates()
    if method == "rule":
        drafts, log = propose_rule(sentences, concepts, predicates, language)
    else:
        drafts, log = propose_llm(sentences, concepts, predicates, language, rubric, backend=backend)
    refs = []
    if (io.question_dir(qid) / "gold.yaml").exists():
        from autograde import gold
        refs = gold.load(qid)[2]
    rel = Relations.from_ontology()
    text = dict(sentences)
    triples = []
    for i, p in enumerate(drafts, 1):
        triples.append({"id": f"P{i}", "s": [p["s"]], "p": p["p"], "o": p["o"], "criterion": p["criterion"],
                        "weight": IMPORTANCE_WEIGHT.get(p["importance"], 1.0), "importance": p["importance"],
                        "in_gold": gold_match(p, refs, rel), "s_text": p["s_text"], "o_text": p["o_text"],
                        "source": " ".join(text[s] for s in p["sentence_ids"]), "accept": None})
    new_concepts = {}
    for p in drafts:
        for side in ("s", "o"):
            if p[f"{side}_new"]:
                new_concepts.setdefault(p[side], {"aliases": []})
                if p[f"{side}_text"] not in new_concepts[p[side]]["aliases"]:
                    new_concepts[p[side]]["aliases"].append(p[f"{side}_text"])
    cfg = io.load_config()["llm"]
    return {"question_id": qid, "status": "draft",
            "note": "Draft for lecturer review. Never read by grading; copy accepted triples into gold.yaml by hand.",
            "proposed_by": "rule-based draft" if method == "rule" else f"{cfg['model']} (AI draft)",
            "proposed_on": date.today().isoformat(), "method": method, "language": language,
            "comparison": compare(drafts, refs, rel) if refs else None,
            "new_concepts": new_concepts, "triples": triples, "log": log}


def review_md(draft, rubric):
    desc = {c["id"]: c["description"] for c in rubric["criteria"]}
    lines = [f"# Draft gold triples for {draft['question_id']} — lecturer review", "",
             f"> Draft by {draft['proposed_by']} ({draft['method']}), {draft['proposed_on']}. "
             "Not used for grading until copied into gold.yaml.", ""]
    c = draft["comparison"]
    if c:
        lines += [f"Compared with the current gold.yaml: {c['in_gold']} of {c['proposed']} drafted triples are already in "
                  f"the key (precision {c['precision']}); {c['gold_covered']} of {c['gold_total']} key triples were "
                  f"drafted (recall {c['recall']}, weighted {c['weighted_recall']}).", ""]
    lines += ["| ID | Subjek | Predikat | Objek | Kriteria | Bobot (saran) | Sudah di kunci | Kalimat sumber | Terima? |",
              "|---|---|---|---|---|---|---|---|---|"]
    for t in draft["triples"]:
        crit = f"{t['criterion']} ({desc.get(t['criterion'], '?')})" if t["criterion"] else "—"
        lines.append(f"| {t['id']} | {' / '.join(t['s'])} | {t['p']} | {t['o']} | {crit} | {t['weight']:g} | "
                     f"{t['in_gold'] or '—'} | {t['source']} | ☐ |")
    if draft["new_concepts"]:
        lines += ["", "## Konsep baru (belum ada di gold.yaml)", ""]
        lines += [f"- **{cid}**: {', '.join(v['aliases'])}" for cid, v in draft["new_concepts"].items()]
    return "\n".join(lines) + "\n"


def write(draft):
    """gold_proposed.yaml next to gold.yaml, plus a review table in docs/. Never touches gold.yaml."""
    d = io.question_dir(draft["question_id"])
    out = d / "gold_proposed.yaml"
    io.save_yaml(draft, out)
    rubric = io.load_yaml(d / "rubric.yaml")
    md = io.ROOT / "docs" / f"gold_{draft['question_id']}_proposed_review.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(review_md(draft, rubric), encoding="utf-8")
    return out, md


def as_gold_yaml(draft, accepted_ids):
    """The accepted triples in gold.yaml's shape (ids R<n>), for the lecturer to paste after review."""
    picked = [t for t in draft["triples"] if t["id"] in accepted_ids]
    return {"concepts": {c: v for c, v in draft["new_concepts"].items()
                         if any(c in t["s"] or c == t["o"] for t in picked)},
            "triples": [{"id": f"R{i}", "s": t["s"], "p": t["p"], "o": t["o"], "criterion": t["criterion"],
                         "weight": t["weight"]} for i, t in enumerate(picked, 1)]}
