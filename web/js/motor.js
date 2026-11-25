/* ley·energía: motor de búsqueda del sitio estático. Puro: sin DOM ni red.
 *
 * Lo usa la página (globalThis.LeyMotor) y la evaluación en Node (evaluacion/web.cjs), así que
 * las cifras de evaluación del sitio salen de este mismo código. Replica las reglas de
 * src/ley_energia/texto.py y busqueda.py: raíces Snowball precalculadas, artículo exacto,
 * documento nombrado (gana el nombre más largo) y fusión de rangos recíprocos.
 */
"use strict";

(function (raiz) {
  const K_RRF = 60;
  const PESOS = { lexica: 1.0, articulo: 2.5, documento: 0.9 };
  // Límites de palabra que entienden acentos (\b de JS sólo reconoce ASCII).
  const ANTES = "(?<![\\p{L}\\p{N}])";
  const DESPUES = "(?![\\p{L}\\p{N}])";
  const ORDINAL =
    "(?:(?:d[ée]cimo|vig[ée]simo|trig[ée]simo)\\s+)?(?:primero|segundo|tercero|cuarto|quinto|sexto|s[ée]ptimo|octavo|noveno|d[ée]cimo|und[ée]cimo|duod[ée]cimo|vig[ée]simo|trig[ée]simo|[úu]nico)";
  const RE_ART = new RegExp(
    `${ANTES}(?:art[íi]culos?|arts?\\.?)\\s*(\\d{1,4})\\s*[oº°]?\\.?((?:\\s*(?:bis|ter|qu[aá]ter|quinquies|sexies))?)${DESPUES}`,
    "giu");
  const RE_TRANS = new RegExp(
    `${ANTES}transitorio\\s+(${ORDINAL})${DESPUES}|${ANTES}(${ORDINAL})\\s+transitorio${DESPUES}`, "giu");
  const RE_DISP = new RegExp(`${ANTES}(?:disposici[oó]n|numeral)\\s+(\\d{1,2}\\.\\d{1,2})${DESPUES}`, "giu");

  /** Quita acentos sin cambiar mayúsculas ni longitud (en NFC); conserva la ñ. */
  function quitarAcentos(t) {
    let salida = "";
    for (const c of t.normalize("NFC")) {
      if (c === "ñ" || c === "Ñ") { salida += c; continue; }
      const base = c.normalize("NFD").replace(/\p{M}/gu, "");
      salida += base.length === 1 ? base : c;
    }
    return salida;
  }

  function normalizar(t) {
    return quitarAcentos(t).toLowerCase();
  }

  function nombreCorto(doc) {
    return doc.abreviatura || (doc.alias && doc.alias[0]) || doc.titulo;
  }

  function citar(doc, etiqueta) {
    const e = /^(Artículo|Disposición|Transitorio)(?![\p{L}])/u.test(etiqueta)
      ? etiqueta[0].toLowerCase() + etiqueta.slice(1) : etiqueta;
    return `${nombreCorto(doc)}, ${e}`;
  }

  function vigenteEn(doc, fecha) {
    const inicio = doc.vigor_desde || doc.fecha_pub;
    if (fecha < inicio) return false;
    return !doc.abrogada_desde || fecha < doc.abrogada_desde;
  }

  function fechaValida(f) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f)) return false;
    const d = new Date(`${f}T00:00:00Z`);
    return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === f;
  }

  function claveArticulo(num, sufijo) {
    const s = normalizar(sufijo || "").trim();
    return s ? `${parseInt(num, 10)} ${s}` : String(parseInt(num, 10));
  }

  function detectarClaves(q) {
    const claves = [];
    for (const m of q.matchAll(RE_TRANS)) claves.push(`transitorio ${normalizar(m[1] || m[2]).split(/\s+/).join(" ")}`);
    for (const m of q.matchAll(RE_DISP)) claves.push(m[1]);
    for (const m of q.matchAll(RE_ART)) {
      const c = claveArticulo(m[1], m[2]);
      if (!claves.includes(c)) claves.push(c);
    }
    return claves;
  }

  /** Completa el índice exportado con lo que se calcula una sola vez. */
  function prepararIndice(ix) {
    ix.vaciasSet = new Set(ix.vacias);
    ix.N = ix.longitudes.length;
    ix.prom = ix.longitudes.reduce((a, b) => a + b, 0) / ix.N;
    return ix;
  }

  function raicesConsulta(q, ix) {
    const palabras = normalizar(q).match(/[a-z0-9ñ]+/g) || [];
    const out = [];
    for (const p of palabras) {
      if (p.length < 2 || ix.vaciasSet.has(p)) continue;
      let r = ix.palabras[p] || p;
      if (!ix.postings[r]) {
        for (const alt of [p.replace(/es$/, ""), p.replace(/s$/, "")]) {
          const ra = ix.palabras[alt] || alt;
          if (ix.postings[ra]) { r = ra; break; }
        }
      }
      if (!out.includes(r)) out.push(r);
    }
    // Vocabulario de 2014 a 2025 (mismas equivalencias que el índice local).
    const norm = ` ${normalizar(q).replace(/[^a-z0-9ñ]+/g, " ")} `;
    for (const [viejo, nuevos] of Object.entries(ix.equivalencias || {})) {
      if (!norm.includes(` ${viejo} `)) continue;
      for (const frase of nuevos) for (const r of frase) if (!out.includes(r)) out.push(r);
    }
    return out;
  }

  function fusionar(senales) {
    const p = new Map();
    for (const [nombre, ranking] of Object.entries(senales)) {
      const w = PESOS[nombre] || 1;
      ranking.forEach((fid, i) => p.set(fid, (p.get(fid) || 0) + w / (K_RRF + i + 1)));
    }
    return [...p.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]);
  }

  const escapar = (s) => s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");

  /** Motor sobre un catálogo (datos/catalogo.json). */
  function crearMotor(catalogo) {
    const docs = catalogo.documentos;
    const porId = Object.fromEntries(docs.map((d) => [d.id, d]));
    const patrones = [];
    for (const d of docs) {
      const nombres = [...d.nombres];
      if (d.tipo === "reglamento") {
        const ley = docs.find((x) => x.tipo === "ley" && d.titulo.endsWith(x.titulo));
        if (ley) {
          for (const n of [...(ley.alias || []), ley.abreviatura]) {
            if (n) nombres.push(`reglamento de la ${normalizar(n)}`, `reglamento ${normalizar(n)}`);
          }
        }
      }
      for (const n of nombres) patrones.push({ id: d.id, re: new RegExp(`(?<![a-z0-9ñ])${escapar(n)}(?![a-z0-9ñ])`, "gu"), sigla: false });
      if (d.abreviatura) {
        const s = escapar(d.abreviatura);
        patrones.push({ id: d.id, re: d.abreviatura.includes("/") ? new RegExp(s, "gu") : new RegExp(`${ANTES}${s}${DESPUES}`, "gu"), sigla: true });
      }
    }

    function detectarDocs(q) {
      // Mismo largo en las dos versiones: las posiciones de siglas y nombres se comparan bien.
      const sinAcentos = quitarAcentos(q);
      const norm = sinAcentos.toLowerCase();
      const hall = [];
      for (const p of patrones) {
        const objetivo = p.sigla ? sinAcentos : norm;
        for (const m of objetivo.matchAll(p.re)) hall.push([m.index, m.index + m[0].length, p.id]);
      }
      hall.sort((a, b) => a[0] - b[0] || (b[1] - b[0]) - (a[1] - a[0]));
      const elegidos = [];
      let fin = -1;
      for (const [ini, ter, id] of hall) {
        if (ini < fin) continue;
        fin = ter;
        if (!elegidos.includes(id)) elegidos.push(id);
      }
      return elegidos;
    }

    /** Búsqueda BM25 + artículo exacto + documento nombrado sobre el índice del navegador. */
    function buscar(q, filtros, k, ix) {
      const nombrados = detectarDocs(q);
      const tipo = filtros.tipo ? filtros.tipo.toLowerCase() : null;
      if (filtros.fecha && !fechaValida(filtros.fecha)) throw new Error("fecha inválida: usa AAAA-MM-DD");
      const permitido = (id) => {
        const d = porId[id];
        if (tipo && d.tipo !== tipo) return false;
        if (filtros.fecha) return vigenteEn(d, filtros.fecha);
        return filtros.abrogados || !d.abrogada_desde || nombrados.includes(id);
      };
      const k1 = 1.2, b = 0.75;
      const puntos = new Map();
      for (const r of raicesConsulta(q, ix)) {
        const post = ix.postings[r];
        if (!post) continue;
        const df = post.length / 2;
        const idf = Math.log(1 + (ix.N - df + 0.5) / (df + 0.5));
        for (let i = 0; i < post.length; i += 2) {
          const fid = post[i], tf = post[i + 1];
          if (!permitido(ix.fragmentos[fid].d)) continue;
          const len = ix.longitudes[fid];
          const s = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * len / ix.prom));
          puntos.set(fid, (puntos.get(fid) || 0) + s);
        }
      }
      const lexica = [...puntos.entries()].sort((a, c) => c[1] - a[1] || a[0] - c[0]).slice(0, 200).map((x) => x[0]);
      const senales = { lexica };
      const posicion = new Map(lexica.map((f, i) => [f, i]));
      const claves = detectarClaves(q);
      if (claves.length) {
        const prio = new Map(nombrados.map((d, i) => [d, i]));
        senales.articulo = ix.fragmentos
          .map((f, i) => [f, i])
          .filter(([f]) => f.c && claves.includes(f.c) && permitido(f.d) && (!nombrados.length || nombrados.includes(f.d)))
          .sort((a, c) => (prio.get(a[0].d) ?? 99) - (prio.get(c[0].d) ?? 99) || (posicion.get(a[1]) ?? 1e6) - (posicion.get(c[1]) ?? 1e6) || a[1] - c[1])
          .map(([, i]) => i);
      }
      const nom = nombrados.filter(permitido);
      if (nom.length) {
        const ranking = lexica.filter((fid) => nom.includes(ix.fragmentos[fid].d));
        if (ranking.length < 50) {
          ix.fragmentos.forEach((f, i) => { if (nom.includes(f.d) && ranking.length < 100 && !ranking.includes(i)) ranking.push(i); });
        }
        senales.documento = ranking;
      }
      return fusionar(senales).slice(0, k).map(([fid]) => {
        const f = ix.fragmentos[fid];
        const d = porId[f.d];
        return { doc: d, clave: f.c, etiqueta: f.e, ruta: [], texto: f.x, cita: citar(d, f.e), parcial: true };
      });
    }

    return { detectarDocs, buscar, porId };
  }

  raiz.LeyMotor = {
    quitarAcentos, normalizar, nombreCorto, citar, vigenteEn, fechaValida, detectarClaves,
    prepararIndice, raicesConsulta, crearMotor,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
