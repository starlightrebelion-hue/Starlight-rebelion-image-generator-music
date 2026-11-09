// Agentes: ver y editar los prompts (agentes/*.md) con respaldo, y leer los de Pixel-set.
import {el, api, head, toast} from "./ui.js";

let selected = null;

export async function agentes() {
  const data = await api("/api/agentes");
  if (!selected && data.agentes.length) selected = data.agentes[0].ruta;
  const list = el("div", {class: "script-side"},
    el("h3", {}, "Agentes de StoryForge"),
    data.agentes.map(agent => el("div", {class: "scene-item" + (agent.ruta === selected ? " on" : ""), onclick: () => { selected = agent.ruta; window.sfRender(true); }},
      el("span", {}, el("b", {}, agent.nombre), el("br"), el("small", {class: "why"}, agent.etapa || agent.ruta)))),
    el("h3", {style: "margin-top:16px"}, "Pixel-set (referencia)"),
    data.pixelset.length ? data.pixelset.map(item => el("div", {class: "scene-item" + (item.ruta === selected ? " on" : ""),
      onclick: () => { if (item.legible) { selected = item.ruta; window.sfRender(true); } else toast("Solo se pueden leer .md y .txt"); }},
      el("small", {}, item.nombre))) : el("p", {class: "why"}, "No se encontró C:\\Pixel-set\\agentes."));
  let editor = el("div", {class: "empty"}, "Elegí un agente.");
  if (selected) {
    const agent = await api("/api/agente?ruta=" + encodeURIComponent(selected));
    const meta = data.agentes.find(item => item.ruta === selected);
    const text = el("textarea", {class: "fountain", value: agent.texto, readonly: !agent.editable});
    editor = el("div", {},
      el("div", {class: "row", style: "justify-content:space-between;margin-bottom:8px"},
        el("div", {}, el("h2", {style: "margin:0"}, selected), meta && meta.etapa ? el("div", {class: "why"}, "Lo usa: " + meta.etapa) : null),
        agent.editable ? el("div", {class: "row"},
          el("button", {class: "btn primary", onclick: async () => {
            await api("/api/agente", {ruta: selected, texto: text.value});
            toast("Guardado (la versión anterior quedó en agentes/_respaldos)"); window.sfRender(true); }}, "Guardar"),
          meta && meta.respaldos.length ? el("select", {onchange: async event => {
            if (!event.target.value) return;
            await api("/api/agente_restaurar", {ruta: selected, respaldo: event.target.value});
            toast("Restaurado"); window.sfRender(true); }},
            el("option", {value: ""}, `Restaurar (${meta.respaldos.length} respaldos)`),
            meta.respaldos.map(name => el("option", {value: name}, name))) : null) : el("span", {class: "badge"}, "solo lectura")),
      text);
  }
  return [head("Herramientas", "Agentes", "Los prompts de cada agente. Al guardar queda un respaldo con fecha; los cambios se usan en el próximo pedido a Ollama."),
    el("div", {class: "script"}, list, editor)];
}
