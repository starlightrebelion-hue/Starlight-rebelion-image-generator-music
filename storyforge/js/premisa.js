// Etapas 1 y 2: Idea y Premisa (con la declaracion de intencion de los revisores de Pixel-set).
import {el, api, head, toast} from "./ui.js";

export async function idea() {
  const project = await api("/api/proyecto");
  const text = el("textarea", {style: "min-height:160px", value: project.idea || ""});
  return [head("Etapa 1", "Idea", "De qué trata, en tus palabras. A partir de esto se genera la premisa (y después las secuencias, las escenas y los planos)."),
    el("div", {class: "panel"}, el("div", {class: "field"}, el("label", {}, "Idea"), text),
      el("div", {class: "row"},
        el("button", {class: "btn primary", onclick: async () => { await api("/api/proyecto", {idea: text.value}); toast("Idea guardada"); window.sfRender(true); }}, "Guardar idea"),
        el("button", {class: "btn", onclick: () => window.sfGo("premisa")}, "Ir a la premisa →")))];
}

const PREMISE = [["titulo", "Título"], ["logline", "Logline (una oración)"], ["tema", "Tema y tesis"], ["genero", "Género"],
  ["tono", "Tono"], ["formato", "Formato y duración"], ["concepto", "Concepto"]];
const INTENT = [["experiencia", "Experiencia buscada: qué debe sentir, entender y recordar el espectador"],
  ["punto_de_vista", "Punto de vista"], ["publico", "Público imaginado"], ["referencias", "Referencias: obras, imágenes, sonidos"],
  ["restricciones", "Restricciones reales"], ["decisiones_cerradas", "Decisiones cerradas (no reabrir)"],
  ["preocupacion", "Lo que más me preocupa (donde quiero la crítica más dura)"]];

export async function premisa() {
  const project = await api("/api/proyecto");
  const fields = {};
  const intent = {};
  const input = (key, value, big) => el(big ? "textarea" : "input", {value: value || ""});
  return [head("Etapa 2", "Premisa", "La premisa y la declaración de intención: todos los agentes y revisores la leen antes de trabajar."),
    el("div", {class: "overview"},
      el("div", {}, project.poster ? el("div", {class: "poster", style: `background-image:url('${project.poster}')`},
        el("div", {class: "poster-content"}, el("div", {class: "poster-title"}, project.titulo), el("div", {class: "poster-logline"}, project.logline))) : null),
      el("div", {class: "panel"},
        PREMISE.map(([key, label]) => {
          fields[key] = input(key, project[key], ["logline", "tema", "concepto"].includes(key));
          return el("div", {class: "field"}, el("label", {}, label), fields[key]);
        }),
        el("h3", {style: "margin-top:16px"}, "Declaración de intención"),
        INTENT.map(([key, label]) => {
          intent[key] = input(key, (project.intencion || {})[key], true);
          return el("div", {class: "field"}, el("label", {}, label), intent[key]);
        }),
        el("div", {class: "row"},
          el("button", {class: "btn primary", onclick: async () => {
            const body = {intencion: {}};
            for (const [key, node] of Object.entries(fields)) body[key] = node.value;
            for (const [key, node] of Object.entries(intent)) body.intencion[key] = node.value;
            await api("/api/proyecto", body);
            toast("Premisa guardada");
            window.sfRender(true);
          }}, "Guardar premisa"),
          el("button", {class: "btn", onclick: () => window.sfGo("guion")}, "Ir al guion →"))))];
}
