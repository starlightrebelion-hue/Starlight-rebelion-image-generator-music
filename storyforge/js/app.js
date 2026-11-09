// StoryForge: etapas (como LTX Studio), proyecto activo, barra de la cola y refresco. Cada pagina en su modulo.
import {$, el, api, toast, queued, confirmBox, closeDrawer} from "./ui.js";
import {overview} from "./overview.js";
import {idea, premisa} from "./premisa.js";
import {guion} from "./guion.js";
import {personajes} from "./personajes.js";
import {arteEtapa} from "./arte.js";
import {storyboard} from "./storyboard.js";
import {tecnico} from "./tecnico.js";
import {edicion} from "./edicion.js";
import {audio} from "./audio.js";
import {piloto} from "./piloto.js";
import {exportPage} from "./export.js";
import {configuracion} from "./config.js";
import {logPage} from "./log.js";
import {agentes} from "./agentes.js";
import {projectMenu} from "./proyectos.js";
import {revision} from "./revision.js";
import {libros} from "./libros.js";
import {carpetas} from "./carpetas.js";

// etapa: clave de /api/etapas para el puntito de estado
const PAGES = [
  {id: "overview", name: "Overview", view: overview},
  {group: "Etapas"},
  {id: "idea", name: "Idea", view: idea, etapa: "idea"},
  {id: "premisa", name: "Premisa", view: premisa, etapa: "premisa"},
  {id: "guion", name: "Guion", view: guion, etapa: "guion"},
  {id: "personajes", name: "Casting", view: personajes, etapa: "casting", tipos: ["retrato", "vestuario", "vista", "expresion", "cinematico", "tela", "hoja"]},
  {id: "arte", name: "Arte", view: arteEtapa, etapa: "arte", tipos: ["lugar", "objeto"]},
  {id: "tecnico", name: "Dirección", view: tecnico, etapa: "direccion"},
  {id: "storyboard", name: "Storyboard", view: storyboard, etapa: "storyboard", tipos: ["toma"]},
  {id: "audio", name: "Audio", view: audio, etapa: "audio"},
  {id: "edicion", name: "Edición", view: edicion, etapa: "edicion"},
  {id: "export", name: "Export", view: exportPage, etapa: "export"},
  {group: "Herramientas"},
  {id: "carpetas", name: "Carpetas", view: carpetas, tool: true},
  {id: "revision", name: "Revisión", view: revision, tool: true},
  {id: "libros", name: "Libros", view: libros, tool: true},
  {id: "log", name: "Log", view: logPage, tool: true},
  {id: "agentes", name: "Agentes", view: agentes, tool: true},
  {id: "config", name: "Configuración", view: configuracion, tool: true},
  {id: "piloto", name: "Piloto", view: piloto, tool: true},
];
const ALIASES = {lugares: ["arte", {sub: "lugar"}], objetos: ["arte", {sub: "objeto"}], vestuario: ["arte", {sub: "vestuario"}],
  casting: ["personajes", {}], direccion: ["tecnico", {}], musica: ["audio", {}]};
const STAGE_COLORS = {vacia: "#3a3f49", "en curso": "var(--warn)", lista: "var(--ok)"};

export const state = {page: "overview", summary: null, stages: {}, polling: null, lastLog: null, params: {}};

export function go(page, params = {}) {
  if (ALIASES[page]) [page, params] = [ALIASES[page][0], {...ALIASES[page][1], ...params}];
  state.page = page;
  state.params = params;
  $("#side").classList.remove("open");
  closeDrawer();
  try { localStorage.setItem("sf_page", page); } catch (error) { /* sin almacenamiento */ }
  const arg = params.semilla || params.id || params.sub;
  const hash = "#" + page + (arg ? "/" + arg : "");
  if (location.hash !== hash) history.pushState(null, "", hash);
  render();
}
window.sfGo = go;

function fromHash() {
  let [page, arg] = decodeURIComponent(location.hash.slice(1)).split("/");
  let params = !arg ? {} : /^\d+$/.test(arg) ? {semilla: Number(arg)} : {id: arg, sub: arg};
  if (ALIASES[page]) [page, params] = [ALIASES[page][0], {...ALIASES[page][1], ...params}];
  if (!PAGES.some(item => item.id === page)) return false;
  state.page = page;
  state.params = params;
  return true;
}
window.addEventListener("popstate", () => { if (fromHash()) { closeDrawer(); render(); } });
window.sfRender = quiet => render(quiet);

function pageCount(page) {
  if (!state.summary || !page.tipos) return null;
  let todo = 0, total = 0, corriendo = 0;

  // 1. Contar totales y pendientes desde el resumen de nodos
  for (const tipo of page.tipos) {
    for (const [status, n] of Object.entries(state.summary.conteos[tipo] || {})) {
      if (status === "a pedido") continue;
      total += n;
      if (["rechazado", "desactualizado", "generado"].includes(status)) todo += n;
    }
  }

  // 2. Verificar si hay algo de este tipo corriendo en la cola actual
  if (state.summary.cola && state.summary.cola.corriendo) {
    const actual = state.summary.cola.estado && state.summary.cola.estado.actual;
    if (actual && actual.nodo) {
      const nodo_tipo = actual.nodo.split("/")[0];
      if (page.tipos.includes(nodo_tipo)) corriendo = 1;
    }
  }

  return {todo, total, corriendo};
}

function renderNav() {
  const nav = $("#nav");
  nav.replaceChildren();
  let number = 0;
  for (const page of PAGES) {
    if (page.group) { nav.append(el("div", {class: "nav-group"}, page.group)); continue; }
    if (page.etapa) number += 1;
    const count = pageCount(page);
    const stage = page.etapa ? state.stages[page.etapa] : null;

    // Determinar color del contador
    let countClass = "";
    if (count && count.total) {
      if (count.corriendo) countClass = " warn"; // Titilando amarillo: trabajando
      else if (count.todo) countClass = " alert"; // Rojo: faltan/rechazados
      else countClass = " ok"; // Verde: todo listo
    }

    nav.append(el("button", {class: "nav-btn" + (state.page === page.id ? " active" : ""), onclick: () => go(page.id)},
      el("span", {}, page.etapa ? el("span", {class: "n"}, String(number).padStart(2, "0")) : null, page.name),
      el("span", {class: "row", style: "gap:6px"},
        count && count.total ? el("span", {class: "num" + countClass, title: "pendientes / total"},
          count.todo ? `${count.todo}/${count.total}` : count.total) : null,
        stage ? el("i", {class: "stage-dot", title: `etapa ${stage}`, style: `background:${STAGE_COLORS[stage] || "#3a3f49"}`}) : null)));
  }
}

export function nextStage() {
  const stages = PAGES.filter(page => page.etapa);
  const index = stages.findIndex(page => page.id === state.page);
  return index >= 0 && index < stages.length - 1 ? stages[index + 1] : null;
}

export async function loadSummary() {
  [state.summary, state.stages] = await Promise.all([api("/api/resumen"), api("/api/etapas")]);
  renderNav();
  renderQueue(state.summary.cola, state.summary.ollama_cargado);
  const jobs = state.summary.plan.filter(job => job.motivo !== "esperando").length;
  const button = $("#regen");
  button.textContent = `Regenerar rechazados y dependientes (${jobs})`;
  button.disabled = !jobs;   // si hay algo corriendo, el pedido espera su turno en la cola
  button.title = state.summary.ollama_cargado ? "Ollama está cargado: la cola lo descarga antes de prender ComfyUI" : "";
  const next = nextStage();
  const nextButton = $("#next");
  nextButton.style.display = next ? "" : "none";
  if (next) { nextButton.textContent = `Siguiente: ${next.name} →`; nextButton.onclick = () => go(next.id); }
}

function renderQueue(queue, ollama) {
  const box = $("#queue");
  box.replaceChildren();
  if (queue.corriendo) {
    const current = queue.estado && queue.estado.actual;
    const waiting = queue.lotes_pendientes ? ` · ${queue.lotes_pendientes} lote(s) esperando` : "";
    box.append("Cola: ", el("b", {}, "corriendo"), current ? ` · ${current.nodo} ${current.paso || ""}` : "", waiting,
      " ", el("a", {href: "#log", onclick: event => { event.preventDefault(); go("log"); }}, "ver log"));
    if (!state.polling) state.polling = setInterval(pollQueue, 3000);
  } else {
    box.append("Cola: quieta");
    if (state.polling) { clearInterval(state.polling); state.polling = null; render(true); }
  }
  if (ollama) box.append(" · ", el("span", {class: "warn"}, "Ollama cargado"));
}

// sin pisar lo que el usuario esta escribiendo (nota abierta, confirmacion o un campo con foco)
function busy() {
  return document.querySelector(".reject.open") || document.querySelector(".confirm") ||
    ["TEXTAREA", "INPUT", "SELECT"].includes((document.activeElement || {}).tagName) || $("#drawer").classList.contains("open");
}

async function pollQueue() {
  const queue = await api("/api/cola");
  renderQueue(queue, false);
  const log = $("#log");
  if (log) log.textContent = queue.registro.join("\n");
  const mark = queue.registro.length + "|" + (queue.registro[queue.registro.length - 1] || "");
  if (state.lastLog !== null && mark !== state.lastLog && !busy()) render(true);   // termino un paso: la imagen nueva
  state.lastLog = mark;
}

export async function render(quiet = false) {
  const content = $("#content");
  const scroll = window.scrollY;
  if (!quiet) content.replaceChildren(el("div", {class: "empty"}, "Cargando…"));
  try {
    await loadSummary();
    const page = PAGES.find(item => item.id === state.page) || PAGES[0];
    const view = await page.view(state.params);
    content.replaceChildren(...[view].flat(Infinity).filter(Boolean));
    if (quiet) window.scrollTo(0, scroll);
  } catch (error) {
    content.replaceChildren(el("div", {class: "empty"}, "Error: " + error.message));
  }
}

$("#refresh").addEventListener("click", () => render());
$("#menu").addEventListener("click", () => $("#side").classList.toggle("open"));
$("#lightbox").addEventListener("click", () => $("#lightbox").classList.remove("open"));
document.addEventListener("keydown", event => { if (event.key === "Escape") { closeDrawer(); $("#lightbox").classList.remove("open"); } });
document.addEventListener("visibilitychange", () => { if (!document.hidden && !busy()) render(true); });
$("#regen").addEventListener("click", () => {
  const plan = state.summary.plan.filter(job => job.motivo !== "esperando");
  const list = plan.slice(0, 25).map(job => `${job.nodo} (${job.motivo})`).join("\n");
  confirmBox(`Se van a generar ${plan.length} trabajos:\n\n${list}${plan.length > 25 ? "\n…" : ""}`, async () => {
    const result = await api("/api/regenerar", {ids: [], etiqueta: "todo lo pendiente"});
    queued(result, `${plan.length} trabajos`);
    loadSummary();
  });
});

(async function start() {
  await projectMenu();
  if (!fromHash()) {
    try { state.page = localStorage.getItem("sf_page") || "overview"; } catch (error) { /* sin almacenamiento */ }
  }
  render();
})();
