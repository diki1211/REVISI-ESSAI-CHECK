# Decisions

Agent Rule 2: formula changes need a human decision recorded here. Newest last.

## 2026-10-21 — Formulas (refinements of deck slides 3.4)

1. **SWRL/embedding split.** SWRL cannot compute embeddings, so Python asserts `ag:alignedSubject` and `ag:alignedObject` only for pairs with σ ≥ τ_h. Pellet then infers `ag:contradicts` with Rules 1–3. Mention this in the article.
2. **Negation.** Eq. 3 gives no credit to a negated triple. Eq. 5 marks a contradiction for an incompatible predicate that is *not* negated, or for an equivalent predicate that *is* negated. "Fotosintesis tidak menghasilkan CO2" is a correct statement and is not a contradiction. Python asserts `ag:negated` on every student triple, because under the open-world assumption a missing value never satisfies `negated(?t, false)`.
3. **sim.** Two *known* concepts with different ids score 0.0, with no embedding fallback; this stops Oksigen vs CO2 from earning credit. Embeddings are used only when at least one side is not in the alias table.
4. **Accepted subjects.** A gold triple lists the subjects it accepts (`s: [Fotosintesis, Tumbuhan]`), and σ uses the best one. The lecturer decides the list per triple.
5. **Equivalence lives in the ontology only.** `predicates.yaml` aliases only normalize surface wording. `menyerap` is its own `ag:Relation` with `menyerap equivalentPredicate menggunakan`, as on deck slide 3.2.

## 2026-10-21 — Parameters

- Initial values: τ_h = 0.80, τ_l = 0.60, δ = 0.5, λ = 0.0. λ = 0.5 is reported as a variant row.
- **δ and λ are fixed, not tuned.** Only τ_h and τ_l are searched (12 grid points with τ_l < τ_h). Reason: with a pilot of a few answers per question, tuning four parameters would overfit.
- Calibration is **global**: one search over the pooled pilot answers of all questions, in LLM mode, minimizing MAE against lecturer totals. `frozen.yaml` is written once and never overwritten.
- Calibration uses the SPARQL reasoner rather than Pellet, for speed (12 grid points × answers). The two are parity-tested on 10 crafted cases (`tests/test_reason.py`).

## 2026-10-21 — Implementation

- **LLM:** Claude Opus 5.5 (`claude-opus-5-5`) through the Anthropic SDK with JSON-schema structured output, at effort `medium`. **This model does not accept a temperature parameter**, so plan Rule 7's "temperature 0" cannot be applied. Determinism comes from the response cache, keyed by (provider, model, effort, schema, system prompt, user prompt). Anthropic's server-side refusal fallback (`fallbacks: "default"`) is enabled.
- **Java:** Owlready2 0.51's bundled Pellet needs Java 25 (class-file version 69). A Temurin 25 JRE is installed in `~/.local/share/jdk/`, and `io.java_exe()` finds it (or use `JAVA_EXE` / `JAVA_HOME`). Homebrew's `openjdk` install was blocked by a symlink another tool owns.
- **Starter ontology:** `ontology/build_ontology.py` generates `autograde.owl` (RDF/XML) from plan Section 6. A human checks and refines it in Protégé. Once it has been edited in Protégé, do not re-run the script, because it overwrites the file.
- **Ledger RDF:** statuses are `ag:Status` individuals (`ag:Cocok`, `ag:Parsial`, `ag:Hilang`, `ag:Kontradiksi`); code and JSON use the English enum. IRIs carry the question id (`ag:Q1_R5`, `ag:L_Q1_A07_R5`).
- **Lecturer corrections** (deck slide 1.4): `data/human/overrides.yaml` → `python -m autograde override`. This writes `ledger_corrected.*` and `score_corrected.json`; the original ledger is never changed. Corrected scores are never used in `evaluate`.
- **Synthetic data** lives in `data/synthetic/` (deck answers A07/A08 plus five invented answers, a single invented rater). Reports that include it are stamped "SYNTHETIC DATA — not real results".

## 2026-10-21 — SAF subset and demo app

- **SAF subset** (Filighera et al. 2022, English, CC-BY-4.0), imported by `scripts/import_saf.py` into `data/external/saf/`: 5 questions, 150 answers (SAF validation → pilot, SAF test_unseen_answers → test; SAF train not imported). It is loaded only with `--saf`.
  - The 5 questions are DHCP, piggybacking, async/sync transmission, data-link service classes, and CSMA/CD diameter. They were chosen for spread of scores and relation-like reference answers.
  - **The gold triples, rubrics and the 15 triple annotations for SAF were drafted by Claude (AI), not by a lecturer or a human annotator.** Every file says so. They are for the demo only and must not be used for the gold-mode ablation.
  - SAF scores are holistic points (max 1 for these questions), stored as `criterion = _total`. So SAF has no per-criterion errors.
- **English predicates** (`lang: en` in `predicates.yaml`) with ontology relations `utilizes ≡ uses`, `enables ≡ allows`, `provides ≡ assigns`, and `has ⊥ lacks`, `allows ⊥ prevents`, `decreases ⊥ increases`. Extraction prompts, examples and the predicate enum follow each question's `rubric.yaml` `language`.
- **Either/or reference answers can't be expressed.** SAF piggybacking allows "duplex connection OR acknowledgement field", so its gold has only the duplex triple.
- **Embedding labels:** known concept ids are embedded as words (`LowTransmissionRate` → "low transmission rate"), not the run-together id.
- `answer.ttl` now also stores the reasoner's input (`ag:alignedSubject` / `ag:alignedObject`) and output (`ag:contradicts`), so the reasoning can be inspected and queried with SPARQL.
- The demo app's SPARQL console is read-only and refuses `SERVICE` (federated queries to remote endpoints).

## 2026-10-21 — SAF subset extended to 18 questions (demonstration)

- 13 more SAF questions imported (549 answers in total), each with a rubric and gold key **drafted by Claude as a demonstration, not lecturer-validated**. The 8 questions that can't be written as fixed triples were skipped (see `data/external/saf/README.md`).
- SAF scores are now divided by each question's maximum (0.5–3.5 points), not assumed to be out of 1.
- New English predicates `causes`, `determines`, `follows`, `precedes`, `reduces`; new incompatible pairs causes ⊥ prevents, follows ⊥ precedes. `increases`/`decreases` cover both senses ("cwnd increases" and "slow start increases cwnd"), because students use the same verb for both. The alias "reduces" moved from `decreases` to the new `reduces`.
- Known misfits, kept on purpose to show the method's limits:
  - **"Any two of three reasons"** (SAF_ENC): the key lists all three, so a correct answer can lose points.
  - **Rates** (SAF_TCP1/2): triples say *that* cwnd grows, not *how fast* (exponential vs linear).
  - **Implicit subjects**: many answers never name the topic ("we need a duplex operation"), so the subject goes unmatched.
- **Some aliases were added after reading pilot-split answers only.** The keyword check afterwards showed pilot coverage improving but unseen test answers barely changing (SAF_DUP: 20 of 23 test answers still match no key concept). Exact alias lists don't keep up with paraphrase, which is why LLM extraction and the embedding step matter.

### Offline grading of the extended SAF subset (same day)

- 40 more AI-drafted annotations (55 in total, about 3 answers per question), following the rules in `data/external/saf/README.md`, including filling in subjects the question implies (marked `# implied subject`).
- Fixed after reading real answers: merged `increments`/`lowers` back into `increases`/`decreases` (students use the same verbs), frame bursting's disadvantage uses `requires`, bridges accept "bridge" as subject. Pilot-derived aliases added for TCP, DUPMETH, DQDB, IPv6 and Poisson.
- Gold-mode result on the 32 annotated test answers (AI-drafted keys and annotations, so a demonstration only): Pearson r 0.61, Spearman ρ 0.66, MAE 34.2. The keyword baseline scores r 0.64, MAE 28.8.
- Failure patterns seen, useful for the article's discussion:
  - near-synonym predicates count as different: *avoids* vs *reduces*, *minimizes* vs *prevents*, *requires* vs *causes*;
  - typos and long paraphrases fall below τl ("the playload", "the source of the received packet");
  - an unknown wrong concept can earn partial credit by embedding ("character oriented encoding" vs Binary Encoding);
  - SAF graders accept reasons the key doesn't list (e.g. "duplicates waste bandwidth" scored full marks).

## 2026-10-21 — Separate namespaces and a concept hierarchy

- **Namespaces.** Schema and data no longer share one namespace:
  - `ag:` = `http://example.org/autograde/ontology#`: classes, properties, the predicate vocabulary, status values;
  - `key:` = `http://example.org/autograde/key/`: the lecturer's data (concepts, key facts, rubric criteria);
  - `ans:` = `http://example.org/autograde/answer/`: student data (answers, sentences, student facts, ledger entries).

  Criteria now include the question id (`key:Q1_K2_Produk`), since criterion names repeat across questions.
- **Concept hierarchy (formula change to §4 `sim`).** `gold.yaml` concepts may list `broader:` concepts, written to `gold.ttl` as `skos:broader` (W3C SKOS). For two known concepts, sim(key, student) is:
  - 1.0 if they are the same, or the student's concept is narrower (more specific) than the key's;
  - `broader_similarity` = 0.70 if the student's concept is broader (more general) than the key's (partial credit, flagged for review);
  - 0.0 otherwise.

  The hierarchy is transitive (`skos:broader+`). 0.70 lies in the partial band for every calibration grid point, and grading refuses to run if it doesn't.
- **Q1 hierarchy (demonstration, to confirm with the lecturer):** Glukosa → Makanan, Oksigen → Gas, CO2 → Gas, Cahaya → Energi. With it, the deck's answer A07 scores 70 with the real embedding model, through a link the lecturer wrote. (Before, it scored 60, because cos(makanan, glukosa) = 0.36.)
- A broader concept never aligns for the reasoner (0.70 < τh), so a vague answer can't trigger a contradiction.

## Open — needs a human decision

- **Pronoun subjects.** Many SAF answers start "It is used to…". In LLM mode the grounding check keeps "it" as the subject, which doesn't match "DHCP". Options: resolve pronouns to the question's topic concept, or accept the miss. (The AI-drafted annotations keep the student's explicit subjects.)
- **SAF in the article.** The deck lists SAF as an optional comparison, pending the lecturer's approval. If it's used, the gold triples need a human review first.

- ~~The deck's partial-credit example does not hold with the chosen embedding model~~: resolved by the concept hierarchy (see the namespaces and hierarchy entry above).
- **Unknown concept vs gold concept** compares against the concept's id label only ("glukosa"), not its aliases ("gula", cos 0.541). Taking the max over id and aliases is a candidate change to `sim`.
