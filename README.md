# AutoGrade-RDF

Auditable short-answer scoring for Indonesian answers. The score is a published formula over a ledger of RDF triple matches weighted by the lecturer's rubric; SWRL (Pellet) detects limited contradictions; an LLM only writes feedback from the ledger. See `PROTOTYPE_PLAN.md` (single source of truth) and `docs/DECISIONS.md`.

## Setup

```bash
# The project folder is synced by iCloud, which hides files inside a venv and breaks imports,
# so the venv lives outside ~/Documents and .venv is a symlink to it.
uv venv --python 3.12 ~/.venvs/semantic_web_final && ln -sfn ~/.venvs/semantic_web_final .venv
uv pip install --python .venv/bin/python -r requirements.txt -e .
cp .env.example .env          # add ANTHROPIC_API_KEY for LLM extraction, feedback and baseline B2
```

Pellet needs **Java 25+** (Owlready2 0.51). Without a system JDK, `pip install jdk4py` provides one; point `JAVA_EXE` at `python -c "import jdk4py; print(jdk4py.JAVA)"`. It is looked up in `JAVA_EXE`, `JAVA_HOME`, `~/.local/share/jdk/*`, then `PATH`. Without Java, set `reasoner: sparql` in `config/config.yaml`.

## Run

```bash
.venv/bin/pytest                                   # all tests, offline
python -m autograde gold --question Q1             # validate gold.yaml -> gold.ttl + docs/gold_Q1_review.md
python -m autograde run --question Q1 --mode gold --split all --synthetic --template-feedback   # offline demo
python -m autograde evaluate --run <run_id>         # also reports B3/G1/G2 graph metrics (comparison only)
streamlit run app/streamlit_app.py
```

Lecturer tools (see `docs/DECISIONS.md`, 2026-10-21 lecturer tools):

```bash
python -m autograde propose --question Q1          # draft gold triples -> gold_proposed.yaml (never gold.yaml)
python -m autograde propose --question all --no-write   # compare drafts with the current keys
python -m autograde override --run <run_id>        # apply data/human/overrides.yaml (also from the app's Tinjauan Dosen page)
```

- **Usulan Kunci** (app): draft triples from the reference answer, pick criteria and weights, download the accepted ones in `gold.yaml` format.
- **Tinjauan Dosen** (app): review queue (partial, contradicted, premise gaps), per-triple corrections with reason and reviewer; corrected copies only.
- **Rule 4** (premise gaps): `requires: [..]` on a gold triple marks its premises; a credited conclusion without credited premises is flagged in feedback. It never changes the score.

Cyber law & security set (Indonesian, AI-drafted keys from UU PDP, UU ITE, NIST, CISA and OWASP; see `docs/DECISIONS.md`):

```bash
python -m autograde run --question HS1 --mode gold --split all --synthetic --template-feedback   # HS1-HS3, KS1-KS3
```

SAF subset (real English answers, AI-drafted gold triples; see `data/external/saf/README.md`):

```bash
python -m autograde run --question all --mode gold --split all --saf --annotated-only --template-feedback
```

Full command list: plan Section 8. Real data goes in `data/answers/answers.csv`, `data/human/scores.csv` (per criterion), `data/annotations/` (gold mode) and `data/human/evidence_audit.csv` / `overrides.yaml`. `data/synthetic/` is demo data only.
