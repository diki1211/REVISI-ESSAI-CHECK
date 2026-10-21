"""AutoGrade-RDF demo: streamlit run app/streamlit_app.py

Shows the Semantic Web pieces (OWL ontology, SWRL rules, RDF graphs, SPARQL) behind each score.
Works offline with hand-annotated triples and template feedback. Nothing here changes a system score: the lecturer
review page stores corrections in data/human/overrides.yaml, which produce separate corrected copies
(docs/DECISIONS.md), and the gold proposal page never writes gold.yaml.
"""
import html
import re
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yaml
from rdflib import OWL, RDF, Namespace

import explorer
import rdfviz
from autograde import baselines, graphsim, io, pipeline, propose, review
from autograde import feedback as fb_mod
from autograde import ledger as ledger_mod
from autograde.evaluate import human_totals
from autograde.gold import criterion_weights
from autograde.models import STATUS_IRI_NAME
from autograde.score import score

st.set_page_config(page_title="AutoGrade-RDF", layout="wide")


# ---------- cached loaders ----------

@st.cache_resource
def context(qid):
    return pipeline.Context.load(qid)


@st.cache_data
def answers_table():
    df = io.load_answers(include_synthetic=True, include_saf=True)
    human = io.load_human_scores(include_synthetic=True, include_saf=True)
    totals = {}
    for qid in df.question_id.unique():
        ctx = context(qid)
        sub = human[human.answer_id.isin(df[df.question_id == qid].answer_id)]
        if len(sub):
            totals.update(human_totals(sub, {qid: criterion_weights(ctx.refs)},
                                       dict.fromkeys(sub.answer_id.unique(), qid)).to_dict())
    df["human"] = df.answer_id.map(totals)
    df["annotated"] = df.answer_id.map(lambda a: io.annotation_path(a) is not None)
    return df


def question_label(qid):
    ctx = context(qid)
    lang = {"id": "ID", "en": "EN"}[ctx.rubric.get("language", "id")]
    origin = ("SAF, kunci draf AI" if qid.startswith("SAF_") else "kunci draf AI" if ctx.gold_raw.get("drafted_by")
              else "contoh dek")
    return f"{qid} · {lang} · {origin}"


def gold_notice(ctx):
    if ctx.gold_raw.get("drafted_by"):
        st.warning(f"Triple acuan soal ini disusun oleh **{ctx.gold_raw['drafted_by']}** dan belum divalidasi dosen.")
    elif not ctx.gold_raw.get("validated_by"):
        st.info("Triple acuan ini adalah contoh dari presentasi dan belum divalidasi dosen.")


def read_md(path):
    return re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S).strip()


def chip(status):
    return (f"<span style='background:{rdfviz.STATUS_COLOR[status]};color:white;border-radius:8px;padding:1px 8px;"
            f"font-size:0.85em'>{STATUS_IRI_NAME[status]}</span>")


# ---------- pages ----------

def page_ontology():
    st.header("Ontologi OWL `ag:`")
    st.caption("Skema (TBox) yang dimuat Pellet untuk setiap jawaban. Dibuat oleh `ontology/build_ontology.py`, "
               "dapat dibuka dan diperiksa di Protégé.")
    g = io.ontology_graph()
    SWRL = Namespace("http://www.w3.org/2003/11/swrl#")
    c = st.columns(5)
    c[0].metric("Kelas", sum(1 for x in g.subjects(RDF.type, OWL.Class) if str(x).startswith(str(io.AG))))
    c[1].metric("Object property", len(set(g.subjects(RDF.type, OWL.ObjectProperty))))
    c[2].metric("Data property", len(set(g.subjects(RDF.type, OWL.DatatypeProperty))))
    c[3].metric("Predikat (ag:Relation)", len(set(g.subjects(RDF.type, io.AG.Relation))))
    c[4].metric("Aturan SWRL", len(set(g.subjects(RDF.type, SWRL.Imp))))
    tabs = st.tabs(["Hierarki kelas", "Properti", "Predikat & relasinya", "Aturan SWRL", "Berkas OWL"])
    with tabs[0]:
        st.graphviz_chart(rdfviz.ontology_classes_dot(g))
        st.caption("Garis putus merah: `owl:AllDisjointClasses` — tidak ada individu yang sekaligus triple acuan dan triple jawaban.")
    with tabs[1]:
        st.dataframe(rdfviz.properties_table(g), hide_index=True, use_container_width=True)
    with tabs[2]:
        lang = st.radio("Bahasa", ["Semua", "Indonesia (Q1)", "Inggris (SAF)"], horizontal=True)
        preds = io.load_predicates()["predicates"]
        only = None if lang == "Semua" else {p["id"] for p in preds if p.get("lang") == ("id" if lang.startswith("Indo") else "en")}
        st.graphviz_chart(rdfviz.relations_dot(g, only))
        st.caption("Biru: `ag:equivalentPredicate` (simetris & transitif) → dihitung cocok. "
                   "Merah: `ag:incompatibleWith` (simetris) → bahan aturan kontradiksi SWRL.")
        st.dataframe(pd.DataFrame([{"Predikat": p["id"], "Bahasa": p.get("lang"), "Alias (normalisasi teks)": ", ".join(p.get("aliases", [])),
                                    "Deskripsi": p["description"]} for p in preds
                                   if only is None or p["id"] in only]), hide_index=True, use_container_width=True)
    with tabs[3]:
        st.markdown("Python menegaskan `alignedSubject`/`alignedObject` hanya untuk pasangan dengan σ ≥ τ<sub>h</sub> "
                    "(SWRL tidak bisa menghitung embedding). Pellet lalu menyimpulkan `ag:contradicts`.", unsafe_allow_html=True)
        for block in (io.ROOT / "ontology" / "rules.swrl.txt").read_text(encoding="utf-8").strip().split("\n\n"):
            title, rule = block.split("\n", 1)
            st.markdown(f"**{title.lstrip('# ')}**")
            st.code(rule.replace(" ^ ", " ^\n  ").replace(" -> ", "\n  -> "), language="text")
        st.markdown("1 = predikat inkompatibel dan **tidak** dinegasi · 2 = predikat sama dinegasi · "
                    "3 = predikat setara dinegasi. Asumsi dunia terbuka: triple yang tidak ada **tidak** pernah jadi kontradiksi.")
        st.markdown("4 = **logika argumen**: kesimpulan (triple acuan dengan `requires`) sudah dikreditkan, tetapi premisnya "
                    "berstatus Hilang/Kontradiksi → `ag:lacksPremise`. Aturan ini berjalan **setelah** ledger dibuat, hanya "
                    "untuk umpan balik dan tinjauan dosen, dan **tidak** mengubah skor. `ag:isCredited` pada setiap status "
                    "membuat \"belum dikreditkan\" menjadi fakta positif, jadi aturan tidak memakai negasi (dunia terbuka tetap dihormati).")
    with tabs[4]:
        owl = io.ontology_path().read_text(encoding="utf-8")
        st.download_button("Unduh autograde.owl (RDF/XML)", owl, file_name="autograde.owl")
        st.code(owl[:6000] + ("\n…" if len(owl) > 6000 else ""), language="xml")


def page_question():
    qid = st.selectbox("Soal", io.question_ids(), format_func=question_label)
    ctx = context(qid)
    d = io.question_dir(qid)
    gold_notice(ctx)
    c1, c2 = st.columns(2)
    c1.subheader("Soal")
    c1.markdown(read_md(d / "question.md"))
    c2.subheader("Jawaban acuan")
    c2.markdown(read_md(d / "reference_answer.md"))
    if qid.startswith("SAF_"):
        st.caption("Sumber: SAF (Filighera dkk., 2022), CC-BY-4.0.")
    st.subheader("Rubrik dan triple acuan")
    w = criterion_weights(ctx.refs)
    st.dataframe(pd.DataFrame([{"Kriteria": c["id"], "Deskripsi": c["description"], "Bobot total": w[c["id"]]}
                               for c in ctx.rubric["criteria"]]), hide_index=True, use_container_width=True)
    st.dataframe(pd.DataFrame([{"ID": r.id, "Subjek (diterima)": " / ".join(r.s), "Predikat": r.p, "Objek": r.o,
                                "Kriteria": r.criterion, "Bobot": r.weight, "Premis (requires)": ", ".join(r.requires)}
                               for r in ctx.refs]),
                 hide_index=True, use_container_width=True)
    view = st.radio("Tampilan graf", ["Graf konsep", "RDF terreifikasi"], horizontal=True)
    if view == "Graf konsep":
        st.graphviz_chart(rdfviz.gold_concept_dot(ctx.refs, ctx.gold_raw["concepts"]))
        st.caption("Garis putus abu-abu: subjek alternatif yang juga diterima. Garis putus hijau-biru: hierarki konsep "
                   "dosen (skos:broader) — menyebut konsep yang lebih umum memberi kredit parsial.")
    else:
        st.graphviz_chart(rdfviz.gold_reified_dot(qid, ctx.refs))
        st.caption("Triple RDF biasa tidak bisa diberi bobot, kriteria, atau sumber kalimat, "
                   "jadi setiap triple acuan dijadikan sumber daya `ag:ReferenceTriple`.")
    with st.expander("Konsep dan alias (normalisasi sebelum embedding)"):
        st.dataframe(pd.DataFrame([{"Konsep": f"key:{c}", "Alias": ", ".join((v or {}).get("aliases", [])),
                                    "Lebih umum (skos:broader)": ", ".join((v or {}).get("broader") or [])}
                                   for c, v in ctx.gold_raw["concepts"].items()]), hide_index=True, use_container_width=True)
    with st.expander("gold.ttl"):
        st.code((d / "gold.ttl").read_text(encoding="utf-8"), language="turtle")


def page_grade():
    qid = st.selectbox("Soal", io.question_ids(), format_func=question_label)
    ctx = context(qid)
    gold_notice(ctx)
    df = answers_table()
    df = df[df.question_id == qid]
    source = st.radio("Sumber jawaban", ["Jawaban tersimpan", "Tempel jawaban baru"], horizontal=True)
    if source == "Jawaban tersimpan":
        only_annotated = st.checkbox("Hanya jawaban yang punya anotasi triple (bisa dinilai offline)", value=True)
        if only_annotated:
            df = df[df.annotated]
        if df.empty:
            st.info("Tidak ada jawaban untuk pilihan ini.")
            return
        labels = {f"{a.answer_id} · {a.split}" + (f" · dosen {a.human:.0f}" if pd.notna(a.human) else "")
                  + (" · anotasi ✓" if a.annotated else "") + (" · sintetis" if a.synthetic else ""): a for a in df.itertuples()}
        a = labels[st.selectbox("Jawaban", list(labels))]
        answer_id, text = a.answer_id, a.text
        st.markdown(f"> {html.escape(text)}".replace("\n", "<br>"), unsafe_allow_html=True)
        c = st.columns(3)
        if pd.notna(a.human):
            c[0].metric("Nilai manusia" + (" (SAF)" if a.source == "saf" else " (sintetis)" if a.synthetic else ""), f"{a.human:.1f}")
        c[1].metric("Baseline B1 (kata kunci)", f"{baselines.b1_keyword(text, ctx.refs, ctx.gold_raw['concepts']):.1f}")
        annotation = io.annotation_path(answer_id)
        if annotation is not None:
            by = (io.load_yaml(annotation) or {}).get("annotated_by")
            if by:
                st.warning(f"Anotasi triple jawaban ini ditulis oleh **{by}**.")
    else:
        answer_id = f"{qid}_UI"
        text = st.text_area("Jawaban mahasiswa", height=120)
    has_annotation = io.annotation_path(answer_id) is not None
    mode = st.radio("Ekstraksi triple", ["gold", "llm"], horizontal=True, index=0 if has_annotation else 1,
                    format_func=lambda m: "Anotasi (gold)" if m == "gold" else "LLM (butuh API key)")
    use_llm_fb = st.checkbox("Umpan balik dari LLM (butuh API key)", value=False)
    if st.button("Nilai jawaban", type="primary"):
        if mode == "gold" and not has_annotation:
            st.error("Tidak ada anotasi untuk jawaban ini. Pilih mode LLM.")
            return
        try:
            with st.spinner("Ekstraksi → pencocokan → Pellet/SWRL → ledger → SPARQL…"):
                res = pipeline.run_answer(ctx, answer_id, text, mode, io.ROOT / "outputs" / "ui" / answer_id, use_llm_fb)
        except Exception as e:  # e.g. no API key for LLM extraction
            st.error(f"Gagal menilai: {e}")
            return
        st.session_state["graded"] = {"qid": qid, "answer_id": answer_id, "res": res}
    graded = st.session_state.get("graded")
    if graded and graded["qid"] == qid and graded["answer_id"] == answer_id:
        show_result(qid, answer_id, graded["res"])


def show_result(qid, answer_id, res):
    ctx, sc, entries = context(qid), res["score"], res["entries"]
    st.divider()
    c = st.columns(5)
    c[0].metric("Skor sistem", fb_mod.display_score(sc.score))
    c[1].metric("Σ w·m", f"{sc.sum_weighted_credit:g}")
    c[2].metric("Penalti λ·Σ w·κ", f"{sc.sum_penalty:g}")
    c[3].metric("Σ w", f"{sc.sum_weights:g}")
    ok = abs(sc.score - sc.sparql_score) < 1e-9
    c[4].metric("Hitung ulang SPARQL", fb_mod.display_score(sc.sparql_score), "✓ sama" if ok else "✗ berbeda",
                delta_color="normal" if ok else "inverse")
    with st.expander("Metrik kemiripan graf (pembanding, tidak memengaruhi skor)"):
        g = graphsim.all_metrics(ctx.refs, res["students"], ctx.rel)
        gc = st.columns(3)
        for col, (name, value) in zip(gc, g.items()):
            col.metric(name, f"{value:.1f}")
        st.caption("B3: recall triple dengan id konsep persis (tanpa embedding/hierarki). G1: F1 graf — sisi tambahan "
                   "menurunkan presisi. G2: 1 − GED/ukuran graf (node = konsep, sisi = predikat setara). "
                   "Dilaporkan di Evaluasi sebagai pembanding Pers. 6.")
    tabs = st.tabs(["Ledger & umpan balik", "Graf interaktif", "Graf penyelarasan", "Penalaran", "RDF (Turtle)", "SPARQL"])
    with tabs[0]:
        show_ledger(ctx, answer_id, res)
    with tabs[1]:
        human = answers_table().set_index("answer_id").human.dropna().to_dict()
        components.html(explorer.html(explorer.build(ctx, [res["out_dir"]], ctx.params, human), height=600),
                        height=700, scrolling=False)
    with tabs[2]:
        st.graphviz_chart(rdfviz.alignment_dot(ctx.refs, res["students"], entries, res["trace"]))
        st.caption("Kiri: triple hasil ekstraksi ([konsep] dari tabel alias, [?] = tidak dikenal → embedding). "
                   "Kanan: triple acuan berwarna sesuai status. Panah tebal: bukti di ledger; "
                   "merah: `ag:contradicts` dari SWRL; titik-titik: selaras tetapi predikat lain.")
    with tabs[3]:
        show_reasoning(ctx, res)
    with tabs[4]:
        out = res["out_dir"]
        for name, caption in (("answer.ttl", "Triple jawaban + provenance PROV-O + masukan/keluaran penalaran"),
                              ("ledger.ttl", "Ledger: satu ag:LedgerEntry per triple acuan"),
                              ("gold.ttl", "Graf acuan")):
            path = io.question_dir(qid) / name if name == "gold.ttl" else out / name
            with st.expander(f"{name} — {caption}", expanded=name == "ledger.ttl"):
                st.code(path.read_text(encoding="utf-8"), language="turtle")
                st.download_button(f"Unduh {name}", path.read_text(encoding="utf-8"), file_name=name, key=f"dl_{name}")
    with tabs[5]:
        g = rdfviz.merged_graph(rdfviz.answer_graph_paths(qid, res["out_dir"]))
        st.caption(f"Graf gabungan: ontologi + gold.ttl + answer.ttl + ledger.ttl ({len(g)} triple). Hanya baca.")
        sparql_console(g, rdfviz.ANSWER_QUERIES, "ans")


def show_ledger(ctx, answer_id, res):
    entries, refs = res["entries"], {r.id: r for r in ctx.refs}
    sentences = dict(res["sentences"])
    rows = "".join(
        f"<tr><td><code>{e.reference_id}</code></td><td>{html.escape(fb_mod.triple_label(refs[e.reference_id]))}</td>"
        f"<td>{e.criterion}</td><td>{e.weight:g}</td><td>{chip(e.status)}{' ⚑' if e.needs_review else ''}</td>"
        f"<td>{e.credit:g}</td><td>{'–' if e.sigma is None else f'{e.sigma:.2f}'}</td>"
        f"<td>{html.escape(' '.join(sentences.get(s, '') for s in e.sentence_ids)) or '–'}</td></tr>"
        for e in entries)
    st.markdown("<table><tr><th>Ref</th><th>Triple acuan</th><th>Kriteria</th><th>w</th><th>Status</th><th>m</th>"
                f"<th>σ</th><th>Kalimat bukti</th></tr>{rows}</table>", unsafe_allow_html=True)
    st.caption("⚑ = parsial, perlu ditinjau dosen. Setiap baris ditelusuri ke triple acuan, kriteria, bobot, dan kalimat.")
    for g in res["trace"].get("premise_gaps", []):
        st.warning(f"Aturan 4: {g.reference_id} ({fb_mod.triple_label(refs[g.reference_id])}) dikreditkan, tetapi premis "
                   f"{g.premise_id} ({fb_mod.triple_label(refs[g.premise_id])}) berstatus "
                   f"{STATUS_IRI_NAME[g.premise_status]}. Hanya catatan; skor tidak berubah.")
    ov_path = io.ROOT / "data" / "human" / "overrides.yaml"
    overrides = [o for o in (io.load_yaml(ov_path) or []) if o["answer_id"] == answer_id] if ov_path.exists() else []
    if overrides:
        fixed = ledger_mod.apply_overrides(entries, overrides, ctx.params)
        st.subheader("Ledger setelah koreksi dosen")
        st.dataframe(pd.DataFrame([{"Ref": e.reference_id, "Status": STATUS_IRI_NAME[e.status], "m": e.credit,
                                    "Koreksi": f"{e.override['by']}: {e.override['reason']}" if e.override else ""}
                                   for e in fixed]), hide_index=True)
        st.metric("Skor terkoreksi", fb_mod.display_score(score(answer_id, fixed, ctx.params).score))
    st.subheader("Umpan balik")
    fb = res["feedback"]
    for c in fb.claims:
        st.markdown(f"- {html.escape(c.text)} <small>({', '.join(c.ledger_entry_ids)})</small>", unsafe_allow_html=True)
    st.markdown(f"_{html.escape(fb.summary)}_ · sumber: {'LLM' if fb.source == 'llm' else 'templat'}")


def show_reasoning(ctx, res):
    p = ctx.params
    st.markdown(f"**1 · Normalisasi konsep** — tabel alias dulu, embedding hanya untuk konsep yang tidak dikenal. "
                f"Parameter: τ<sub>h</sub> = {p['tau_h']}, τ<sub>l</sub> = {p['tau_l']}, δ = {p['delta']}, λ = {p['lambda']}.",
                unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([{"Triple": t.id.rsplit("_", 1)[1], "Subjek": t.s_text, "→ konsep": t.s_concept or "? (embedding)",
                                "Predikat": t.p, "Negasi": t.negated, "Objek": t.o_text,
                                "→ konsep ": t.o_concept or "? (embedding)", "Kalimat": ", ".join(t.sentence_ids)}
                               for t in res["students"]]), hide_index=True, use_container_width=True)
    if res["students"]:
        st.markdown("**2 · σ = min(sim subjek, sim objek)** untuk setiap pasangan (baris: triple jawaban, kolom: triple acuan).")
        table = rdfviz.sigma_table(ctx.refs, res["students"], res["trace"]["sigmas"])
        st.dataframe(table.style.format("{:.2f}").background_gradient(cmap="Greens", vmin=0, vmax=1),
                     use_container_width=True)
    aligned = res["trace"]["aligned"]
    st.markdown(f"**3 · Fakta yang ditegaskan Python ke Pellet** (σ ≥ τ<sub>h</sub>): {len(aligned)} pasangan",
                unsafe_allow_html=True)
    if aligned:
        st.code("\n".join(f"ans:{t} ag:alignedSubject key:{ctx.qid}_{r} ; ag:alignedObject key:{ctx.qid}_{r} ." for t, r in aligned),
                language="turtle")
    contra = res["trace"]["contradictions"]
    st.markdown(f"**4 · Disimpulkan Pellet dengan aturan SWRL:** {len(contra)} `ag:contradicts`")
    if contra:
        st.code("\n".join(f"ans:{t} ag:contradicts key:{ctx.qid}_{r} ." for t, r in contra), language="turtle")
    else:
        st.caption("Tidak ada kontradiksi. Triple acuan yang tidak disebut tetap Hilang (asumsi dunia terbuka).")
    gaps = res["trace"].get("premise_gaps", [])
    st.markdown(f"**5 · Aturan 4 (logika argumen) atas ledger:** {len(gaps)} `ag:lacksPremise` — tidak mengubah skor")
    if gaps:
        st.code("\n".join(f"ans:{g.entry_id} ag:lacksPremise ans:{g.premise_entry_id} .  "
                          f"# {g.reference_id} dikreditkan, premis {g.premise_id} {STATUS_IRI_NAME[g.premise_status]}"
                          for g in gaps), language="turtle")
    elif any(r.requires for r in ctx.refs):
        st.caption("Setiap kesimpulan yang dikreditkan didukung premis yang juga dikreditkan.")
    else:
        st.caption("Kunci soal ini tidak mencantumkan premis (`requires`).")
    if res["log"]:
        with st.expander(f"{len(res['log'])} triple dibuang saat ekstraksi (cek grounding)"):
            st.json(res["log"])


def sparql_console(g, presets, key):
    preset = st.selectbox("Kueri contoh", list(presets), key=f"preset_{key}")
    query = st.text_area("SPARQL", presets[preset], height=260, key=f"q_{key}_{preset}")
    if st.button("Jalankan kueri", key=f"run_{key}"):
        try:
            result = rdfviz.run_query(g, query)
        except Exception as e:
            st.error(f"Kueri gagal: {e}")
            return
        if isinstance(result, str):
            st.code(result or "# (graf kosong)", language="turtle")
        else:
            st.dataframe(result, hide_index=True, use_container_width=True)
            st.caption(f"{len(result)} baris")


def page_sparql():
    st.header("Konsol SPARQL")
    st.caption("Kueri berjalan pada graf RDF lokal (rdflib), hanya baca. Kueri federasi (SERVICE) dinonaktifkan.")
    graded = st.session_state.get("graded")
    runs = pipeline.completed_runs()
    options = (["Jawaban terakhir yang dinilai"] if graded else []) + [f"Run: {r.name}" for r in runs]
    if not options:
        st.info("Nilai sebuah jawaban dulu, atau buat run: `python -m autograde run …`.")
        return
    choice = st.selectbox("Graf", options)
    if choice.startswith("Jawaban"):
        g = rdfviz.merged_graph(rdfviz.answer_graph_paths(graded["qid"], graded["res"]["out_dir"]))
        presets = rdfviz.ANSWER_QUERIES
    else:
        run_dir = runs[[f"Run: {r.name}" for r in runs].index(choice)]
        qids = set(pd.read_csv(run_dir / "scores.csv", dtype=str).question_id)
        g = rdfviz.merged_graph(rdfviz.run_graph_paths(run_dir, qids))
        presets = {**rdfviz.RUN_QUERIES, **rdfviz.ANSWER_QUERIES}
    st.caption(f"{len(g)} triple RDF dimuat.")
    sparql_console(g, presets, "global")


def page_explorer():
    st.header("Penjelajah Graf (Semantic Explorer)")
    st.caption("Graf pengetahuan satu soal. Node = sumber daya RDF dari tiga namespace: ag: (skema/ontologi), "
               "key: (data dosen: konsep, triple acuan, hierarki skos:broader), ans: (data mahasiswa: jawaban, triple, "
               "ledger). Garis = properti RDF/OWL/SKOS/PROV.")
    qid = st.selectbox("Soal", io.question_ids(), format_func=question_label, key="explorer_q")
    ctx = context(qid)
    sources = {}
    for run in pipeline.completed_runs():
        dirs = sorted(d for d in run.iterdir() if d.is_dir() and d.name.startswith(qid + "_") and (d / "trace.json").exists())
        if dirs:
            sources[f"Run {run.name} · {len(dirs)} jawaban"] = (dirs, io.load_json(run / "run.json")["params"])
    ui = io.ROOT / "outputs" / "ui"
    dirs = sorted(d for d in ui.glob(qid + "_*") if (d / "trace.json").exists()) if ui.exists() else []
    if dirs:
        sources[f"Dinilai di aplikasi · {len(dirs)} jawaban"] = (dirs, ctx.params)
    if not sources:
        st.info("Belum ada jawaban yang dinilai untuk soal ini. Nilai jawaban di halaman *Nilai Jawaban*, atau buat run "
                "dengan `python -m autograde run …`. Graf kunci tetap ditampilkan di bawah.")
        dirs, params = [], ctx.params
    else:
        dirs, params = sources[st.selectbox("Sumber jawaban", list(sources))]
    names = [d.name for d in dirs]
    chosen = st.multiselect("Jawaban yang ditampilkan", names, default=names[:12]) if names else []
    human = answers_table().set_index("answer_id").human.dropna().to_dict()
    graph = explorer.build(ctx, [d for d in dirs if d.name in chosen], params, human)
    st.caption(f"{len(graph['nodes'])} node · {len(graph['edges'])} relasi")
    components.html(explorer.html(graph, height=640), height=740, scrolling=False)


def page_evaluation():
    runs = [p for p in pipeline.completed_runs() if (p / "evaluation.md").exists()]
    if not runs:
        st.info("Belum ada hasil evaluasi. Jalankan `python -m autograde evaluate --run <run_id>`.")
        return
    run = st.selectbox("Run", runs, format_func=lambda p: p.name)
    st.markdown(run.joinpath("evaluation.md").read_text(encoding="utf-8"))
    cols = st.columns(2)
    for col, name in zip(cols, ["scatter.png", "per_criterion.png"]):
        if (run / name).exists():
            col.image(str(run / name))


STATUS_LABEL = STATUS_IRI_NAME  # MATCHED -> Cocok, …: Indonesian labels in the UI
LABEL_STATUS = {v: k for k, v in STATUS_LABEL.items()}


def page_propose():
    st.header("Usulan Triple Acuan")
    st.caption("Draf triple dari jawaban acuan dosen untuk ditinjau. Draf disimpan di `gold_proposed.yaml`, "
               "**tidak pernah** menimpa `gold.yaml` dan tidak dipakai untuk menilai. Triple yang diterima disalin "
               "dosen ke `gold.yaml`, lalu `python -m autograde gold --question <id>`.")
    root = io.ROOT / "data" / "questions"
    qids = sorted(p.name for p in root.iterdir() if (p / "reference_answer.md").exists() and (p / "rubric.yaml").exists())
    qid = st.selectbox("Soal", qids, key="prop_q")
    d = io.question_dir(qid)
    st.markdown(read_md(d / "reference_answer.md"))
    method = st.radio("Metode", list(propose.METHODS), horizontal=True, key="prop_m",
                      format_func=lambda m: "Berbasis aturan (offline)" if m == "rule" else "LLM (butuh API key)")
    if st.button("Buat usulan", type="primary", key="prop_run"):
        try:
            st.session_state["draft"] = propose.propose(qid, method)
        except Exception as e:  # no API key, missing files
            st.error(f"Gagal membuat usulan: {e}")
            return
    draft = st.session_state.get("draft")
    if not draft or draft["question_id"] != qid or draft["method"] != method:
        return
    st.caption(f"Disusun oleh: {draft['proposed_by']} · {draft['proposed_on']}")
    c = draft["comparison"]
    if c:
        cols = st.columns(3)
        cols[0].metric("Triple diusulkan", c["proposed"])
        cols[1].metric("Sudah ada di kunci (presisi)", f"{c['in_gold']} ({c['precision'] if c['precision'] is not None else '–'})")
        cols[2].metric("Kunci yang terliput (recall)", f"{c['gold_covered']}/{c['gold_total']} ({c['recall']})")
    else:
        st.info("Soal ini belum punya gold.yaml, jadi usulan tidak dibandingkan.")
    criteria = [x["id"] for x in io.load_yaml(d / "rubric.yaml")["criteria"]]
    table = pd.DataFrame([{"Terima": bool(t["accept"]), "ID": t["id"], "Subjek": " / ".join(t["s"]), "Predikat": t["p"],
                           "Objek": t["o"], "Kriteria": t["criterion"], "Bobot": t["weight"],
                           "Sudah di kunci": t["in_gold"] or "", "Kalimat sumber": t["source"]} for t in draft["triples"]])
    if table.empty:
        st.warning("Tidak ada triple yang bisa diusulkan dari jawaban acuan ini.")
        return
    edited = st.data_editor(
        table, hide_index=True, use_container_width=True, key=f"prop_edit_{qid}_{method}",
        disabled=["ID", "Subjek", "Predikat", "Objek", "Sudah di kunci", "Kalimat sumber"],
        column_config={"Terima": st.column_config.CheckboxColumn("Terima"),
                       "Kriteria": st.column_config.SelectboxColumn("Kriteria", options=criteria),
                       "Bobot": st.column_config.NumberColumn("Bobot", min_value=0.5, step=0.5)})
    for t, row in zip(draft["triples"], edited.to_dict("records")):
        t.update(accept=bool(row["Terima"]), criterion=row["Kriteria"] if pd.notna(row["Kriteria"]) else None,
                 weight=float(row["Bobot"]))
    if draft["new_concepts"]:
        with st.expander(f"{len(draft['new_concepts'])} konsep baru (belum ada di gold.yaml)"):
            st.dataframe(pd.DataFrame([{"Konsep": k, "Alias": ", ".join(v["aliases"])} for k, v in draft["new_concepts"].items()]),
                         hide_index=True)
    accepted = {t["id"] for t in draft["triples"] if t["accept"]}
    cols = st.columns(2)
    if cols[0].button("Simpan draf tinjauan", key="prop_save"):
        out, md = propose.write(draft)
        st.success(f"Disimpan: {out.relative_to(io.ROOT)} dan {md.relative_to(io.ROOT)}. gold.yaml tidak diubah.")
    snippet = propose.as_gold_yaml(draft, accepted)
    unready = [t["id"] for t in draft["triples"] if t["id"] in accepted and not t["criterion"]]
    if unready:
        cols[1].caption(f"Isi kriteria untuk {', '.join(unready)} sebelum menyalin ke gold.yaml.")
    cols[1].download_button(f"Unduh {len(accepted)} triple diterima (format gold.yaml)",
                            yaml.safe_dump(snippet, allow_unicode=True, sort_keys=False),
                            file_name=f"{qid}_gold_accepted.yaml", disabled=not accepted)
    if draft["log"]:
        with st.expander(f"{len(draft['log'])} bagian dilewati"):
            st.json(draft["log"])


def page_review():
    st.header("Tinjauan Dosen")
    st.caption("Koreksi status per triple acuan. Koreksi disimpan ke `data/human/overrides.yaml` (dengan nama, tanggal "
               "dan alasan), lalu dihitung ulang menjadi `ledger_corrected.*` dan `score_corrected.json` dengan cek "
               "paritas SPARQL. Ledger dan skor sistem asli **tidak** berubah, dan skor terkoreksi **tidak** dipakai "
               "di evaluasi.")
    runs = pipeline.completed_runs()
    if not runs:
        st.info("Belum ada run. Buat dengan `python -m autograde run …`, lalu tinjau di sini.")
        return
    run = st.selectbox("Run", runs, format_func=lambda p: p.name, key="rev_run")
    queue = review.queue(run.name)
    only = st.checkbox("Hanya jawaban yang perlu ditinjau (parsial, kontradiksi, atau celah premis)", value=True,
                       key="rev_only")
    shown = queue[queue.needs_review | queue.has_overrides] if only else queue
    st.dataframe(shown.rename(columns={"answer_id": "Jawaban", "question_id": "Soal", "score": "Skor sistem",
                                       "partial": "Parsial", "contradicted": "Kontradiksi", "premise_gaps": "Celah premis",
                                       "corrected_score": "Skor terkoreksi", "has_overrides": "Dikoreksi",
                                       "needs_review": "Perlu ditinjau"}),
                 hide_index=True, use_container_width=True)
    if shown.empty:
        st.success("Tidak ada jawaban yang perlu ditinjau di run ini.")
        return
    answer_id = st.selectbox("Jawaban", list(shown.answer_id), key="rev_answer")
    qid = review.question_of(run, answer_id)
    ctx = context(qid)
    refs = {r.id: r for r in ctx.refs}
    entries = review.load_entries(run, answer_id)
    sentences = dict(io.load_json(run / answer_id / "sentences.json"))
    st.markdown("> " + html.escape(" ".join(sentences.values())), unsafe_allow_html=True)
    trace = io.load_json(run / answer_id / "trace.json")
    for g in trace.get("premise_gaps", []):
        st.warning(f"Aturan 4: {g['reference_id']} dikreditkan tanpa premis {g['premise_id']} "
                   f"({STATUS_LABEL[g['premise_status']]}).")
    existing = {o["reference_id"]: o for o in review.load_overrides() if o["answer_id"] == answer_id}
    table = pd.DataFrame([{"Ref": e.reference_id, "Triple acuan": fb_mod.triple_label(refs[e.reference_id]),
                           "Kriteria": e.criterion, "w": e.weight,
                           "Status sistem": STATUS_LABEL[e.status] + (" ⚑" if e.needs_review else ""),
                           "Status dosen": STATUS_LABEL[existing[e.reference_id]["status"]] if e.reference_id in existing
                           else STATUS_LABEL[e.status],
                           "Alasan": existing.get(e.reference_id, {}).get("reason", ""),
                           "σ": None if e.sigma is None else round(e.sigma, 2),
                           "Kalimat bukti": " ".join(sentences.get(s, "") for s in e.sentence_ids)} for e in entries])
    edited = st.data_editor(
        table, hide_index=True, use_container_width=True, key=f"rev_edit_{run.name}_{answer_id}",
        disabled=["Ref", "Triple acuan", "Kriteria", "w", "Status sistem", "σ", "Kalimat bukti"],
        column_config={"Status dosen": st.column_config.SelectboxColumn("Status dosen", options=list(LABEL_STATUS),
                                                                        required=True),
                       "Alasan": st.column_config.TextColumn("Alasan (wajib jika status diubah)", width="medium")})
    cols = st.columns(2)
    by = cols[0].text_input("Nama penilai", value=next(iter(existing.values()), {}).get("by", ""), key="rev_by")
    on = cols[1].date_input("Tanggal", value=date.today(), key="rev_date")
    if st.button("Simpan koreksi & hitung ulang", type="primary", key="rev_save"):
        corrections = {row["Ref"]: (LABEL_STATUS[row["Status dosen"]], row["Alasan"] or "")
                       for row in edited.to_dict("records")}
        try:
            review.save_corrections(answer_id, corrections, entries, by=by, on=on)
            review.apply_run(run.name, [answer_id])
        except (review.OverrideError, ValueError) as e:
            st.error(f"Koreksi tidak disimpan: {e}")
        else:
            st.success("Koreksi disimpan ke data/human/overrides.yaml dan dihitung ulang. Skor sistem asli tidak berubah.")
    c = st.columns(2)
    c[0].metric("Skor sistem", fb_mod.display_score(io.load_json(run / answer_id / "score.json")["score"]))
    corrected = run / answer_id / "score_corrected.json"
    if corrected.exists():
        sc = io.load_json(corrected)
        c[1].metric("Skor terkoreksi", fb_mod.display_score(sc["score"]),
                    "✓ SPARQL sama" if abs(sc["score"] - sc["sparql_score"]) < 1e-9 else "✗ SPARQL berbeda")


PAGES = {"Ontologi": page_ontology, "Soal & Kunci": page_question, "Usulan Kunci": page_propose,
         "Penjelajah Graf": page_explorer, "Nilai Jawaban": page_grade, "Tinjauan Dosen": page_review,
         "Konsol SPARQL": page_sparql, "Evaluasi": page_evaluation}
st.sidebar.title("AutoGrade-RDF")
page = st.sidebar.radio("Halaman", list(PAGES), index=list(PAGES).index("Nilai Jawaban"))
st.sidebar.caption("Skor = fungsi eksplisit atas ledger triple RDF (Pers. 6). LLM tidak pernah menentukan skor.")
PAGES[page]()
