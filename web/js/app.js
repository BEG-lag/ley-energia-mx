/* ley·energía: búsqueda y lectura de la regulación energética. Sin dependencias ni terceros.
 *
 * Dos modos:
 *  - híbrido: si la página la sirve `ley-energia serve`, usa /api/buscar (léxica + vectorial).
 *  - navegador: en GitHub Pages, BM25 sobre datos/indice.json con las mismas raíces Snowball
 *    que el índice SQLite (el mapa palabra a raíz viene precalculado).
 * Nada de innerHTML con datos: todo se arma con nodos de texto.
 */
"use strict";

(() => {
  const M = globalThis.LeyMotor;
  const { normalizar, nombreCorto, citar, raicesConsulta } = M;

  const $ = (sel) => document.querySelector(sel);
  const estado = { catalogo: null, docs: {}, indice: null, hibrido: false, ultimos: [], consulta: "" };

  // ------------------------------------------------------------------ utilidades

  function el(tag, attrs = {}, ...hijos) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const h of hijos.flat()) if (h !== null && h !== undefined) n.append(h);
    return n;
  }

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, 2600);
  }

  function fechaLarga(iso) {
    if (!iso) return "";
    const [a, m, d] = iso.split("-").map(Number);
    const meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
    return `${d} ${meses[m - 1]} ${a}`;
  }

  function chipVigencia(doc) {
    if (doc.abrogada_desde) return el("span", { class: "chip abrogado", text: `abrogado desde ${fechaLarga(doc.abrogada_desde)}` });
    if (doc.nota_vigencia) return el("span", { class: "chip nota", text: "vigente, con nota", title: doc.nota_vigencia });
    return el("span", { class: "chip vigente", text: "vigente" });
  }

  // ------------------------------------------------------------------ datos

  async function json(url) {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
  }

  async function cargarIndice() {
    if (!estado.indice) {
      estado.indice = json("datos/indice.json").then(M.prepararIndice);
    }
    return estado.indice;
  }

  async function cargarDoc(id) {
    if (!estado.docs[id]) estado.docs[id] = json(`datos/docs/${encodeURIComponent(id)}.json`);
    return estado.docs[id];
  }

  // ------------------------------------------------------------------ búsqueda

  async function buscarLocal(q, filtros, k = 12) {
    const ix = await cargarIndice();
    estado.motor = estado.motor || M.crearMotor(estado.catalogo);
    return estado.motor.buscar(q, filtros, k, ix);
  }

  async function buscarHibrido(q, filtros, k = 12) {
    const p = new URLSearchParams({ q, k: String(k) });
    if (filtros.tipo) p.set("tipo", filtros.tipo);
    if (filtros.abrogados) p.set("abrogados", "true");
    if (filtros.fecha) p.set("fecha", filtros.fecha);
    const r = await json(`api/buscar?${p}`);
    const docs = Object.fromEntries(estado.catalogo.documentos.map((d) => [d.id, d]));
    return r.resultados.map((x) => ({
      doc: docs[x.documento_id], clave: x.clave, etiqueta: x.etiqueta, ruta: x.ruta,
      texto: x.texto, cita: x.cita, parcial: false,
    }));
  }

  // ------------------------------------------------------------------ resultados

  function resaltar(texto, q) {
    // Con el índice cargado compara raíces exactas; sin él (modo híbrido), prefijos de 5 letras.
    const ix = estado.indiceListo;
    const vacias = ix ? ix.vaciasSet : new Set();
    const raices = ix ? raicesConsulta(q, ix)
      : (normalizar(q).match(/[a-z0-9ñ]+/g) || []).filter((w) => w.length > 3).map((w) => w.slice(0, 5));
    const frag = document.createDocumentFragment();
    if (!raices.length) { frag.append(texto); return frag; }
    for (const parte of texto.split(/([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+)/)) {
      const n = normalizar(parte);
      const r = ix ? (ix.palabras[n] || n) : n.slice(0, 5);
      if (parte && n.length > 2 && !vacias.has(n) && raices.includes(r)) frag.append(el("mark", { text: parte }));
      else frag.append(parte);
    }
    return frag;
  }

  function pintarResultados(res, q) {
    const lista = $("#res-lista");
    lista.replaceChildren();
    $("#resultados").hidden = false;
    $("#res-resumen").textContent = res.length ? `${res.length} resultados para "${q}"` : "";
    if (!res.length) {
      lista.append(el("li", { class: "vacio", text: "Sin resultados. Prueba con otras palabras, incluye abrogados o quita la fecha." }));
      return;
    }
    res.forEach((r) => {
      const extracto = r.texto.length > 420 ? `${r.texto.slice(0, 420).replace(/\s+\S*$/, "")} …` : r.texto;
      lista.append(el("li", { class: "res" },
        el("div", { class: "res-cab" },
          el("span", { class: "cita", text: r.cita }),
          chipVigencia(r.doc),
          el("span", { class: "chip plain", text: r.doc.tipo === "dacg" ? "DACG" : r.doc.tipo })),
        el("div", { class: "doc", text: r.doc.titulo }),
        r.ruta && r.ruta.length ? el("div", { class: "ruta", text: r.ruta.join(" › ") }) : null,
        el("p", { class: "extracto" }, resaltar(extracto, q)),
        el("div", { class: "acciones" },
          el("button", { type: "button", text: "Leer completo", onclick: () => abrirLector(r.doc.id, r.clave) }),
          el("a", { href: r.doc.url_oficial, rel: "noopener", target: "_blank", text: "Fuente oficial ↗" }),
          r.doc.sustituido_por ? el("button", { type: "button", text: "Ver la norma vigente", onclick: () => abrirLector(r.doc.sustituido_por) }) : null)));
    });
  }

  function filtrosActuales() {
    return { tipo: $("#tipo").value || null, abrogados: $("#abrogados").checked, fecha: $("#fecha").value || null };
  }

  async function buscar(q) {
    q = q.trim();
    if (!q) return;
    estado.consulta = q;
    const filtros = filtrosActuales();
    $("#res-resumen").textContent = "Buscando…";
    $("#resultados").hidden = false;
    try {
      if (!estado.hibrido) estado.indiceListo = await cargarIndice();
      const res = estado.hibrido ? await buscarHibrido(q, filtros) : await buscarLocal(q, filtros);
      estado.ultimos = res;
      pintarResultados(res, q);
      history.replaceState(null, "", `#q=${encodeURIComponent(q)}`);
      $("#resultados").scrollIntoView({ block: "start" });
    } catch (e) {
      $("#res-resumen").textContent = "No se pudo buscar. Revisa la conexión e intenta de nuevo.";
      console.error(e);
    }
  }

  async function copiarParaClaude() {
    if (!estado.ultimos.length) return;
    const top = estado.ultimos.slice(0, 6);
    const bloques = [];
    for (const [i, r] of top.entries()) {
      let texto = r.texto;
      if (r.parcial) {
        try {
          const d = await cargarDoc(r.doc.id);
          const partes = d.fragmentos.filter((f) => f.c === r.clave && (r.clave || f.e === r.etiqueta));
          if (partes.length) texto = partes.map((f) => f.t).join("\n\n");
        } catch { /* se queda el extracto */ }
      }
      const vig = r.doc.abrogada_desde ? `abrogado desde ${r.doc.abrogada_desde}` : "vigente";
      bloques.push(`[${i + 1}] ${r.cita.replace(/ \(parte \d+ de \d+\)$/, "")} (${r.doc.titulo}; ${vig})\nFuente: ${r.doc.url_oficial}\n${texto.slice(0, 6000)}`);
    }
    const corte = estado.catalogo.meta.corte;
    const prompt = [
      `Pregunta: ${estado.consulta}`,
      "",
      `Responde sólo con base en estos fragmentos de la regulación energética mexicana (ley-energia-mx, corte ${corte}). Cita cada afirmación como [n] con documento y artículo. Si los fragmentos no alcanzan para responder, dilo. Señala si algo está abrogado. Termina recordando que no es opinión legal y que la versión con validez es la del DOF.`,
      "",
      ...bloques,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(prompt);
      toast("Copiado. Pégalo en Claude.");
    } catch {
      toast("Tu navegador no dejó copiar.");
    }
  }

  // ------------------------------------------------------------------ lector

  let ultimoFoco = null;
  async function abrirLector(id, clave = null) {
    const meta = estado.catalogo.documentos.find((d) => d.id === id);
    if (!meta) return;
    ultimoFoco = document.activeElement;
    const lector = $("#lector");
    $("#lector-titulo").textContent = meta.titulo;
    $("#lector-meta").replaceChildren(...[
      chipVigencia(meta),
      el("span", { text: `${meta.emisor} · DOF ${fechaLarga(meta.fecha_pub)}` }),
      meta.nota_vigencia ? el("span", { text: meta.nota_vigencia }) : null,
      meta.sustituido_por ? el("span", { text: `Sustituido por ${nombreCorto(estado.catalogo.documentos.find((d) => d.id === meta.sustituido_por))}` }) : null,
      el("a", { href: meta.url_oficial, rel: "noopener", target: "_blank", text: "Fuente oficial ↗" }),
    ].filter(Boolean));
    const texto = $("#lector-texto");
    const indice = $("#lector-indice");
    texto.replaceChildren(el("p", { class: "cargando", text: "Cargando…" }));
    indice.replaceChildren();
    lector.hidden = false;
    document.body.style.overflow = "hidden";
    $("#cerrar").focus();
    const d = await cargarDoc(id);
    const nodos = [];
    const vistos = new Set();
    let destino = null;
    d.fragmentos.forEach((f, i) => {
      const ancla = `u-${i}`;
      const base = f.e.replace(/ \(parte \d+ de \d+\)$/, "");
      const unidad = el("article", { class: "unidad", id: ancla },
        el("h3", { text: f.e }),
        f.r && f.r.length ? el("div", { class: "ruta", text: f.r.join(" › ") }) : null,
        ...f.t.split(/\n{1,}/).map((p) => el("p", { text: p })));
      if (clave && f.c === clave && !destino) { destino = unidad; unidad.classList.add("destacada"); }
      nodos.push(unidad);
      if (!vistos.has(base)) {
        vistos.add(base);
        const enlace = el("a", { href: `#${ancla}`, text: base, onclick: (ev) => { ev.preventDefault(); unidad.scrollIntoView({ block: "start" }); } });
        if (unidad === destino) enlace.classList.add("activo");
        indice.append(enlace);
      }
    });
    texto.replaceChildren(...nodos);
    if (destino) {
      destino.scrollIntoView({ block: "start" });
      const activo = indice.querySelector("a.activo");
      if (activo) activo.scrollIntoView({ block: "center" });
    }
    else texto.scrollTop = 0;
  }

  function cerrarLector() {
    $("#lector").hidden = true;
    document.body.style.overflow = "";
    if (ultimoFoco) ultimoFoco.focus();
  }

  // ------------------------------------------------------------------ catálogo y linaje

  function pintarCatalogo(filtro = "todos") {
    const grid = $("#grid");
    const docs = estado.catalogo.documentos.filter((d) =>
      filtro === "todos" ? true : filtro === "abrogados" ? !!d.abrogada_desde : d.tipo === filtro && !d.abrogada_desde);
    grid.replaceChildren(...docs.map((d) => el("article", { class: "tarjeta" },
      el("div", { class: "res-cab" }, chipVigencia(d), el("span", { class: "chip plain", text: d.tipo === "dacg" ? "DACG" : d.tipo })),
      el("h3", { text: d.titulo }),
      el("div", { class: "meta" },
        el("span", { text: d.abreviatura || "" }),
        el("span", { text: d.emisor }),
        el("span", { text: `DOF ${fechaLarga(d.fecha_pub)}` }),
        el("span", { text: `${d.articulos || d.fragmentos} ${d.tipo === "dacg" && !d.abreviatura ? "unidades" : "artículos"}` })),
      el("button", { class: "leer", type: "button", text: "Leer →", onclick: () => abrirLector(d.id) }))));
  }

  function pintarLinaje() {
    const docs = Object.fromEntries(estado.catalogo.documentos.map((d) => [d.id, d]));
    const pares = estado.catalogo.documentos.filter((d) => d.sustituido_por)
      .sort((a, b) => a.abrogada_desde.localeCompare(b.abrogada_desde) || a.titulo.localeCompare(b.titulo));
    $("#lista-linaje").replaceChildren(...pares.map((d) => {
      const n = docs[d.sustituido_por];
      return el("li", {},
        el("div", { class: "de" }, el("strong", { text: d.titulo }), el("span", { class: "small", text: `${nombreCorto(d)} · DOF ${fechaLarga(d.fecha_pub)}` })),
        el("div", { class: "flecha", text: `→ desde ${fechaLarga(d.abrogada_desde)}` }),
        el("div", { class: "a" }, el("strong", { text: n.titulo }), el("span", { class: "small", text: `${nombreCorto(n)} · ${d.base || ""}` })));
    }));
  }

  function pintarStats() {
    const c = estado.catalogo;
    const docs = c.documentos;
    const valores = {
      documentos: docs.length,
      articulos: docs.reduce((a, d) => a + (d.articulos || 0), 0).toLocaleString("es-MX"),
      dacg: docs.filter((d) => d.tipo === "dacg" && !d.abrogada_desde).length,
      linaje: docs.filter((d) => d.sustituido_por).length,
    };
    for (const [k, v] of Object.entries(valores)) { const n = document.querySelector(`[data-stat="${k}"]`); if (n) n.textContent = v; }
    $("#corte").textContent = `· corte ${fechaLarga(c.meta.corte)}`;
    const ev = c.meta.evaluacion;
    if (ev) for (const [k, v] of Object.entries(ev)) { const n = document.querySelector(`[data-eval="${k}"]`); if (n) n.textContent = v; }
  }

  // ------------------------------------------------------------------ arranque

  async function iniciar() {
    try {
      estado.catalogo = await json("datos/catalogo.json");
    } catch (e) {
      $("#grid").replaceChildren(el("p", { class: "vacio", text: "No se pudo cargar el catálogo." }));
      return;
    }
    pintarStats();
    pintarCatalogo();
    pintarLinaje();
    // La API sólo existe cuando sirve `ley-energia serve` (localhost); en Pages no se pregunta.
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
    if (local) try {
      const r = await fetch("api/estado");
      if (r.ok && (r.headers.get("content-type") || "").includes("json")) {
        estado.hibrido = true;
        const m = $("#modo");
        m.textContent = "búsqueda híbrida local";
        m.classList.add("hibrido");
      }
    } catch { /* modo navegador */ }

    $("#buscar").addEventListener("submit", (ev) => { ev.preventDefault(); buscar($("#q").value); });
    $("#q").addEventListener("focus", () => { if (!estado.hibrido) cargarIndice(); }, { once: true });
    document.querySelectorAll("[data-ejemplo]").forEach((b) => b.addEventListener("click", () => {
      $("#q").value = b.dataset.ejemplo;
      $("#fecha").value = b.dataset.fecha || "";
      buscar(b.dataset.ejemplo);
    }));
    $("#copiar").addEventListener("click", copiarParaClaude);
    $("#cerrar").addEventListener("click", cerrarLector);
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !$("#lector").hidden) cerrarLector(); });
    $("#pestanas").addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-filtro]");
      if (!b) return;
      document.querySelectorAll("#pestanas button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      pintarCatalogo(b.dataset.filtro);
    });
    const desdeHash = () => {
      const m = location.hash.match(/^#q=(.+)$/);
      if (!m) return;
      const q = decodeURIComponent(m[1]);
      if (q === estado.consulta) return;
      $("#q").value = q;
      buscar(q);
    };
    window.addEventListener("hashchange", desdeHash);
    desdeHash();
  }

  document.addEventListener("DOMContentLoaded", iniciar);
})();
