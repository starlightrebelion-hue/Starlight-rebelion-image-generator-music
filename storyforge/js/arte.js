// Arte: lugares, objetos de firma y vestuario. Tarjetas de revision + edicion del texto que genera cada imagen.
// Una locacion puede llevar una foto subida a mano en vez del prompt (queda aprobada; lo que depende se rehace).
import {el, api, head, toast, nodeCard, STATES} from "./ui.js";

const LEADS = {
  lugar: "Locaciones de Neo-Kansai Delta sin personas, en tres capas (cerca, medio, lejos). Se hacen desde el prompt o con una foto propia; la miniatura de cada escena sale de acá.",
  objeto: "Objetos de firma de cada personaje. Diseño propio, sin texto legible.",
  vestuario: "Vestuario hasta la cintura sobre el retrato aprobado: es la única referencia de persona que entra en las tomas.",
};
const TITLES = {lugar: "Lugares", objeto: "Objetos", vestuario: "Vestuario"};
const filters = {};
let current = "lugar";

// Etapa 5: Arte con sus tres subsolapas
export async function arteEtapa(params = {}) {
  if (params.sub && TITLES[params.sub]) current = params.sub;
  const tabs = el("div", {class: "tabs"}, Object.entries(TITLES).map(([id, label]) =>
    el("button", {class: "tab" + (current === id ? " on" : ""), onclick: () => window.sfGo("arte", {sub: id})}, label)));
  const [header, ...rest] = await arte(current);
  return [header, tabs, ...rest];
}

export async function arte(tipo) {
  const data = await api("/api/estado?tipo=" + tipo);
  const nodes = data.nodos;
  filters[tipo] = filters[tipo] || "todos";
  const bar = el("div", {class: "filters"});
  const grid = el("div", {class: "grid"});
  const draw = () => {
    bar.replaceChildren(...["todos", ...STATES].map(status => {
      const n = status === "todos" ? nodes.length : nodes.filter(node => node.estado === status).length;
      return n || status === "todos" ? el("button", {class: "chip" + (filters[tipo] === status ? " on" : ""),
        onclick: () => { filters[tipo] = status; draw(); }}, `${status} ${n}`) : null;
    }).filter(Boolean));
    const shown = nodes.filter(node => filters[tipo] === "todos" || node.estado === filters[tipo]);
    grid.replaceChildren(...(shown.length ? shown.map(node => withText(node)) : [el("div", {class: "empty"}, "Nada en este estado.")]));
  };
  draw();
  return [head("Dirección de arte", TITLES[tipo], LEADS[tipo]), bar, grid];
}

function withText(node) {
  const card = nodeCard(node, {onChange: () => window.sfRender(true)});
  const editor = textEditor(node);
  const body = card.querySelector(".body");
  if (editor) body.insertBefore(editor, body.querySelector(":scope > .actions"));   // la de la tarjeta, no la del rechazo
  return card;
}

// un lugar: descripcion, luz, atmosfera y utileria por separado; sin personas ni acciones (el servidor lo controla)
function placeEditor(id, info) {
  const fields = [["prompt", "Descripción del lugar (vacío, sin personas ni acciones)", info.descripcion],
    ["luz", "Luz", info.luz], ["atmosfera", "Atmósfera (lo que se siente en el aire: lluvia, vapor, frío)", info.atmosfera],
    ["utileria", "Utilería (un objeto por renglón)", (info.utileria || []).join("\n")]];
  const inputs = {};
  return el("details", {}, el("summary", {}, "Editar el lugar"),
    fields.map(([key, label, value]) => {
      inputs[key] = el("textarea", {value: value || "", style: key === "prompt" ? "min-height:90px" : "min-height:50px"});
      return el("div", {class: "field"}, el("label", {}, label), inputs[key]);
    }),
    el("button", {class: "btn sm", onclick: async () => {
      try {
        const original = {prompt: info.descripcion, luz: info.luz, atmosfera: info.atmosfera, utileria: (info.utileria || []).join("\n")};
        let changed = 0;
        for (const [key, input] of Object.entries(inputs)) {
          if (input.value !== (original[key] || "")) { await api("/api/texto", {tipo: "lugar", id, campo: key, valor: input.value}); changed += 1; }
        }
        toast(changed ? "Lugar guardado: su imagen y lo que depende quedan desactualizados" : "Sin cambios");
        window.sfRender(true);
      } catch (error) { toast("Error: " + error.message); }
    }}, "Guardar lugar"));
}

function textEditor(node) {
  const [kind, name] = node.id.split("/");
  let body;
  if (kind === "lugar") return placeEditor(name, node.info);
  if (kind === "vestuario") body = {tipo: "personaje", id: name, campo: "vestuario", valor: node.info.vestuario};
  else if (kind === "objeto") {
    const [pid, index] = name.split("__");
    body = {tipo: "personaje", id: pid, campo: "objetos", indice: Number(index), valor: node.info.objeto};
  }
  if (!body) return null;
  const input = el("textarea", {value: body.valor || ""});
  return el("details", {}, el("summary", {}, "Editar el texto que la genera"), input,
    el("button", {class: "btn sm", style: "margin-top:4px", onclick: async () => {
      await api("/api/texto", {...body, valor: input.value});
      toast("Guardado: la imagen y lo que depende quedan desactualizados");
      window.sfRender(true);
    }}, "Guardar texto"));
}
