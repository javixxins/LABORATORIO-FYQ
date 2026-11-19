/* Laboratorio FyQ — interfaz */
"use strict";

const S = { config: {}, cats: [], items: [], grupos: [], practicas: [], view: "panel", filtroCat: null, buscar: "", P: null, lastRes: null };

const UNIDADES = ["uds", "mL", "L", "g", "mg", "kg", "gotas", "cm", "m"];
const AGRUP = [[0, "Automático"], [1, "Individual"], [2, "Parejas"], [3, "Tríos"], [4, "Grupos de 4"]];
const AMBITOS = [["grupo", "Por grupo"], ["alumno", "Por alumno"], ["total", "Común (profesor)"]];
const SYM_DEF = { RECIPIENTES: "Rc", REACTIVOS: "Rv", INSTRUMENTOS: "In", OTROS: "Ot" };

// ------------------------------------------------------------------ utilidades
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (x) => { if (x == null || x === "") return ""; const n = Number(x); return Math.abs(n - Math.round(n)) < 1e-9 ? String(Math.round(n)) : n.toFixed(2).replace(/0+$/, "").replace(/\.$/, "").replace(".", ","); };
const qtxt = (q, u) => `${fmt(q)} ${u === "uds" ? (Math.abs(q - 1) < 1e-9 ? "ud." : "uds.") : u}`;

async function api(url, opts = {}) {
  const o = Object.assign({}, opts);
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch(url, o);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.blob();
  if (!r.ok) { const e = new Error((data && data.error) || "Error " + r.status); e.data = data; throw e; }
  return data;
}

function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), err ? 5000 : 2600);
}

function distribuir(n, t) {
  n = Math.max(0, n | 0); t = Math.max(1, t | 0);
  if (!n) return [];
  if (t === 1) return Array(n).fill(1);
  if (n <= t) return [n];
  if (t === 2) { const s = Array(Math.floor(n / 2)).fill(2); if (n % 2) s[s.length - 1] += 1; return s; }
  const g = Math.ceil(n / t), base = Math.floor(n / g), extra = n % g;
  return Array(extra).fill(base + 1).concat(Array(g - extra).fill(base));
}
function nombreTam(s, plural) {
  const b = { 1: "alumno", 2: "pareja", 3: "trío" }[s] || `grupo de ${s}`;
  if (!plural) return b;
  return { alumno: "alumnos", pareja: "parejas", "trío": "tríos" }[b] || b.replace("grupo", "grupos");
}
function describir(sizes) {
  if (!sizes.length) return "sin alumnos";
  const c = {}; sizes.forEach((s) => (c[s] = (c[s] || 0) + 1));
  return Object.keys(c).sort((a, b) => c[b] - c[a]).map((s) => {
    s = +s; const n = c[s];
    if (s === 1) return `${n} individual${n > 1 ? "es" : ""}`;
    if (s === 3 && n === 1) return "1 grupo de 3";
    return `${n} ${nombreTam(s, n > 1)}`;
  }).join(" + ");
}
function parseLista(txt) {
  return (txt || "").split(/\r?\n/).map((l) => l.trim().replace(/^[;,\t ]+|[;,\t ]+$/g, "").replace(/^\d+[.)\-\s]+/, "").trim())
    .filter((l) => l && !/^(nombre|alumno|apellidos?)\b/i.test(l))
    .map((l) => { if ((l.match(/,/g) || []).length === 1) { const [a, b] = l.split(",").map((x) => x.trim()); if (a && b) return b + " " + a; } return l.replace(/\s+/g, " "); });
}
function catSym(c) {
  if (SYM_DEF[c.nombre]) return SYM_DEF[c.nombre];
  const n = c.nombre.replace(/[^A-Za-zÁÉÍÓÚÑ]/g, "");
  const used = new Set(S.cats.filter((x) => x.id !== c.id).map((x) => SYM_DEF[x.nombre] || ""));
  for (let i = 1; i < n.length; i++) { const s = n[0] + n[i].toLowerCase(); if (!used.has(s)) return s; }
  return (n[0] || "?") + (n[1] || "").toLowerCase();
}
function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

// ------------------------------------------------------------------ carga
async function loadAll() {
  [S.config, S.cats, S.items, S.grupos, S.practicas] = await Promise.all([
    api("/api/config"), api("/api/categorias"), api("/api/items"), api("/api/grupos"), api("/api/practicas"),
  ]);
  $("#brandName").textContent = S.config.instituto || "Instituto";
  $("#brandLogo").src = "/logo?t=" + Date.now();
  document.title = "Laboratorio FyQ · " + (S.config.instituto || "");
}

function go(view) {
  S.view = view;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  render();
  window.scrollTo(0, 0);
}
function render() { (VIEWS[S.view] || VIEWS.panel)(); }

// ------------------------------------------------------------------ PANEL
const VIEWS = {};
VIEWS.panel = () => {
  const rotos = S.items.filter((i) => i.rotos > 0);
  const bajo = S.items.filter((i) => i.minimo > 0 && i.cantidad < i.minimo);
  const agot = S.items.filter((i) => i.cantidad <= 0);
  $("#main").innerHTML = `
  <div class="hero">
    <img src="/logo?t=${Date.now()}" alt="">
    <div>
      <h1>${esc(S.config.instituto)}</h1>
      <p>${esc(S.config.departamento)} · ${esc(S.config.laboratorio)}</p>
    </div>
    <svg viewBox="0 0 200 200" aria-hidden="true"><g fill="none" stroke="#fff" stroke-width="5"><ellipse cx="100" cy="100" rx="90" ry="34"/><ellipse cx="100" cy="100" rx="90" ry="34" transform="rotate(60 100 100)"/><ellipse cx="100" cy="100" rx="90" ry="34" transform="rotate(120 100 100)"/></g><circle cx="100" cy="100" r="14" fill="#fff"/></svg>
  </div>
  <div class="grid g4" style="margin-bottom:18px">
    <div class="card stat"><span class="v">${S.items.length}</span><span class="l">Materiales en inventario</span></div>
    <div class="card stat ${rotos.length ? "alert" : ""}"><span class="v">${rotos.length}</span><span class="l">Con unidades rotas</span></div>
    <div class="card stat ${bajo.length + agot.length ? "alert" : ""}"><span class="v">${bajo.length + agot.length}</span><span class="l">Agotados o bajo mínimo</span></div>
    <div class="card stat"><span class="v">${S.practicas.length}</span><span class="l">Prácticas guardadas</span></div>
  </div>
  <div class="card">
    <div class="page-head" style="margin-bottom:12px"><div><h2>Categorías del laboratorio</h2><p class="sub" style="margin:0">Pulsa una categoría para ver su material</p></div>
    <div class="actions"><button class="btn" onclick="UI.itemForm()">＋ Añadir material</button><button class="btn primary" onclick="UI.nuevaPractica()">⚗ Nueva práctica</button></div></div>
    <div class="elements">
      ${S.cats.map((c, i) => `<div class="element" style="background:${esc(c.color)}" onclick="S.filtroCat=${c.id};go('inventario')">
        <span class="z">${i + 1}</span><span class="n">${c.n} art.</span>
        <span class="sym">${esc(catSym(c))}</span><span class="nm">${esc(c.nombre)}</span></div>`).join("")}
    </div>
  </div>
  <div class="grid g2">
    <div class="card">
      <h2>Avisos de stock</h2><p class="sub">Material roto, agotado o por debajo del mínimo</p>
      ${!rotos.length && !bajo.length && !agot.length ? `<div class="empty"><div class="big">✓</div>Todo en orden</div>` : `<table>
        ${agot.map((i) => `<tr><td>${esc(i.nombre)}</td><td class="num"><span class="badge bad">Agotado</span></td></tr>`).join("")}
        ${bajo.filter((i) => i.cantidad > 0).map((i) => `<tr><td>${esc(i.nombre)}</td><td class="num"><span class="badge warn">${qtxt(i.cantidad, i.unidad)} (mín. ${fmt(i.minimo)})</span></td></tr>`).join("")}
        ${rotos.map((i) => `<tr><td>${esc(i.nombre)}</td><td class="num"><span class="badge bad">${fmt(i.rotos)} roto${i.rotos > 1 ? "s" : ""}</span></td></tr>`).join("")}
      </table>`}
    </div>
    <div class="card">
      <h2>Últimas prácticas</h2><p class="sub">Resultado de la última comprobación</p>
      ${S.practicas.length ? `<table>${S.practicas.slice(0, 6).map((p) => `<tr style="cursor:pointer" onclick="UI.abrirPractica(${p.id})">
        <td><b>${esc(p.titulo)}</b><div class="small">${esc(p.ultima ? p.ultima.grupo + " · " + p.ultima.fecha : p.creado)}</div></td>
        <td class="num">${p.ultima ? (p.ultima.viable ? `<span class="badge ok">ES VIABLE</span>` : `<span class="badge bad">NO ES VIABLE</span>`) : `<span class="badge mute">Sin comprobar</span>`}</td></tr>`).join("")}</table>`
        : `<div class="empty"><div class="big">📄</div>Aún no hay prácticas.<br><br><button class="btn primary" onclick="UI.nuevaPractica()">Subir un guion</button></div>`}
    </div>
  </div>`;
};

// ------------------------------------------------------------------ INVENTARIO
VIEWS.inventario = () => {
  const q = S.buscar.toLowerCase();
  const cats = S.filtroCat ? S.cats.filter((c) => c.id === S.filtroCat) : S.cats;
  const sinCat = S.items.filter((i) => !i.categoria_id);
  let html = `
  <div class="page-head">
    <div><h1>Inventario del laboratorio</h1><p>Registra compras, descuenta material gastado y marca lo que se rompe.</p></div>
    <div class="actions">
      <input type="search" placeholder="Buscar material…" value="${esc(S.buscar)}" oninput="S.buscar=this.value;UI.refreshInv()" style="width:220px">
      <button class="btn" onclick="UI.catForm()">＋ Categoría</button>
      <button class="btn primary" onclick="UI.itemForm()">＋ Añadir material</button>
    </div>
  </div>
  <div class="seg" style="margin-bottom:6px">
    <button class="${!S.filtroCat ? "on" : ""}" onclick="S.filtroCat=null;render()">Todas</button>
    ${S.cats.map((c) => `<button class="${S.filtroCat === c.id ? "on" : ""}" onclick="S.filtroCat=${c.id};render()">${esc(c.nombre)}</button>`).join("")}
  </div>
  <div id="invBody"></div>`;
  $("#main").innerHTML = html;
  UI.refreshInv();
  if (!S.items.length) {
    $("#invBody").innerHTML = `<div class="card empty"><div class="big">🧪</div><p>El inventario está vacío.</p>
      <div class="actions" style="justify-content:center"><button class="btn primary" onclick="UI.itemForm()">Añadir el primer material</button>
      <button class="btn" onclick="UI.demo()">Cargar inventario de ejemplo</button></div></div>`;
  }
  void cats; void sinCat; void q;
};

const UI = {
  refreshInv() {
    const q = S.buscar.toLowerCase();
    const cats = S.filtroCat ? S.cats.filter((c) => c.id === S.filtroCat) : S.cats;
    const groups = cats.map((c) => ({ c, items: S.items.filter((i) => i.categoria_id === c.id && (!q || i.nombre.toLowerCase().includes(q))) }));
    if (!S.filtroCat) {
      const sin = S.items.filter((i) => !i.categoria_id && (!q || i.nombre.toLowerCase().includes(q)));
      if (sin.length) groups.push({ c: { id: 0, nombre: "SIN CATEGORÍA", color: "#94a3b8" }, items: sin });
    }
    const box = $("#invBody");
    if (!box || !S.items.length) return;
    box.innerHTML = groups.map(({ c, items }) => `
      <div class="cat-head"><div class="sym" style="background:${esc(c.color)}">${esc(c.id ? catSym(c) : "?")}</div>
        <div><h2>${esc(c.nombre)}</h2><span class="cnt">${items.length} artículo${items.length === 1 ? "" : "s"}${c.consumible ? " · se gasta al hacer prácticas" : ""}</span></div></div>
      <div class="card" style="padding:6px 10px">
        ${items.length ? `<div class="table-wrap"><table>
          <thead><tr><th>Material</th><th class="num">Disponible</th><th class="num">Rotos</th><th>Estado</th><th>Ubicación</th><th class="num">Acciones</th></tr></thead>
          <tbody>${items.map(UI.itemRow).join("")}</tbody></table></div>`
        : `<div class="empty" style="padding:16px">${q ? "Sin resultados" : "Sin material en esta categoría"}</div>`}
      </div>`).join("");
  },
  itemRow(i) {
    let estado;
    if (i.cantidad <= 0 && i.rotos > 0) estado = `<span class="badge bad">ROTO · no disponible</span>`;
    else if (i.cantidad <= 0) estado = `<span class="badge bad">Agotado</span>`;
    else if (i.minimo > 0 && i.cantidad < i.minimo) estado = `<span class="badge warn">Bajo mínimo (${fmt(i.minimo)})</span>`;
    else estado = `<span class="badge ok">Disponible</span>`;
    return `<tr class="${i.rotos > 0 ? "broken" : ""}">
      <td><b>${esc(i.nombre)}</b>${i.notas ? `<div class="small">${esc(i.notas)}</div>` : ""}</td>
      <td class="num"><span class="qty">${fmt(i.cantidad)}</span> <span class="small">${esc(i.unidad)}</span></td>
      <td class="num">${i.rotos > 0 ? `<a href="#" onclick="UI.rotosForm(${i.id});return false" class="badge bad">${fmt(i.rotos)}</a>` : `<span class="small">—</span>`}</td>
      <td>${estado}</td>
      <td class="small">${esc(i.ubicacion || "")}</td>
      <td class="num" style="white-space:nowrap">
        <button class="btn sm" title="Registrar compra / entrada" onclick="UI.movForm(${i.id},'entrada')">＋ Entrada</button>
        <button class="btn sm" title="Descontar material gastado o perdido" onclick="UI.movForm(${i.id},'baja')">－ Descontar</button>
        <button class="btn sm danger" title="Marcar unidades rotas (dejan de estar disponibles)" onclick="UI.movForm(${i.id},'rotura')">⚠ Roto</button>
        <button class="iconbtn" title="Editar" onclick="UI.itemForm(${i.id})">✎</button>
      </td></tr>`;
  },

  // -------------------------------------------------------------- modales
  openModal(html) { $("#modalBody").innerHTML = html; $("#modal").classList.remove("hidden"); const f = $("#modalBody input,#modalBody select"); if (f) f.focus(); },
  closeModal() { $("#modal").classList.add("hidden"); },

  itemForm(id) {
    const it = id ? S.items.find((x) => x.id === id) : { nombre: "", categoria_id: S.filtroCat || (S.cats[0] && S.cats[0].id), unidad: "uds", cantidad: 0, minimo: 0, ubicacion: "", notas: "" };
    UI.openModal(`<h2>${id ? "Editar material" : "Añadir material"}</h2>
      <p class="sub">${id ? "Para compras, gastos o roturas usa mejor los botones de la tabla: quedan registrados en el historial." : "Da de alta un material o reactivo nuevo del laboratorio."}</p>
      <div class="form-grid">
        <label class="f full">Nombre<input type="text" id="fNombre" value="${esc(it.nombre)}" placeholder="p. ej. Vaso de precipitados 250 mL"></label>
        <label class="f">Categoría<select id="fCat">${S.cats.map((c) => `<option value="${c.id}" ${c.id === it.categoria_id ? "selected" : ""}>${esc(c.nombre)}</option>`).join("")}</select></label>
        <label class="f">Unidad<select id="fUni">${UNIDADES.map((u) => `<option ${u === it.unidad ? "selected" : ""}>${u}</option>`).join("")}</select></label>
        <label class="f">${id ? "Cantidad disponible" : "Cantidad inicial"}<input type="number" step="any" min="0" id="fCant" value="${fmt(it.cantidad).replace(",", ".")}"></label>
        <label class="f">Stock mínimo (aviso)<input type="number" step="any" min="0" id="fMin" value="${fmt(it.minimo).replace(",", ".")}"></label>
        ${id ? `<label class="f">Unidades rotas<input type="number" step="any" min="0" id="fRot" value="${fmt(it.rotos).replace(",", ".")}"></label>` : ""}
        <label class="f ${id ? "" : "full"}">Ubicación<input type="text" id="fUbi" value="${esc(it.ubicacion)}" placeholder="Armario 2, estante B"></label>
        <label class="f full">Notas<input type="text" id="fNot" value="${esc(it.notas)}"></label>
        ${id && it.alias ? `<div class="full small">La app también lo reconoce en los guiones como: <i>${esc(it.alias.split("|").join(", "))}</i></div>` : ""}
      </div>
      <div class="modal-foot">
        ${id ? `<button class="btn danger" style="margin-right:auto" onclick="UI.delItem(${id})">Eliminar</button>` : ""}
        <button class="btn" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn primary" onclick="UI.saveItem(${id || 0})">Guardar</button></div>`);
  },
  async saveItem(id) {
    const d = { nombre: $("#fNombre").value.trim(), categoria_id: +$("#fCat").value, unidad: $("#fUni").value, cantidad: $("#fCant").value,
      minimo: $("#fMin").value, ubicacion: $("#fUbi").value, notas: $("#fNot").value };
    if (!d.nombre) return toast("Escribe el nombre del material", true);
    if (id) { d.rotos = $("#fRot").value; const it = S.items.find((x) => x.id === id); d.alias = it.alias; }
    try {
      await api(id ? `/api/items/${id}` : "/api/items", { method: id ? "PUT" : "POST", json: d });
      UI.closeModal(); await loadAll(); render(); toast(id ? "Material actualizado" : "Material añadido al inventario");
    } catch (e) { toast(e.message, true); }
  },
  async delItem(id) {
    const it = S.items.find((x) => x.id === id);
    if (!confirm(`¿Eliminar «${it.nombre}» del inventario?`)) return;
    await api(`/api/items/${id}`, { method: "DELETE" }); UI.closeModal(); await loadAll(); render(); toast("Material eliminado");
  },
  movForm(id, tipo) {
    const it = S.items.find((x) => x.id === id);
    const T = {
      entrada: ["Registrar entrada / compra", "Suma unidades al stock (compra, donación, reposición).", "primary", "Añadir al stock"],
      baja: ["Descontar del stock", "Resta material gastado, perdido o retirado.", "navy", "Descontar"],
      rotura: ["Marcar como roto", "Las unidades rotas dejan de estar disponibles y no cuentan en el cálculo de viabilidad.", "danger", "Marcar como roto"],
    }[tipo];
    UI.openModal(`<h2>${T[0]}</h2><p class="sub"><b>${esc(it.nombre)}</b> · disponibles: ${qtxt(it.cantidad, it.unidad)}${it.rotos ? ` · rotos: ${fmt(it.rotos)}` : ""}<br>${T[1]}</p>
      <div class="form-grid">
        <label class="f">Cantidad (${esc(it.unidad)})<input type="number" step="any" min="0" id="mCant" value="${tipo === "rotura" ? 1 : ""}"></label>
        <label class="f">Nota (opcional)<input type="text" id="mNota" placeholder="${tipo === "entrada" ? "Proveedor, factura…" : "Motivo"}"></label>
      </div>
      <div class="modal-foot"><button class="btn" onclick="UI.closeModal()">Cancelar</button>
      <button class="btn ${T[2] === "danger" ? "danger" : T[2]}" onclick="UI.saveMov(${id},'${tipo}')">${T[3]}</button></div>`);
  },
  rotosForm(id) {
    const it = S.items.find((x) => x.id === id);
    UI.openModal(`<h2>Unidades rotas</h2><p class="sub"><b>${esc(it.nombre)}</b> tiene ${fmt(it.rotos)} unidad(es) marcadas como rotas (no disponibles).</p>
      <label class="f">Cantidad<input type="number" step="any" min="0" id="mCant" value="${fmt(it.rotos).replace(",", ".")}"></label>
      <input type="hidden" id="mNota" value="">
      <div class="modal-foot"><button class="btn" onclick="UI.closeModal()">Cancelar</button>
      <button class="btn danger" onclick="UI.saveMov(${id},'desechar')">Desechar (dar de baja)</button>
      <button class="btn primary" onclick="UI.saveMov(${id},'reparacion')">Reparado: vuelve a estar disponible</button></div>`);
  },
  async saveMov(id, tipo) {
    try {
      await api(`/api/items/${id}/movimiento`, { method: "POST", json: { tipo, cantidad: $("#mCant").value, nota: $("#mNota").value } });
      UI.closeModal(); await loadAll(); render();
      toast({ entrada: "Entrada registrada", baja: "Stock descontado", rotura: "Marcado como roto: ya no cuenta como disponible", reparacion: "Vuelve a estar disponible", desechar: "Unidades rotas desechadas" }[tipo]);
    } catch (e) { toast(e.message, true); }
  },
  catForm(id) {
    const c = id ? S.cats.find((x) => x.id === id) : { nombre: "", color: "#14b8a6", consumible: 0 };
    UI.openModal(`<h2>${id ? "Editar categoría" : "Nueva categoría"}</h2><p class="sub">Organiza el inventario como quieras.</p>
      <div class="form-grid"><label class="f">Nombre<input type="text" id="cNom" value="${esc(c.nombre)}" placeholder="p. ej. ELECTRICIDAD"></label>
      <label class="f">Color<input type="color" id="cCol" value="${esc(c.color)}" style="height:40px;width:100%;border:1px solid #d5dde6;border-radius:9px"></label>
      <label class="check full"><input type="checkbox" id="cCons" ${c.consumible ? "checked" : ""}> Material consumible (se descuenta al registrar una práctica realizada, como los reactivos)</label></div>
      <div class="modal-foot">${id ? `<button class="btn danger" style="margin-right:auto" onclick="UI.delCat(${id})">Eliminar</button>` : ""}
      <button class="btn" onclick="UI.closeModal()">Cancelar</button><button class="btn primary" onclick="UI.saveCat(${id || 0})">Guardar</button></div>`);
  },
  async saveCat(id) {
    const d = { nombre: $("#cNom").value, color: $("#cCol").value, consumible: $("#cCons").checked };
    if (!d.nombre.trim()) return toast("Escribe un nombre", true);
    try { await api(id ? `/api/categorias/${id}` : "/api/categorias", { method: id ? "PUT" : "POST", json: d }); UI.closeModal(); await loadAll(); render(); toast("Categoría guardada"); }
    catch (e) { toast(e.message, true); }
  },
  async delCat(id) {
    if (!confirm("¿Eliminar esta categoría?")) return;
    try { await api(`/api/categorias/${id}`, { method: "DELETE" }); UI.closeModal(); await loadAll(); render(); } catch (e) { toast(e.message, true); }
  },
  async demo() { await api("/api/demo", { method: "POST" }); await loadAll(); render(); toast("Inventario de ejemplo cargado. Ajusta las cantidades a tu laboratorio."); },

  // -------------------------------------------------------------- PRÁCTICAS
  nuevaPractica() {
    const g = S.grupos[0];
    S.P = { id: null, titulo: "", texto: "", pdf_file: "", pdf_nombre: "", materiales: [], ajustes: { grupo_id: g ? g.id : null, agrupamiento: g ? g.agrupamiento : 0 } };
    S.view = "practicas"; go("practicas");
  },
  async abrirPractica(id) {
    const p = await api(`/api/practicas/${id}`);
    const aj = p.ajustes || {};
    if (!aj.grupo_id && S.grupos[0]) aj.grupo_id = S.grupos[0].id;
    if (aj.agrupamiento == null) { const g = S.grupos.find((x) => x.id === aj.grupo_id); aj.agrupamiento = g ? g.agrupamiento : 0; }
    S.P = { id: p.id, titulo: p.titulo, texto: p.texto, pdf_file: p.pdf_file, pdf_nombre: p.pdf_nombre, materiales: p.materiales, ajustes: aj };
    go("practicas");
  },
  async analizar() {
    const f = $("#pdfFile").files[0];
    const txt = $("#pdfTexto").value;
    if (!f && !txt.trim()) return toast("Sube el PDF del guion o pega la lista de materiales", true);
    const fd = new FormData();
    if (f) fd.append("pdf", f);
    if (txt.trim()) fd.append("texto", txt);
    $("#btnAnalizar").disabled = true; $("#btnAnalizar").textContent = "Leyendo el guion…";
    try {
      const r = await api("/api/practicas/analizar", { method: "POST", body: fd });
      const keep = S.P ? S.P.ajustes : {};
      S.P = { id: null, titulo: r.titulo, texto: r.texto, pdf_file: r.pdf_file, pdf_nombre: r.pdf_nombre, materiales: r.materiales, ajustes: keep };
      render();
      toast(r.materiales.length ? `Detectados ${r.materiales.length} materiales. Revisa la asignación.` : "No se encontró la lista de materiales. Añádelos a mano.", !r.materiales.length);
    } catch (e) { toast(e.message, true); $("#btnAnalizar").disabled = false; $("#btnAnalizar").textContent = "Leer guion"; }
  },
  setMat(i, k, v) {
    const m = S.P.materiales[i];
    if (k === "cantidad") v = parseFloat(String(v).replace(",", ".")) || 0;
    if (k === "item_id") { v = v ? +v : null; m.manual = true; }
    if (k === "ignorar") v = !!v;
    m[k] = v;
    if (k === "nombre" && !m.manual) {
      api("/api/emparejar", { method: "POST", json: { nombre: v } }).then((r) => { m.item_id = r.item_id; m.confianza = r.confianza; UI.renderMats(); });
    }
    if (k === "ignorar" || k === "item_id") UI.renderMats();
  },
  addMat() { S.P.materiales.push({ nombre: "", texto: "", cantidad: 1, unidad: "uds", ambito: "grupo", item_id: null, ignorar: false, manual: false }); UI.renderMats(); },
  delMat(i) { S.P.materiales.splice(i, 1); UI.renderMats(); },
  itemOptions(sel) {
    let h = `<option value="">— No está en el stock —</option>`;
    S.cats.forEach((c) => {
      const its = S.items.filter((i) => i.categoria_id === c.id);
      if (its.length) h += `<optgroup label="${esc(c.nombre)}">${its.map((i) => `<option value="${i.id}" ${i.id === sel ? "selected" : ""}>${esc(i.nombre)} (${fmt(i.cantidad)} ${esc(i.unidad)})</option>`).join("")}</optgroup>`;
    });
    const sin = S.items.filter((i) => !i.categoria_id);
    if (sin.length) h += `<optgroup label="SIN CATEGORÍA">${sin.map((i) => `<option value="${i.id}" ${i.id === sel ? "selected" : ""}>${esc(i.nombre)}</option>`).join("")}</optgroup>`;
    return h;
  },
  renderMats() {
    const box = $("#matsBody");
    if (!box) return;
    const ms = S.P.materiales;
    if (!ms.length) { box.innerHTML = `<tr><td colspan="7" class="empty">Sin materiales. Pulsa «＋ Añadir línea».</td></tr>`; return; }
    box.innerHTML = ms.map((m, i) => {
      const c = m.item_id ? (m.manual || m.confianza >= .8 ? "h" : "m") : "l";
      const tip = m.item_id ? (m.manual ? "Asignado a mano" : `Coincidencia ${Math.round((m.confianza || 0) * 100)} %`) : "Sin asignar";
      return `<tr class="${m.ignorar ? "ign" : ""}">
        <td><span class="conf ${m.ignorar ? "" : c}" title="${tip}"></span></td>
        <td><input type="text" value="${esc(m.nombre)}" onchange="UI.setMat(${i},'nombre',this.value)">${m.texto && m.texto.toLowerCase() !== m.nombre.toLowerCase() ? `<div class="orig" title="${esc(m.texto)}">Guion: ${esc(m.texto)}</div>` : ""}</td>
        <td><input type="number" step="any" min="0" value="${fmt(m.cantidad).replace(",", ".")}" onchange="UI.setMat(${i},'cantidad',this.value)"></td>
        <td><select onchange="UI.setMat(${i},'unidad',this.value)">${UNIDADES.map((u) => `<option ${u === m.unidad ? "selected" : ""}>${u}</option>`).join("")}</select></td>
        <td><select onchange="UI.setMat(${i},'ambito',this.value)">${AMBITOS.map(([v, l]) => `<option value="${v}" ${v === m.ambito ? "selected" : ""}>${l}</option>`).join("")}</select></td>
        <td><select onchange="UI.setMat(${i},'item_id',this.value)" style="min-width:230px">${UI.itemOptions(m.item_id)}</select></td>
        <td style="white-space:nowrap"><label class="check" title="No tener en cuenta (agua del grifo, material del alumno…)"><input type="checkbox" ${m.ignorar ? "checked" : ""} onchange="UI.setMat(${i},'ignorar',this.checked)"> Ignorar</label>
          <button class="iconbtn" title="Quitar línea" onclick="UI.delMat(${i})">✕</button></td></tr>`;
    }).join("");
  },
  setAjuste(k, v) {
    S.P.ajustes[k] = v === "" ? null : +v;
    if (k === "grupo_id") { const g = S.grupos.find((x) => x.id === +v); if (g) S.P.ajustes.agrupamiento = g.agrupamiento; }
    UI.renderSetup();
  },
  renderSetup() {
    const box = $("#setupBox"); if (!box) return;
    const aj = S.P.ajustes;
    const g = S.grupos.find((x) => x.id === aj.grupo_id);
    const n = g ? (parseLista(g.lista).length || g.alumnos) : 0;
    const t = aj.agrupamiento | 0;
    box.innerHTML = `
      <div class="setup">
        <label class="f">Curso y grupo que hará la práctica
          <select onchange="UI.setAjuste('grupo_id',this.value)">${S.grupos.map((x) => `<option value="${x.id}" ${x.id === aj.grupo_id ? "selected" : ""}>${esc(x.curso)} ${esc(x.grupo)} — ${parseLista(x.lista).length || x.alumnos} alumnos</option>`).join("")}</select></label>
        <label class="f">Forma de trabajo
          <div class="seg">${AGRUP.map(([v, l]) => `<button class="${t === v ? "on" : ""}" onclick="UI.setAjuste('agrupamiento',${v})">${l}</button>`).join("")}</div></label>
        <button class="btn" onclick="go('grupos')">Gestionar grupos</button>
      </div>
      <p class="small" style="margin:10px 0 0">${g ? (t ? `${n} alumnos → <b>${describir(distribuir(n, t))}</b>.` : `${n} alumnos → la app elegirá parejas, tríos o grupos de 4 según mesas, sillas y material disponible.`) : "Crea primero un curso/grupo."}
      ${g && parseLista(g.lista).length ? " Con listado de alumnos ✓" : g ? " Sin listado de nombres (opcional)." : ""}</p>`;
  },
  payload() {
    return { titulo: S.P.titulo, materiales: S.P.materiales, grupo_id: S.P.ajustes.grupo_id, agrupamiento: S.P.ajustes.agrupamiento, practica_id: S.P.id };
  },
  async guardar(silencioso) {
    S.P.titulo = $("#pTitulo").value.trim() || "Práctica";
    const body = { titulo: S.P.titulo, texto: S.P.texto, pdf_file: S.P.pdf_file, pdf_nombre: S.P.pdf_nombre, materiales: S.P.materiales, ajustes: S.P.ajustes };
    if (S.P.id) await api(`/api/practicas/${S.P.id}`, { method: "PUT", json: body });
    else S.P.id = (await api("/api/practicas", { method: "POST", json: body })).id;
    S.P.materiales.forEach((m) => (m.manual = false));
    S.practicas = await api("/api/practicas"); S.items = await api("/api/items");
    if (!silencioso) { toast("Práctica guardada"); render(); }
  },
  async comprobar() {
    if (!S.P.materiales.filter((m) => !m.ignorar).length) return toast("No hay materiales que comprobar", true);
    if (!S.P.ajustes.grupo_id) return toast("Elige el curso/grupo", true);
    try {
      await UI.guardar(true);
      const r = await api("/api/viabilidad", { method: "POST", json: UI.payload() });
      S.lastRes = r; UI.showVerdict(r);
      S.practicas = await api("/api/practicas");
    } catch (e) { toast(e.message, true); }
  },
  showVerdict(r) {
    const ok = r.viable;
    const eq = r.equipos || [];
    const mesaDe = {}; (r.plano || []).forEach((gs, m) => gs.forEach((g) => (mesaDe[g] = m + 1)));
    const conNombres = (r.grupo && r.grupo.nombres && r.grupo.nombres.length);
    $("#verdict").innerHTML = `<div class="verdict-box">
      <div class="banner ${ok ? "ok" : "bad"}">
        <div class="mark">${ok ? "✔" : "✖"}</div>
        <div class="word">${ok ? "ES VIABLE" : "NO ES VIABLE"}</div>
        <div class="det">${esc(S.P.titulo)}<br>${esc((r.grupo.curso || "") + " " + (r.grupo.grupo || ""))} · ${r.alumnos} alumnos · ${esc(r.reparto_texto)}</div>
      </div>
      <div class="verdict-body">
        ${r.motivo_auto ? `<p class="small" style="margin:0 0 6px;color:#0f766e"><b>⚙ ${esc(r.motivo_auto)}</b></p>` : ""}
        ${ok ? `<p style="margin:0">Hay material y espacio suficientes para que <b>todos los alumnos</b> hagan la práctica.</p>` : `
          <h3 style="margin-top:6px">Qué falta</h3>
          ${r.faltas.length ? `<div class="miss"><table><thead><tr><th>Material</th><th class="num">Necesario</th><th class="num">Disponible</th><th>Falta</th></tr></thead><tbody>
            ${r.faltas.map((l) => `<tr><td><b>${esc(l.nombre)}</b>${l.rotos ? ` <span class="badge bad">${fmt(l.rotos)} roto${l.rotos > 1 ? "s" : ""}</span>` : ""}</td>
              <td class="num">${qtxt(l.necesario, l.unidad)}</td><td class="num">${qtxt(l.disponible, l.unidad)}</td>
              <td>${l.sin_stock ? `<span class="badge bad">No existe en el stock</span>` : `<span class="badge bad">Faltan ${qtxt(l.falta, l.unidad)}</span>`}</td></tr>`).join("")}
          </tbody></table></div>` : ""}
          ${r.espacio.map((e) => `<p style="color:var(--bad);margin:8px 0 0"><b>⚠ ${esc(e)}</b></p>`).join("")}
          <div class="alcance"><div class="n">${r.max_alumnos}/${r.alumnos}</div>
            <div>${r.max_alumnos ? `Con el stock actual alcanza para <b>${r.max_alumnos} alumnos</b> (${esc(r.reparto_max_texto)}).` : "Con el stock actual no alcanza para ningún grupo."}
            ${r.sugerencia ? `<br><b>Sugerencia:</b> ${esc(r.sugerencia)}` : ""}</div></div>`}
        <h3>Reparto de alumnos y puestos</h3>
        <div class="reparto">${r.reparto.map((s, i) => `<div class="puesto s${Math.min(s, 4)}"><b>${s === 1 ? "Puesto" : "Grupo"} ${i + 1} · ${nombreTam(s)}${mesaDe[i] ? " · Mesa " + mesaDe[i] : r.mesas ? " · <span style='color:var(--bad)'>sin mesa</span>" : ""}</b>${conNombres ? esc((eq[i] || []).join(", ")) : `${s} alumno${s > 1 ? "s" : ""}`}</div>`).join("")}</div>
        ${r.alternativas ? `<h3>Comparativa de agrupamientos</h3><div class="table-wrap"><table><thead><tr><th>Agrupamiento</th><th>Reparto</th><th>¿Viable?</th><th>Alumnos atendidos</th></tr></thead><tbody>
          ${r.alternativas.map((a) => `<tr style="${a.tam === r.agrupamiento ? "background:#f0fdfa;font-weight:600" : ""}"><td>${esc(a.nombre[0].toUpperCase() + a.nombre.slice(1))}${a.tam === r.agrupamiento ? " ◀" : ""}</td><td>${esc(a.reparto_texto)}</td>
          <td>${a.viable ? `<span class="badge ok">SÍ</span>` : `<span class="badge bad">NO</span>`}</td><td class="small">${a.max_alumnos} de ${r.alumnos}${a.viable ? "" : " · " + esc(a.motivo)}</td></tr>`).join("")}</tbody></table></div>` : ""}
        <h3>Recuento total de material</h3>
        <div class="table-wrap"><table><thead><tr><th>Material</th><th>Categoría</th><th class="num">Necesario</th><th class="num">En stock</th><th>Estado</th></tr></thead><tbody>
          ${r.lineas.map((l) => `<tr><td>${esc(l.nombre)}</td><td class="small">${esc(l.categoria)}</td><td class="num">${qtxt(l.necesario, l.unidad)}${l.margen ? "*" : ""}</td><td class="num">${qtxt(l.disponible, l.unidad)}</td>
            <td>${l.ok ? `<span class="badge ok">OK</span>` : `<span class="badge bad">Falta</span>`}</td></tr>`).join("")}
        </tbody></table></div>
        ${r.lineas.some((l) => l.margen) ? `<p class="small">* Incluye un ${fmt(r.margen)} % de margen de seguridad en reactivos.</p>` : ""}
        ${r.avisos.map((a) => `<p class="small" style="color:var(--warn)">⚠ ${esc(a)}</p>`).join("")}
        <div class="verdict-actions">
          <button class="btn" onclick="UI.closeVerdict()">Cerrar</button>
          ${ok ? `<button class="btn" onclick="UI.realizar()" title="Descuenta del stock los reactivos y consumibles usados">✓ Registrar práctica realizada</button>` : ""}
          <button class="btn" onclick="UI.exportar()">⇩ Exportar proyecto</button>
          <button class="btn primary big" onclick="UI.informe()">⇩ Descargar informe PDF</button>
        </div>
      </div></div>`;
    $("#verdict").classList.remove("hidden");
    $("#verdict").scrollTop = 0;
  },
  closeVerdict() { $("#verdict").classList.add("hidden"); render(); },
  async informe() {
    try {
      if (S.view === "practicas" && $("#pTitulo")) await UI.guardar(true);
      const b = await api("/api/informe", { method: "POST", json: UI.payload() });
      const g = S.grupos.find((x) => x.id === S.P.ajustes.grupo_id);
      const name = ("Informe_" + S.P.titulo + (g ? "_" + g.curso + "_" + g.grupo : "")).normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9_-]+/g, "_").slice(0, 80);
      download(b, name + ".pdf"); toast("Informe PDF descargado");
    } catch (e) { toast(e.message, true); }
  },
  async exportar(id) {
    try {
      if (!id) { if ($("#pTitulo")) await UI.guardar(true); id = S.P.id; }
      const r = await fetch(`/api/practicas/${id}/exportar`);
      const cd = r.headers.get("content-disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      download(await r.blob(), m ? m[1] : "Proyecto.labfyq");
      toast("Proyecto exportado (.labfyq). Guárdalo para retomarlo cuando quieras.");
    } catch (e) { toast(e.message, true); }
  },
  async importar(input) {
    const f = input.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("proyecto", f);
    try {
      const r = await api("/api/practicas/importar", { method: "POST", body: fd });
      await loadAll();
      let msg = "Proyecto importado";
      if (r.grupo_creado) msg += " · se ha creado su curso/grupo";
      if (r.no_encontrados.length) msg += ` · ${r.no_encontrados.length} material(es) no están en tu stock: revisa la asignación`;
      toast(msg, r.no_encontrados.length > 0);
      UI.abrirPractica(r.id);
    } catch (e) { toast(e.message, true); }
    input.value = "";
  },
  async realizar() {
    if (!confirm("¿Registrar la práctica como realizada?\n\nSe descontarán del stock los reactivos y materiales consumibles usados.")) return;
    try {
      const r = await api(`/api/practicas/${S.P.id}/realizar`, { method: "POST", json: UI.payload() });
      await loadAll();
      toast(r.descontado.length ? "Descontado: " + r.descontado.map((d) => `${d.nombre} ${qtxt(d.cantidad, d.unidad)}`).join(", ") : "No había material consumible que descontar");
      UI.closeVerdict();
    } catch (e) { toast(e.message, true); }
  },
  async borrarPractica(id) {
    if (!confirm("¿Eliminar esta práctica guardada?")) return;
    await api(`/api/practicas/${id}`, { method: "DELETE" });
    if (S.P && S.P.id === id) S.P = null;
    S.practicas = await api("/api/practicas"); render();
  },

  // -------------------------------------------------------------- GRUPOS
  grupoForm(id) {
    const g = id ? S.grupos.find((x) => x.id === id) : { curso: "", grupo: "", alumnos: 24, agrupamiento: 2, lista: "" };
    UI.openModal(`<h2>${id ? "Editar grupo" : "Nuevo curso / grupo"}</h2>
      <p class="sub">Si pegas el listado de alumnos, el número se calcula solo y los nombres aparecerán en el reparto y en el croquis del laboratorio.</p>
      <div class="form-grid">
        <label class="f">Curso<input type="text" id="gCur" value="${esc(g.curso)}" placeholder="3º ESO"></label>
        <label class="f">Grupo<input type="text" id="gGru" value="${esc(g.grupo)}" placeholder="A"></label>
        <label class="f">Nº de alumnos<input type="number" min="1" id="gNum" value="${g.alumnos}" oninput="UI.prevGrupo()"></label>
        <label class="f">Forma de trabajo habitual<select id="gAgr" onchange="UI.prevGrupo()">${AGRUP.map(([v, l]) => `<option value="${v}" ${v === g.agrupamiento ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="f full">Listado de alumnos (uno por línea; admite «Apellidos, Nombre»)
          <textarea id="gLista" rows="8" oninput="UI.prevGrupo()" placeholder="García López, Ana&#10;Pérez Ruiz, Luis&#10;…">${esc(g.lista || "")}</textarea></label>
        <div class="full" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <label class="btn sm" style="cursor:pointer">📄 Importar .txt / .csv<input type="file" accept=".txt,.csv,text/plain,text/csv" hidden onchange="UI.leerLista(this)"></label>
          <span id="gPrev" class="small"></span></div>
      </div>
      <div class="modal-foot">${id ? `<button class="btn danger" style="margin-right:auto" onclick="UI.delGrupo(${id})">Eliminar</button>` : ""}
      <button class="btn" onclick="UI.closeModal()">Cancelar</button><button class="btn primary" onclick="UI.saveGrupo(${id || 0})">Guardar</button></div>`);
    UI.prevGrupo();
  },
  leerLista(input) {
    const f = input.files[0]; if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      let t = String(rd.result);
      // CSV: toma la primera columna con texto, o une «apellidos;nombre»
      t = t.split(/\r?\n/).map((l) => { const c = l.split(/[;\t]/).map((x) => x.trim().replace(/^"|"$/g, "")).filter(Boolean); return c.length >= 2 && !/\d/.test(c[1]) ? c[0] + ", " + c[1] : (c[0] || ""); }).join("\n");
      $("#gLista").value = t; UI.prevGrupo();
    };
    rd.readAsText(f, "utf-8");
  },
  prevGrupo() {
    const l = parseLista($("#gLista").value);
    if (l.length) $("#gNum").value = l.length;
    const n = +$("#gNum").value, t = +$("#gAgr").value;
    $("#gPrev").innerHTML = `${l.length ? `<b>${l.length} alumnos</b> en la lista` : `${n} alumnos`}${t ? ` → ${describir(distribuir(n, t))}` : " → reparto automático según mesas y material"}`;
  },
  async saveGrupo(id) {
    const d = { curso: $("#gCur").value, grupo: $("#gGru").value, alumnos: $("#gNum").value, agrupamiento: $("#gAgr").value, lista: $("#gLista").value };
    await api(id ? `/api/grupos/${id}` : "/api/grupos", { method: id ? "PUT" : "POST", json: d });
    UI.closeModal(); S.grupos = await api("/api/grupos");
    if (S.P && !S.P.ajustes.grupo_id && S.grupos[0]) S.P.ajustes.grupo_id = S.grupos[0].id;
    render(); toast("Grupo guardado");
  },
  async delGrupo(id) {
    if (!confirm("¿Eliminar este grupo?")) return;
    await api(`/api/grupos/${id}`, { method: "DELETE" }); UI.closeModal(); S.grupos = await api("/api/grupos"); render();
  },

  // -------------------------------------------------------------- CONFIG
  async saveConfig() {
    const d = {};
    document.querySelectorAll("[data-cfg]").forEach((el) => (d[el.dataset.cfg] = el.value));
    S.config = await api("/api/config", { method: "PUT", json: d });
    await loadAll(); render(); toast("Configuración guardada");
  },
  async subirLogo(input) {
    const f = input.files[0]; if (!f) return;
    // se convierte en el navegador a JPEG (fondo blanco, máx. 400 px) para poder incluirlo en los PDF
    const jpg = await new Promise((ok, ko) => {
      const img = new Image();
      img.onload = () => {
        const k = Math.min(1, 400 / Math.max(img.width, img.height));
        const c = document.createElement("canvas");
        c.width = Math.max(1, Math.round(img.width * k)); c.height = Math.max(1, Math.round(img.height * k));
        const x = c.getContext("2d"); x.fillStyle = "#fff"; x.fillRect(0, 0, c.width, c.height); x.drawImage(img, 0, 0, c.width, c.height);
        c.toBlob((b) => (b ? ok(b) : ko(new Error("No se pudo convertir la imagen"))), "image/jpeg", 0.9);
        URL.revokeObjectURL(img.src);
      };
      img.onerror = () => ko(new Error("Formato de imagen no admitido"));
      img.src = URL.createObjectURL(f);
    }).catch((e) => { toast(e.message, true); return null; });
    if (!jpg) return;
    const fd = new FormData(); fd.append("logo", jpg, "logo.jpg");
    try { await api("/api/config/logo", { method: "POST", body: fd }); await loadAll(); render(); toast("Logo actualizado"); } catch (e) { toast(e.message, true); }
  },
  async quitarLogo() { await api("/api/config/logo", { method: "DELETE" }); await loadAll(); render(); },
};

VIEWS.practicas = () => {
  const P = S.P;
  const lista = `
    <div class="card pract-list">
      <div class="page-head" style="margin-bottom:6px"><div><h2>Prácticas guardadas</h2><p class="sub" style="margin:0">Ábrelas para volver a comprobarlas, o expórtalas como proyecto.</p></div>
      <label class="btn" style="cursor:pointer">⇪ Importar proyecto (.labfyq)<input type="file" accept=".labfyq,.zip" hidden onchange="UI.importar(this)"></label></div>
      ${S.practicas.length ? S.practicas.map((p) => `<div class="row">
        <div><div class="t">${esc(p.titulo)}</div><div class="small">${p.materiales.length} materiales · creada ${esc(p.creado)}${p.pdf_nombre ? " · " + esc(p.pdf_nombre) : ""}</div></div>
        <div class="actions">
          ${p.ultima ? (p.ultima.viable ? `<span class="badge ok">ES VIABLE · ${esc(p.ultima.grupo)}</span>` : `<span class="badge bad">NO ES VIABLE · ${esc(p.ultima.grupo)}</span>`) : `<span class="badge mute">Sin comprobar</span>`}
          ${p.pdf_file ? `<a class="btn sm" href="/api/practicas/${p.id}/pdf" target="_blank">Ver guion</a>` : ""}
          <button class="btn sm" onclick="UI.exportar(${p.id})">⇩ Exportar</button>
          <button class="btn sm navy" onclick="UI.abrirPractica(${p.id})">Abrir</button>
          <button class="iconbtn" title="Eliminar" onclick="UI.borrarPractica(${p.id})">🗑</button>
        </div></div>`).join("") : `<div class="empty">Todavía no hay prácticas guardadas.</div>`}
    </div>`;

  if (!P || (!P.id && !P.materiales.length && !P.titulo)) {
    if (!S.P) S.P = { id: null, titulo: "", texto: "", pdf_file: "", pdf_nombre: "", materiales: [], ajustes: { grupo_id: S.grupos[0] ? S.grupos[0].id : null, agrupamiento: S.grupos[0] ? S.grupos[0].agrupamiento : 0 } };
    $("#main").innerHTML = `
    <div class="page-head"><div><h1>Prácticas</h1><p>Sube el guion de la práctica: la app lee la lista de materiales, la asigna al stock y comprueba si es viable.</p></div></div>
    <div class="card">
      <h2>1 · Sube el guion de la práctica</h2><p class="sub">PDF con la lista de material y reactivos. Si el PDF es una imagen escaneada, pega la lista en el cuadro de texto.</p>
      <div class="grid g2">
        <label class="drop" id="drop">
          <div class="big">📄</div><b id="dropTxt">Arrastra aquí el PDF o pulsa para elegirlo</b><div class="small">Se guardará junto a la práctica</div>
          <input type="file" id="pdfFile" accept="application/pdf,.pdf" hidden onchange="document.getElementById('dropTxt').textContent=this.files[0]?this.files[0].name:'Arrastra aquí el PDF'">
        </label>
        <label class="f">O pega la lista de materiales (opcional)
          <textarea id="pdfTexto" rows="7" placeholder="Material:&#10;- 2 vasos de precipitados de 250 mL&#10;- Probeta de 100 mL&#10;- Sulfato de cobre: 20 g"></textarea></label>
      </div>
      <div class="actions" style="justify-content:flex-end;margin-top:14px">
        <button class="btn" onclick="S.P.titulo='Nueva práctica';UI.addMat();render()">Introducir a mano</button>
        <button class="btn primary big" id="btnAnalizar" onclick="UI.analizar()">Leer guion</button></div>
    </div>${lista}`;
    const drop = $("#drop");
    ["dragover", "dragenter"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((e) => drop.addEventListener(e, () => drop.classList.remove("over")));
    drop.addEventListener("drop", (ev) => { ev.preventDefault(); const f = ev.dataTransfer.files[0]; if (f) { const dt = new DataTransfer(); dt.items.add(f); $("#pdfFile").files = dt.files; $("#dropTxt").textContent = f.name; } });
    return;
  }

  $("#main").innerHTML = `
  <div class="page-head">
    <div><h1>${P.id ? "Práctica guardada" : "Nueva práctica"}</h1><p>Revisa el material detectado, elige el grupo y comprueba la viabilidad.</p></div>
    <div class="actions"><button class="btn" onclick="S.P=null;render()">← Otra práctica</button>
      ${P.id && P.pdf_file ? `<a class="btn" href="/api/practicas/${P.id}/pdf" target="_blank">Ver guion PDF</a>` : ""}</div>
  </div>
  <div class="card">
    <label class="f">Título de la práctica<input type="text" id="pTitulo" value="${esc(P.titulo)}" style="font-size:17px;font-weight:600" oninput="S.P.titulo=this.value"></label>
    ${P.pdf_nombre ? `<p class="small" style="margin:8px 0 0">Guion: ${esc(P.pdf_nombre)}</p>` : ""}
  </div>
  <div class="card">
    <h2>2 · Material de la práctica</h2>
    <p class="sub">Cantidades tal y como aparecen en el guion. «Por grupo» se multiplica por el nº de puestos de trabajo, «Por alumno» por el nº de alumnos y «Común» es una sola vez (mesa del profesor).
      <span class="conf h"></span> asignado &nbsp;<span class="conf m"></span> revisar &nbsp;<span class="conf l"></span> sin asignar</p>
    <div class="table-wrap"><table class="mat-table"><thead><tr><th></th><th>Material (guion)</th><th>Cantidad</th><th>Unidad</th><th>Se usa</th><th>Asignado al stock</th><th></th></tr></thead>
      <tbody id="matsBody"></tbody></table></div>
    <div class="actions" style="margin-top:10px"><button class="btn sm" onclick="UI.addMat()">＋ Añadir línea</button>
      <span class="small">Al asignar a mano un material, la app lo recordará para los próximos guiones.</span></div>
  </div>
  <div class="card">
    <h2>3 · Grupo y forma de trabajo</h2><p class="sub">Capacidad del laboratorio: ${esc(S.config.mesas)} mesas de ${esc(S.config.alumnos_por_mesa)} alumnos · ${esc(S.config.sillas)} sillas · máx. ${esc(S.config.capacidad)} alumnos <a href="#" onclick="go('config');return false">(cambiar)</a></p>
    <div id="setupBox"></div>
  </div>
  <div class="actions" style="justify-content:flex-end">
    <button class="btn" onclick="UI.guardar()">💾 Guardar práctica</button>
    <button class="btn" onclick="UI.exportar()">⇩ Exportar proyecto</button>
    <button class="btn" onclick="UI.informe()">⇩ Informe PDF</button>
    <button class="btn primary big" onclick="UI.comprobar()">⚗ Comprobar viabilidad</button>
  </div>
  <div style="height:22px"></div>${lista}`;
  UI.renderMats();
  UI.renderSetup();
};

VIEWS.grupos = () => {
  $("#main").innerHTML = `
  <div class="page-head"><div><h1>Cursos y grupos</h1><p>Número de alumnos, forma de trabajo habitual y listado de alumnos.</p></div>
    <div class="actions"><button class="btn primary" onclick="UI.grupoForm()">＋ Nuevo grupo</button></div></div>
  <div class="card">${S.grupos.length ? `<div class="table-wrap"><table><thead><tr><th>Curso</th><th>Grupo</th><th class="num">Alumnos</th><th>Forma de trabajo</th><th>Listado</th><th></th></tr></thead><tbody>
    ${S.grupos.map((g) => { const l = parseLista(g.lista); const n = l.length || g.alumnos; return `<tr>
      <td><b>${esc(g.curso)}</b></td><td>${esc(g.grupo)}</td><td class="num qty">${n}</td>
      <td>${esc((AGRUP.find((a) => a[0] === g.agrupamiento) || AGRUP[0])[1])}<div class="small">${g.agrupamiento ? describir(distribuir(n, g.agrupamiento)) : "según mesas y material"}</div></td>
      <td>${l.length ? `<span class="badge teal">${l.length} nombres</span>` : `<span class="badge mute">Sin listado</span>`}</td>
      <td class="num"><button class="btn sm" onclick="UI.grupoForm(${g.id})">Editar</button></td></tr>`; }).join("")}
  </tbody></table></div>` : `<div class="empty"><div class="big">👥</div>Crea el primer grupo.</div>`}</div>`;
};

VIEWS.historial = async () => {
  $("#main").innerHTML = `<div class="page-head"><div><h1>Historial de movimientos</h1><p>Altas, compras, gastos, roturas y prácticas realizadas.</p></div></div><div class="card" id="hist">Cargando…</div>`;
  const m = await api("/api/movimientos");
  const B = { alta: "teal", entrada: "ok", baja: "warn", rotura: "bad", reparacion: "ok", desechar: "bad", ajuste: "mute", practica: "warn", eliminado: "bad", importacion: "teal" };
  const N = { alta: "Alta", entrada: "Entrada", baja: "Descontado", rotura: "Roto", reparacion: "Reparado", desechar: "Desechado", ajuste: "Ajuste", practica: "Práctica", eliminado: "Eliminado", importacion: "Importado" };
  $("#hist").innerHTML = m.length ? `<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Tipo</th><th>Material</th><th class="num">Cantidad</th><th>Nota</th></tr></thead><tbody>
    ${m.map((x) => `<tr><td class="small">${esc(x.fecha)}</td><td><span class="badge ${B[x.tipo] || "mute"}">${N[x.tipo] || esc(x.tipo)}</span></td><td>${esc(x.item_nombre)}</td>
    <td class="num">${(x.tipo === "ajuste" && x.cantidad > 0 ? "+" : "") + fmt(x.cantidad)} ${esc(x.unidad || "")}</td><td class="small">${esc(x.nota || "")}</td></tr>`).join("")}</tbody></table></div>`
    : `<div class="empty">Sin movimientos todavía.</div>`;
};

VIEWS.config = () => {
  const c = S.config;
  const f = (k, label, type = "text", extra = "") => `<label class="f">${label}<input type="${type}" data-cfg="${k}" value="${esc(c[k] || "")}" ${extra}></label>`;
  $("#main").innerHTML = `
  <div class="page-head"><div><h1>Configuración</h1><p>Datos del centro, capacidad del laboratorio y categorías del inventario.</p></div>
    <div class="actions"><button class="btn primary" onclick="UI.saveConfig()">Guardar configuración</button></div></div>
  <div class="grid g2">
    <div class="card">
      <h2>Centro</h2><p class="sub">Aparece en la app y en los informes PDF.</p>
      <div style="display:flex;gap:18px;align-items:center;margin-bottom:16px">
        <img class="logo-prev" src="/logo?t=${Date.now()}" alt="Logo">
        <div class="actions" style="flex-direction:column;align-items:flex-start">
          <label class="btn primary" style="cursor:pointer">Subir logo del instituto<input type="file" accept="image/*" hidden onchange="UI.subirLogo(this)"></label>
          ${c.logo ? `<button class="btn sm" onclick="UI.quitarLogo()">Quitar logo</button>` : `<span class="small">PNG o JPG, preferiblemente cuadrado</span>`}
        </div>
      </div>
      <div class="grid" style="gap:12px">${f("instituto", "Nombre del instituto")}${f("departamento", "Departamento")}${f("laboratorio", "Nombre del laboratorio")}</div>
    </div>
    <div class="card">
      <h2>Capacidad del laboratorio</h2><p class="sub">Se usa para decidir el reparto de alumnos y comprobar si caben.</p>
      <div class="form-grid">
        ${f("capacidad", "Capacidad máxima (alumnos)", "number", 'min="0"')}
        ${f("sillas", "Sillas / taburetes", "number", 'min="0"')}
        ${f("mesas", "Mesas de trabajo", "number", 'min="0"')}
        ${f("alumnos_por_mesa", "Alumnos por mesa", "number", 'min="1"')}
        ${f("mesas_por_fila", "Mesas por fila (croquis)", "number", 'min="1"')}
        ${f("margen", "Margen de seguridad en reactivos (%)", "number", 'min="0" step="any"')}
      </div>
      <p class="small" style="margin-top:12px">Ejemplo: 8 mesas de 4 alumnos = 32 puestos → 16 parejas, o 8 grupos de 4.</p>
    </div>
  </div>
  <div class="card">
    <div class="page-head" style="margin-bottom:8px"><div><h2>Categorías del inventario</h2><p class="sub" style="margin:0">Puedes añadir las que necesites.</p></div>
    <button class="btn" onclick="UI.catForm()">＋ Nueva categoría</button></div>
    <table><thead><tr><th></th><th>Nombre</th><th class="num">Materiales</th><th>Consumible</th><th></th></tr></thead><tbody>
    ${S.cats.map((x) => `<tr><td style="width:56px"><div class="cat-head" style="margin:0"><div class="sym" style="background:${esc(x.color)};width:36px;height:36px;font-size:14px">${esc(catSym(x))}</div></div></td>
      <td><b>${esc(x.nombre)}</b></td><td class="num">${x.n}</td><td>${x.consumible ? `<span class="badge warn">Se gasta</span>` : `<span class="badge mute">Reutilizable</span>`}</td>
      <td class="num"><button class="btn sm" onclick="UI.catForm(${x.id})">Editar</button></td></tr>`).join("")}
    </tbody></table>
  </div>`;
};

// ------------------------------------------------------------------ COPIA DEL STOCK
const COPIA = { file: null, resumen: null, modo: "fusionar" };
VIEWS.copia = () => {
  const ult = (S.config.ultima_importacion_stock || "").split("|");
  const totalU = S.items.reduce((a, i) => a + (i.unidad === "uds" ? i.cantidad : 0), 0);
  $("#main").innerHTML = `
  <div class="page-head"><div><h1>Exportar / importar stock</h1>
    <p>Lleva el inventario de un ordenador a otro. La copia guarda el stock tal y como está en el momento de exportarlo.</p></div></div>
  <div class="grid g2">
    <div class="card">
      <h2>⇩ Exportar stock</h2>
      <p class="sub">Descarga un archivo con todo el inventario actualizado a hoy: categorías, cantidades disponibles, unidades rotas, mínimos, ubicaciones y notas.</p>
      <div class="grid g3" style="margin-bottom:16px">
        <div class="stat"><span class="v">${S.items.length}</span><span class="l">materiales</span></div>
        <div class="stat"><span class="v">${S.cats.length}</span><span class="l">categorías</span></div>
        <div class="stat"><span class="v">${fmt(totalU)}</span><span class="l">unidades en total</span></div>
      </div>
      <p class="small">El nombre del archivo incluye la fecha y la hora de la exportación, por ejemplo:<br>
        <code>${esc(UI.nombreCopia())}</code></p>
      <button class="btn primary big" onclick="UI.exportarStock()" ${S.items.length ? "" : "disabled"}>⇩ Exportar stock ahora</button>
    </div>
    <div class="card">
      <h2>⇪ Importar stock</h2>
      <p class="sub">Elige un archivo de stock exportado desde esta app en otro ordenador. Antes de aplicar nada verás un resumen de los cambios.</p>
      <label class="drop" style="display:block;padding:20px">
        <div class="big">📦</div><b id="copiaNombre">${COPIA.file ? esc(COPIA.file.name) : "Pulsa para elegir el archivo Stock_…json"}</b>
        <input type="file" accept=".json,application/json" hidden onchange="UI.elegirStock(this)">
      </label>
      <div id="copiaPrev" style="margin-top:14px"></div>
      ${ult[0] ? `<p class="small" style="margin-top:14px">Última importación en este ordenador: ${esc(ult[0])} (copia exportada el ${esc(ult[1] || "?")}).</p>` : ""}
    </div>
  </div>`;
  UI.renderCopia();
};
Object.assign(UI, {
  nombreCopia() {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    const inst = (S.config.instituto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9_-]+/g, "_").slice(0, 30).replace(/^_|_$/g, "");
    return `Stock_${inst ? inst + "_" : ""}${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}.json`;
  },
  async exportarStock() {
    try {
      const r = await fetch("/api/stock/exportar");
      const m = (r.headers.get("content-disposition") || "").match(/filename="([^"]+)"/);
      download(await r.blob(), m ? m[1] : UI.nombreCopia());
      toast("Stock exportado: " + (m ? m[1] : ""));
    } catch (e) { toast(e.message, true); }
  },
  async elegirStock(input) {
    COPIA.file = input.files[0] || null; COPIA.resumen = null;
    $("#copiaNombre").textContent = COPIA.file ? COPIA.file.name : "Pulsa para elegir el archivo";
    await UI.simularStock();
  },
  async simularStock() {
    if (!COPIA.file) return UI.renderCopia();
    const fd = new FormData(); fd.append("stock", COPIA.file); fd.append("modo", COPIA.modo); fd.append("simular", "1");
    try { COPIA.resumen = await api("/api/stock/importar", { method: "POST", body: fd }); }
    catch (e) { COPIA.resumen = null; COPIA.file = null; toast(e.message, true); $("#copiaNombre").textContent = "Pulsa para elegir el archivo"; }
    UI.renderCopia();
  },
  setModoCopia(m) { COPIA.modo = m; UI.simularStock(); },
  renderCopia() {
    const box = $("#copiaPrev"); if (!box) return;
    const r = COPIA.resumen;
    if (!r) { box.innerHTML = ""; return; }
    const fNombre = (COPIA.file.name.match(/(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})(?:-(\d{2}))?/) || []);
    box.innerHTML = `
      <div class="alcance" style="background:#f0fdfa;border-color:#5eead4;margin-top:0">
        <div class="n" style="color:#0f766e;font-size:28px">📅</div>
        <div>Copia exportada el <b>${esc(r.fecha_exportacion || "?")}</b>${r.instituto ? " · " + esc(r.instituto) : ""}<br>
        <span class="small">${r.total} materiales en la copia${fNombre[1] ? ` · fecha en el nombre del archivo: ${fNombre[1]} ${fNombre[2]}:${fNombre[3]}` : ""}</span></div></div>
      <label class="f" style="margin-top:14px">¿Cómo importar?
        <div class="seg">
          <button class="${COPIA.modo === "fusionar" ? "on" : ""}" onclick="UI.setModoCopia('fusionar')">Actualizar y añadir</button>
          <button class="${COPIA.modo === "reemplazar" ? "on" : ""}" onclick="UI.setModoCopia('reemplazar')">Reemplazar todo el stock</button>
        </div></label>
      <p class="small">${COPIA.modo === "fusionar" ? "Los materiales de la copia actualizan sus cantidades aquí y se añaden los que falten. Lo que solo existe en este ordenador se conserva."
        : "El stock de este ordenador quedará exactamente igual que el de la copia: se borra lo que no esté en ella."}</p>
      <table style="margin-top:6px"><tbody>
        <tr><td>Materiales nuevos que se añadirán</td><td class="num"><span class="badge ok">${r.nuevos}</span></td></tr>
        <tr><td>Materiales con cantidades distintas que se actualizarán</td><td class="num"><span class="badge warn">${r.actualizados}</span></td></tr>
        <tr><td>Materiales sin cambios</td><td class="num"><span class="badge mute">${r.iguales}</span></td></tr>
        ${COPIA.modo === "reemplazar" ? `<tr><td>Materiales que se eliminarán${r.lista_eliminados.length ? `<div class="small">${esc(r.lista_eliminados.join(", "))}</div>` : ""}</td><td class="num"><span class="badge bad">${r.eliminados}</span></td></tr>` : ""}
      </tbody></table>
      ${r.cambios.length ? `<details style="margin-top:10px"><summary class="small" style="cursor:pointer">Ver cambios de cantidad</summary><table><tbody>
        ${r.cambios.map((c) => `<tr><td>${esc(c.nombre)}</td><td class="num small">${fmt(c.antes)} → <b>${fmt(c.despues)}</b> ${esc(c.unidad || "")}</td></tr>`).join("")}</tbody></table></details>` : ""}
      <div class="actions" style="justify-content:flex-end;margin-top:14px">
        <button class="btn" onclick="COPIA.file=null;COPIA.resumen=null;render()">Cancelar</button>
        <button class="btn primary" onclick="UI.importarStock()">⇪ Importar stock</button></div>`;
  },
  async importarStock() {
    const r = COPIA.resumen;
    if (COPIA.modo === "reemplazar" && !confirm(`Se reemplazará todo el stock por la copia del ${r.fecha_exportacion}.${r.eliminados ? `\nSe eliminarán ${r.eliminados} materiales que no están en la copia.` : ""}\n\n¿Continuar?`)) return;
    const fd = new FormData(); fd.append("stock", COPIA.file); fd.append("modo", COPIA.modo);
    try {
      const x = await api("/api/stock/importar", { method: "POST", body: fd });
      COPIA.file = null; COPIA.resumen = null;
      await loadAll(); render();
      toast(`Stock importado (copia del ${x.fecha_exportacion}): ${x.nuevos} nuevos, ${x.actualizados} actualizados${x.eliminados ? ", " + x.eliminados + " eliminados" : ""}`);
    } catch (e) { toast(e.message, true); }
  },
});

// ------------------------------------------------------------------ arranque
document.querySelectorAll("#nav a").forEach((a) => a.addEventListener("click", () => go(a.dataset.view)));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { UI.closeModal(); if (!$("#verdict").classList.contains("hidden")) UI.closeVerdict(); } });
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") UI.closeModal(); });
window.UI = UI; window.S = S; window.go = go; window.render = render;
async function fromHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  let m;
  if ((m = h.match(/^(practica|viabilidad)-(\d+)$/))) {
    await UI.abrirPractica(+m[2]);
    if (m[1] === "viabilidad") await UI.comprobar();
  } else if ((m = h.match(/^grupo-(\d+)$/))) { go("grupos"); UI.grupoForm(+m[1]); }
  else go(VIEWS[h] ? h : "panel");
}
window.addEventListener("hashchange", fromHash);
loadAll().then(fromHash).catch((e) => { $("#main").innerHTML = `<div class="card empty">No se pudo conectar con el servidor: ${esc(e.message)}</div>`; });
