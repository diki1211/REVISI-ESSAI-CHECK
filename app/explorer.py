"""Interactive knowledge-graph explorer ("Semantic Explorer") for the demo app.

Node ids are the RDF names (ag: schema, key: lecturer's data, ans: student data) and edge labels are the RDF/OWL property names, so the picture is the same
graph stored in gold.ttl, answer.ttl, ledger.ttl and the ontology. Drawn with vis-network 9.1.9, vendored in
app/static/ so the demo works offline.
"""
import json
from pathlib import Path

from autograde import gold, io
from autograde.match import mu
from autograde.models import STATUS_IRI_NAME, LedgerEntry, StudentTriple

VIS_JS = Path(__file__).parent / "static" / "vis-network.min.js"

NODE_TYPES = {  # key: (legend label, colour, vis shape, shown by default)
    "answer": ("Jawaban", "#f97316", "ellipse", True),
    "student": ("Triple jawaban", "#6366f1", "dot", True),
    "reference": ("Triple acuan", "#3b82f6", "box", True),
    "concept": ("Konsep", "#10b981", "dot", True),
    "unknown": ("Konsep tak dikenal", "#9ca3af", "dot", True),
    "relation": ("Predikat (ag:Relation)", "#eab308", "diamond", True),
    "sentence": ("Kalimat (PROV-O)", "#64748b", "box", False),
}
EDGE_TYPES = {  # key: (legend label, colour, dashed, width, shown by default)
    "asserted": ("Relasi eksplisit (RDF)", "#94a3b8", False, 1, True),
    "ontology": ("Relasi ontologi (OWL)", "#ca8a04", False, 2, True),
    "match": ("Cocok / Parsial (ledger)", "#10b981", True, 2, True),
    "inferred": ("Disimpulkan Pellet (SWRL)", "#dc2626", True, 3, True),
    "aligned": ("Selaras (masukan reasoner)", "#a855f7", True, 1, False),
    "hierarchy": ("Hierarki konsep (skos:broader)", "#0d9488", True, 2, True),
}


def short_answer(qid, answer_id):
    return answer_id[len(qid) + 1:] if answer_id.startswith(qid + "_") else answer_id


def load_answer(answer_dir):
    """Saved outputs of one graded answer (written by pipeline.run_answer)."""
    trace = io.load_json(answer_dir / "trace.json")
    return {"answer_id": answer_dir.name,
            "students": [StudentTriple(**t) for t in io.load_json(answer_dir / "student_triples.json")],
            "entries": [LedgerEntry(**e) for e in io.load_json(answer_dir / "ledger.json")],
            "sentences": [tuple(s) for s in io.load_json(answer_dir / "sentences.json")],
            "score": io.load_json(answer_dir / "score.json"),
            "sigmas": {(t, r): s for t, r, s in trace["sigmas"]},
            "aligned": {tuple(x) for x in trace["aligned"]},
            "contradictions": {tuple(x) for x in trace["contradictions"]}}


def build(ctx, answer_dirs, params, human=None, predicates=None):
    """{nodes, edges, details} for one question and any number of graded answers."""
    qid, human = ctx.qid, human or {}
    preds = {p["id"]: p for p in (predicates or io.load_predicates())["predicates"]}
    criteria = {c["id"]: c["description"] for c in ctx.rubric["criteria"]}
    nodes, edges, details = {}, [], {}

    def node(nid, kind, label, title):
        nodes.setdefault(nid, {"id": nid, "kind": kind, "label": label, "title": title})

    def edge(src, dst, kind, label, title=None):
        edges.append({"from": src, "to": dst, "kind": kind, "label": label, "title": title or label})

    # --- the lecturer's key (gold.ttl) ---
    ref_status = {r.id: [] for r in ctx.refs}
    for r in ctx.refs:
        rid = f"key:{qid}_{r.id}"
        node(rid, "reference", r.id, f"{r.id}: {' / '.join(r.s)} {r.p} {r.o}")
        for s in r.s:
            edge(rid, f"key:{s}", "asserted", "hasSubject")
        edge(rid, f"ag:{r.p}", "asserted", "hasPredicate")
        edge(rid, f"key:{r.o}", "asserted", "hasObject")
    concepts = ctx.gold_raw["concepts"]
    above = gold.ancestors(concepts)
    for c, spec in concepts.items():
        node(f"key:{c}", "concept", c, c)
        for b in (spec or {}).get("broader") or []:
            edge(f"key:{c}", f"key:{b}", "hierarchy", "skos:broader")

    def hierarchy_note(key_c, stud_c):
        if key_c and stud_c and key_c != stud_c:
            if stud_c in above.get(key_c, ()):
                return f"{stud_c} lebih umum dari {key_c} (skos:broader) → kredit parsial"
            if key_c in above.get(stud_c, ()):
                return f"{stud_c} lebih khusus dari {key_c} (skos:broader) → dihitung sama"
        return None

    # --- the graded answers (answer.ttl + ledger.ttl) ---
    answers = [load_answer(d) for d in answer_dirs]
    used_preds = {r.p for r in ctx.refs}
    by_triple = {}
    for a in answers:
        aid, short = a["answer_id"], short_answer(qid, a["answer_id"])
        node(f"ans:{aid}", "answer", f"{short} · {a['score']['score']:.0f}", f"Jawaban {aid}")
        text = dict(a["sentences"])
        matched = {(e.matched_by, e.reference_id): e for e in a["entries"] if e.matched_by}
        for e in a["entries"]:
            ref_status[e.reference_id].append((short, e))
        for sid, sent in a["sentences"]:
            node(f"ans:{sid}", "sentence", sid.rsplit("_", 1)[1], sent)
            details[f"ans:{sid}"] = {"kind": "Kalimat (prov:Entity)", "title": f"ans:{sid}",
                                    "fields": [["Teks", sent], ["Jawaban", aid]],
                                    "sections": [{"heading": "Triple yang berasal dari kalimat ini",
                                                  "items": [t.id for t in a["students"] if sid in t.sentence_ids] or ["—"]}]}
        for t in a["students"]:
            tid, tn = f"ans:{t.id}", t.id.rsplit("_", 1)[1]
            by_triple[t.id] = t
            used_preds.add(t.p)
            neg = "NOT " if t.negated else ""
            node(tid, "student", f"{short}·{tn}", f"{t.s_text} —{neg}{t.p}→ {t.o_text}")
            edge(tid, f"ans:{aid}", "asserted", "inAnswer")
            edge(tid, f"ag:{t.p}", "asserted", "hasPredicate")
            for role, concept, raw in (("hasSubject", t.s_concept, t.s_text), ("hasObject", t.o_concept, t.o_text)):
                if concept:
                    edge(tid, f"key:{concept}", "asserted", role)
                else:
                    cid = f"ans:{t.id}_{'s' if role == 'hasSubject' else 'o'}"
                    node(cid, "unknown", raw, f"“{raw}” — tidak ada di tabel alias")
                    details[cid] = {"kind": "Konsep tak dikenal", "title": raw,
                                    "fields": [["Dari triple", t.id], ["Peran", role]],
                                    "sections": [{"heading": "Mengapa abu-abu?", "items": [
                                        "Kata ini tidak ada di tabel alias dosen, jadi dibandingkan dengan konsep kunci "
                                        "lewat kemiripan embedding (0–1)."]}]}
                    edge(tid, cid, "asserted", role)
            for sid in t.sentence_ids:
                edge(tid, f"ans:{sid}", "asserted", "prov:wasDerivedFrom")
            reasoning = []
            for r in ctx.refs:
                sig = a["sigmas"].get((t.id, r.id), 0.0)
                rid, e = f"key:{qid}_{r.id}", matched.get((t.id, r.id))
                if (t.id, r.id) in a["contradictions"]:
                    if t.negated:
                        rule = "Aturan 2 (predikat sama, dinegasi)" if t.p == r.p else "Aturan 3 (predikat setara, dinegasi)"
                        why = f"{t.p} dinegasi, padahal kunci menyatakan {r.p}"
                    else:
                        rule, why = "Aturan 1 (predikat inkompatibel)", f"{t.p} incompatibleWith {r.p}, tidak dinegasi"
                    edge(tid, rid, "inferred", "contradicts", f"{rule}: {why}")
                    reasoning.append(f"{r.id} · KONTRADIKSI — disimpulkan Pellet dengan {rule}: {why}; subjek dan objek "
                                     f"selaras (σ = {sig:.2f} ≥ τh {params['tau_h']}) → ag:contradicts.")
                elif e:
                    kind = "Cocok" if e.status == "MATCHED" else "Parsial"
                    edge(tid, rid, "match", f"{kind} σ={sig:.2f}", f"ledger: {e.entry_id} ag:matchedBy {t.id}")
                    band = (f"σ = {sig:.2f} ≥ τh {params['tau_h']} → kredit 1" if kind == "Cocok" else
                            f"τl {params['tau_l']} ≤ σ = {sig:.2f} < τh {params['tau_h']} → kredit δ {params['delta']}, perlu ditinjau")
                    same = "predikat sama" if t.p == r.p else f"predikat {t.p} setara dengan {r.p} (ontologi)"
                    notes = [n for n in (hierarchy_note(r.o, t.o_concept),
                                         *(hierarchy_note(k, t.s_concept) for k in r.s)) if n]
                    reasoning.append(f"{r.id} · {kind.upper()} — {same}; {band}"
                                     + (f" ({'; '.join(notes)})" if notes else "") + ". Dicatat di ledger sebagai bukti (ag:matchedBy).")
                elif mu(r, t, sig, params, ctx.rel) > 0:
                    reasoning.append(f"{r.id} · juga cocok (σ = {sig:.2f}), tetapi triple lain dipilih sebagai bukti (aturan seri).")
                elif (t.id, r.id) in a["aligned"]:
                    edge(tid, rid, "aligned", "aligned", f"alignedSubject + alignedObject (σ = {sig:.2f})")
                    reasoning.append(f"{r.id} · selaras (σ = {sig:.2f}) tetapi predikat {t.p} tidak setara dan tidak "
                                     f"inkompatibel dengan {r.p} → tidak ada kredit, bukan kontradiksi.")
            details[tid] = {
                "kind": "Triple jawaban (ag:StudentTriple)", "title": f"{t.s_text} —{neg}{t.p}→ {t.o_text}",
                "fields": [["IRI", tid], ["Jawaban", aid],
                           ["Subjek", f"“{t.s_text}” → " + (f"key:{t.s_concept} (tabel alias)" if t.s_concept else "? (embedding)")],
                           ["Predikat", f"ag:{t.p}" + (" — DINEGASI" if t.negated else "")],
                           ["Objek", f"“{t.o_text}” → " + (f"key:{t.o_concept} (tabel alias)" if t.o_concept else "? (embedding)")]],
                "sections": [{"heading": "Provenance (prov:wasDerivedFrom)",
                              "items": [f"{s.rsplit('_', 1)[1]}: “{text.get(s, '')}”" for s in t.sentence_ids]},
                             {"heading": "Penalaran", "items": reasoning or [
                                 f"Tidak cocok dengan triple acuan mana pun (σ < τl {params['tau_l']} atau predikat lain)."]}]}
        status_line = lambda e: (f"{e.reference_id} · {STATUS_IRI_NAME[e.status]} · {e.credit:g} × {e.weight:g}"
                                 + (f" (bukti {e.matched_by or e.contradicted_by})" if e.matched_by or e.contradicted_by else ""))
        sc = a["score"]
        fields = [["Skor sistem", f"{sc['score']:.1f}"], ["Hitung ulang SPARQL", f"{sc['sparql_score']:.1f}"]]
        if aid in human:
            fields.append(["Nilai manusia", f"{human[aid]:.1f}"])
        details[f"ans:{aid}"] = {"kind": "Jawaban (ag:Answer)", "title": f"ans:{aid}", "fields": fields,
                                "sections": [{"heading": "Teks", "items": [s for _, s in a["sentences"]] or ["(kosong)"]},
                                             {"heading": "Ledger (satu baris per triple acuan)",
                                              "items": [status_line(e) for e in a["entries"]]}]}

    # --- the ontology's predicate vocabulary (OWL) ---
    _, eq, inc = io.ontology_relations()
    for p in sorted(used_preds):
        node(f"ag:{p}", "relation", p, preds.get(p, {}).get("description", p))
    for p in sorted(used_preds):
        for q in sorted(eq.get(p, {p}) - {p}):
            node(f"ag:{q}", "relation", q, preds.get(q, {}).get("description", q))
        for pair in inc:
            if p in pair:
                q = next(iter(pair - {p}))
                node(f"ag:{q}", "relation", q, preds.get(q, {}).get("description", q))
    shown_rel = {n["label"] for n in nodes.values() if n["kind"] == "relation"}
    seen = set()
    for a, b_set in eq.items():
        for b in b_set - {a}:
            if a in shown_rel and b in shown_rel and frozenset((a, b)) not in seen:
                seen.add(frozenset((a, b)))
                edge(f"ag:{a}", f"ag:{b}", "ontology", "≡ equivalentPredicate")
    for pair in inc:
        a, b = sorted(pair)
        if a in shown_rel and b in shown_rel:
            edge(f"ag:{a}", f"ag:{b}", "ontology", "⊥ incompatibleWith")
    for p in shown_rel:
        details[f"ag:{p}"] = {"kind": "Predikat (ag:Relation)", "title": f"ag:{p}",
                              "fields": [["Arti", preds.get(p, {}).get("description", "—")],
                                         ["Alias (normalisasi)", ", ".join(preds.get(p, {}).get("aliases", [])) or "—"],
                                         ["Setara (≡)", ", ".join(sorted(eq.get(p, {p}) - {p})) or "—"],
                                         ["Inkompatibel (⊥)", ", ".join(sorted(next(iter(x - {p})) for x in inc if p in x)) or "—"]],
                              "sections": [{"heading": "Dari ontologi OWL", "items": [
                                  "≡ simetris dan transitif: dihitung cocok. ⊥ simetris: bahan aturan kontradiksi SWRL."]}]}

    # --- details for key facts and concepts ---
    for r in ctx.refs:
        lines = [f"{s} · {STATUS_IRI_NAME[e.status]}" + (f" (oleh {(e.matched_by or e.contradicted_by).rsplit('_', 1)[1]})"
                                                       if e.matched_by or e.contradicted_by else "")
                 for s, e in ref_status[r.id]]
        details[f"key:{qid}_{r.id}"] = {
            "kind": "Triple acuan (ag:ReferenceTriple)", "title": f"{r.id}: {' / '.join(r.s)} {r.p} {r.o}",
            "fields": [["IRI", f"key:{qid}_{r.id}"], ["Subjek diterima", ", ".join(r.s)], ["Predikat", r.p],
                       ["Objek", r.o], ["Kriteria", f"{r.criterion} — {criteria[r.criterion]}"], ["Bobot", f"{r.weight:g}"]],
            "sections": [{"heading": f"Status di {len(lines)} jawaban yang dimuat", "items": lines or ["Belum ada jawaban dinilai."]}]}
    for c, spec in concepts.items():
        users = [f"{r.id} ({'subjek' if c in r.s else 'objek'})" for r in ctx.refs if c in r.s or c == r.o]
        users += [t.id.rsplit("_", 2)[-2] + "·" + t.id.rsplit("_", 1)[1] for t in by_triple.values()
                  if c in (t.s_concept, t.o_concept)]
        narrower = sorted(x for x, ups in above.items() if c in ups)
        details[f"key:{c}"] = {"kind": "Konsep (ag:Concept, skos:Concept)", "title": f"key:{c}",
                              "fields": [["Alias (tabel dosen)", ", ".join((spec or {}).get("aliases", [])) or "—"],
                                         ["Lebih umum (skos:broader+)", ", ".join(sorted(above.get(c, ()))) or "—"],
                                         ["Lebih khusus", ", ".join(narrower) or "—"]],
                              "sections": [{"heading": "Dipakai oleh", "items": users or ["—"]}]}
    return {"nodes": list(nodes.values()), "edges": edges, "details": details}


def html(graph, height=720):
    """Self-contained page: vis-network inlined, data as JSON, details rendered with textContent (no HTML injection)."""
    data = json.dumps({"graph": graph, "nodeTypes": NODE_TYPES, "edgeTypes": EDGE_TYPES}, ensure_ascii=False)
    data = data.replace("</", "<\\/")  # keep student text from closing the <script> tag
    return TEMPLATE.replace("__VIS__", VIS_JS.read_text(encoding="utf-8")).replace("__DATA__", data) \
                   .replace("__HEIGHT__", str(height))


TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<style>
  body { margin: 0; font-family: Inter, -apple-system, Segoe UI, Helvetica, sans-serif; color: #0f172a; }
  .bar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 6px 0 10px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
          background: #fff; border: 1px solid #e2e8f0; font-size: 12.5px; cursor: pointer; user-select: none; }
  .chip.off { opacity: .35; }
  .dot { width: 10px; height: 10px; border-radius: 50%; }
  .line { width: 18px; height: 0; border-top: 2px solid; }
  .line.dash { border-top-style: dashed; }
  .wrap { display: flex; gap: 12px; height: __HEIGHT__px; }
  #net { flex: 1; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; }
  #panel { width: 330px; overflow: auto; border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px; background: #f8fafc; font-size: 13px; }
  #panel h3 { margin: 2px 0 2px; font-size: 15px; } #panel .kind { color: #64748b; font-size: 12px; }
  #panel table { border-collapse: collapse; margin: 8px 0; width: 100%; }
  #panel td { vertical-align: top; padding: 3px 4px; border-bottom: 1px solid #e2e8f0; }
  #panel td:first-child { color: #64748b; width: 34%; }
  #panel h4 { margin: 12px 0 4px; font-size: 12.5px; text-transform: uppercase; letter-spacing: .03em; color: #475569; }
  #panel li { margin: 3px 0; }
  input[type=search] { padding: 5px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; width: 200px; }
  button { padding: 5px 10px; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; font-size: 12.5px; cursor: pointer; }
  .sep { width: 1px; height: 22px; background: #e2e8f0; margin: 0 4px; }
</style></head><body>
<div class="bar" id="legend"></div>
<div class="bar">
  <input type="search" id="q" placeholder="Cari node… (mis. Oksigen, A07)">
  <button id="fit">Paskan</button><button id="physics">Bekukan tata letak</button>
  <label style="font-size:12.5px"><input type="checkbox" id="labels" checked> label relasi</label>
</div>
<div class="wrap"><div id="net"></div><div id="panel"><h3>Semantic Explorer</h3>
<div class="kind">Klik node untuk melihat penalaran dan provenance. Klik chip di atas untuk menyembunyikan jenis node atau relasi.</div></div></div>
<script>__VIS__</script>
<script>
const D = __DATA__;
const hiddenKinds = new Set(Object.entries(D.nodeTypes).filter(([k, v]) => !v[3]).map(([k]) => k));
const hiddenEdges = new Set(Object.entries(D.edgeTypes).filter(([k, v]) => !v[4]).map(([k]) => k));
const nodes = new vis.DataSet(D.graph.nodes.map(n => {
  const [_, color, shape] = D.nodeTypes[n.kind];
  const box = shape === 'box' || shape === 'ellipse';
  return { id: n.id, label: n.label, title: n.title, kind: n.kind, shape: shape,
           color: { background: color, border: color, highlight: { background: color, border: '#0f172a' } },
           font: box ? { color: '#fff', size: 13 } : { color: '#0f172a', size: 13 },
           size: n.kind === 'answer' ? 22 : n.kind === 'student' ? 12 : 14, hidden: hiddenKinds.has(n.kind) };
}));
let ei = 0;
const edges = new vis.DataSet(D.graph.edges.map(e => {
  const [_, color, dashed, width] = D.edgeTypes[e.kind];
  return { id: 'e' + (ei++), from: e.from, to: e.to, kind: e.kind, label: e.label, fullLabel: e.label, title: e.title,
           arrows: e.kind === 'ontology' ? '' : 'to', dashes: dashed, width: width,
           color: { color: color, highlight: '#0f172a', opacity: e.kind === 'asserted' ? 0.7 : 1 },
           font: { size: 9, color: '#475569', strokeWidth: 2, align: 'top' }, hidden: hiddenEdges.has(e.kind) };
}));
const net = new vis.Network(document.getElementById('net'), { nodes, edges }, {
  physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -60, springLength: 110 },
             stabilization: { iterations: 250 } },
  interaction: { hover: true, tooltipDelay: 120, navigationButtons: false },
  edges: { smooth: { type: 'continuous' } }
});
function chip(label, swatch, key, set, ds, field) {
  const c = document.createElement('span'); c.className = 'chip' + (set.has(key) ? ' off' : '');
  c.appendChild(swatch); c.appendChild(document.createTextNode(label));
  c.onclick = () => { set.has(key) ? set.delete(key) : set.add(key); c.classList.toggle('off');
    ds.update(ds.get({ filter: x => x[field] === key }).map(x => ({ id: x.id, hidden: set.has(key) }))); };
  return c;
}
const legend = document.getElementById('legend');
for (const [k, v] of Object.entries(D.nodeTypes)) {
  const s = document.createElement('span'); s.className = 'dot'; s.style.background = v[1];
  legend.appendChild(chip(v[0], s, k, hiddenKinds, nodes, 'kind'));
}
const sep = document.createElement('span'); sep.className = 'sep'; legend.appendChild(sep);
for (const [k, v] of Object.entries(D.edgeTypes)) {
  const s = document.createElement('span'); s.className = 'line' + (v[2] ? ' dash' : ''); s.style.borderTopColor = v[1];
  legend.appendChild(chip(v[0], s, k, hiddenEdges, edges, 'kind'));
}
function el(tag, text) { const x = document.createElement(tag); if (text !== undefined) x.textContent = text; return x; }
function show(id) {
  const d = D.graph.details[id], p = document.getElementById('panel'); p.replaceChildren();
  if (!d) { p.appendChild(el('h3', id)); return; }
  p.appendChild(el('div', d.kind)).className = 'kind'; p.appendChild(el('h3', d.title));
  const t = el('table');
  for (const [k, v] of d.fields) { const r = el('tr'); r.appendChild(el('td', k)); r.appendChild(el('td', v)); t.appendChild(r); }
  p.appendChild(t);
  for (const s of d.sections) { p.appendChild(el('h4', s.heading)); const ul = el('ul'); s.items.forEach(i => ul.appendChild(el('li', i))); p.appendChild(ul); }
}
net.on('click', e => { if (e.nodes.length) show(e.nodes[0]); });
document.getElementById('fit').onclick = () => net.fit({ animation: true });
let frozen = false;
document.getElementById('physics').onclick = (ev) => { frozen = !frozen; net.setOptions({ physics: { enabled: !frozen } });
  ev.target.textContent = frozen ? 'Gerakkan lagi' : 'Bekukan tata letak'; };
document.getElementById('labels').onchange = (ev) => edges.update(edges.get().map(x => ({ id: x.id, label: ev.target.checked ? x.fullLabel : ' ' })));
document.getElementById('q').oninput = (ev) => {
  const q = ev.target.value.trim().toLowerCase(); if (q.length < 2) return;
  const hit = nodes.get({ filter: n => !n.hidden && (n.label.toLowerCase().includes(q) || (n.title || '').toLowerCase().includes(q)) })[0];
  if (hit) { net.selectNodes([hit.id]); net.focus(hit.id, { scale: 1.2, animation: true }); show(hit.id); }
};
</script></body></html>"""
