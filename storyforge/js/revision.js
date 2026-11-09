// Revision: los cuatro revisores de Pixel-set + el Coordinador (hoja de ruta) sobre la etapa elegida.
import {el, api, head, toast, queued, confirmBox} from "./ui.js";

let stage = "guion";
const NAMES = {idea: "Idea", premisa: "Premisa", guion: "Guion", direccion: "Dirección", storyboard: "Storyboard", edicion: "Edición"};

// markdown minimo: titulos, listas, negritas y tablas (sin HTML del texto: todo va como texto)
function markdown(text) {
  const box = el("div", {class: "md"});
  let table = null;
  for (const raw of (text || "").replace(/<!--.*?-->/gs, "").split("\n")) {
    const line = raw.trimEnd();
    if (/^\|/.test(line)) {
      if (/^\|[\s:|-]+\|$/.test(line)) continue;
      if (!table) { table = el("table", {class: "shots"}); box.append(table); }
      table.append(el("tr", {}, line.split("|").slice(1, -1).map(cell => el("td", {}, cell.trim()))));
      continue;
    }
    table = null;
    if (!line.trim()) continue;
    const heading = line.match(/^(#{1,4})\s+(.*)/);
    if (heading) { box.append(el(`h${Math.min(4, heading[1].length + 1)}`, {}, heading[2])); continue; }
    const item = line.match(/^\s*[-*]\s+(.*)/);
    const content = (item ? item[1] : line).split(/(\*\*[^*]+\*\*)/).map(part => part.startsWith("**") ? el("b", {}, part.slice(2, -2)) : part);
    box.append(item ? el("div", {class: "md-li"}, "• ", content) : el("p", {}, content));
  }
  return box;
}

export async function revision(params = {}) {
  if (params.sub && NAMES[params.sub]) stage = params.sub;
  const data = await api("/api/revision?etapa=" + stage);
  const tabs = el("div", {class: "tabs"}, data.etapas.map(name => el("button", {class: "tab" + (name === stage ? " on" : ""),
    onclick: () => { stage = name; window.sfRender(true); }}, NAMES[name] || name)));
  const followUp = el("textarea", {value: data.seguimiento, placeholder: "Qué notas resolviste, cuáles siguen abiertas y cuáles rebatís (con tu argumento). Entra en la próxima ronda."});
  return [
    head("Herramientas", "Revisión", "Cuatro revisores (Sociología, Estructuras Narrativas, Literatura de las Artes Combinadas, Estética y Teoría de los Medios) leen la etapa contra tu declaración de intención; el Coordinador arma la hoja de ruta. Diagnostican y preguntan: no reescriben."),
    tabs,
    el("div", {class: "row", style: "margin-bottom:12px"},
      el("span", {class: "why"}, "Revisores de esta etapa: " + data.activos.map(item => item.nombre).join(", ")),
      el("button", {class: "btn primary", onclick: () => confirmBox(
        `Ronda de revisión de ${NAMES[stage]} (versión ${(data.version || 0) + 1}).\n${data.activos.length} revisores + Coordinador, con Ollama en la cola.\nSi un revisor no responde, su informe falta (y se avisa).`,
        async () => { const r = await api("/api/generar", {tipo: "revision", etapa: stage}); queued(r, "Revisión"); }, "Revisar")},
        `✦ Revisar ${NAMES[stage]}`),
      data.versiones.length ? el("span", {class: "why"}, `versiones: ${data.versiones.join(", ")}`) : null),
    data.version ? el("div", {class: "grid", style: "grid-template-columns:minmax(320px,1.3fr) 1fr"},
      el("div", {class: "panel"}, el("div", {class: "eyebrow"}, `Hoja de ruta · versión ${data.version}`), markdown(data.hoja_de_ruta)),
      el("div", {},
        Object.entries(data.informes).map(([name, text]) => el("details", {class: "panel", style: "margin-bottom:8px"},
          el("summary", {}, el("b", {}, `Informe de ${name}`)), markdown(text))),
        el("div", {class: "panel"}, el("h3", {}, "Seguimiento del autor"), followUp,
          el("button", {class: "btn", style: "margin-top:6px", onclick: async () => {
            await api("/api/revision_seguimiento", {etapa: stage, texto: followUp.value}); toast("Seguimiento guardado"); }}, "Guardar seguimiento"))))
      : el("div", {class: "empty"}, "Todavía no hay revisiones de esta etapa. Completá la declaración de intención en Premisa y pedí una ronda."),
  ];
}
