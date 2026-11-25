/* Evalúa la búsqueda del sitio estático (web/js/motor.js) con el mismo set que la de Python.
 *
 * Uso: node evaluacion/web.cjs <casos.json> [--detalle]
 * casos.json es evaluacion/golden.yaml convertido a JSON (lo hace la CI). Requiere web/datos,
 * que genera `uv run ley-energia exportar-web`. Sale con código 1 si algún caso falla.
 */
"use strict";
const fs = require("node:fs");
const path = require("node:path");

const RAIZ = path.resolve(__dirname, "..");
require(path.join(RAIZ, "web/js/motor.js"));
const M = globalThis.LeyMotor;

const leer = (p) => JSON.parse(fs.readFileSync(path.join(RAIZ, p), "utf8"));
const catalogo = leer("web/datos/catalogo.json");
const ix = M.prepararIndice(leer("web/datos/indice.json"));
const motor = M.crearMotor(catalogo);
const casos = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const detalle = process.argv.includes("--detalle");

const coincide = (r, e) => r.doc.id === e.doc && (e.clave === undefined || r.clave === String(e.clave));
let aciertos = 0, mrr = 0;
const fallos = [];
for (const c of casos) {
  const k = c.k || 5;
  const f = c.filtros || {};
  const res = motor.buscar(c.consulta, { tipo: f.tipo || null, abrogados: !!f.incluir_abrogados, fecha: f.fecha || null }, Math.max(k, 10), ix);
  let rango = null;
  res.forEach((r, i) => { if (rango === null && c.esperado.some((e) => coincide(r, e))) rango = i + 1; });
  const top = res.slice(0, k);
  const errores = [];
  if (rango && rango <= k) aciertos++; else errores.push(`fuera del top ${k} (rango ${rango})`);
  if (rango) mrr += 1 / rango;
  if (c.primero && rango !== 1) errores.push("no quedó en primer lugar");
  const intrusos = [...new Set(top.filter((r) => (c.ausentes || []).includes(r.doc.id)).map((r) => r.doc.id))];
  if (intrusos.length) errores.push(`aparecen ${intrusos}`);
  for (const a of c.ausentes_clave || []) if (top.some((r) => coincide(r, a))) errores.push(`aparece ${a.doc} ${a.clave}`);
  if (errores.length) fallos.push({ id: c.id, errores, top: top.slice(0, 3).map((r) => r.cita) });
  if (detalle) console.log(`${errores.length ? "XX" : "ok"} ${c.id.padEnd(38)} rango=${rango} ${errores.join("; ")}`);
}
const resumen = {
  casos: casos.length,
  recall_at_k: Number((aciertos / casos.length).toFixed(3)),
  mrr: Number((mrr / casos.length).toFixed(3)),
  aprobados: casos.length - fallos.length,
  fallos: fallos.map((f) => f.id),
};
console.log(JSON.stringify(resumen, null, 1));
for (const f of fallos) console.log(`  ${f.id}: ${f.errores.join("; ")} | ${f.top.join(" / ")}`);
process.exitCode = fallos.length ? 1 : 0;
