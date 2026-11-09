// Log: la cola de generacion (lotes en orden, en vivo), que se esta generando, ComfyUI, Ollama y el historial.
import {el, api, head, toast} from "./ui.js";

let filter = "";
let timer = null;
const STATE_CLASS = {corriendo: "b-generado", pendiente: "b-pendiente", hecho: "b-aprobado", fallo: "b-rechazado", cancelado: ""};

function queuePanel(data) {
  const running = data.lotes.filter(item => item.estado === "corriendo");
  const waiting = data.lotes.filter(item => item.estado === "pendiente");
  const done = data.lotes.filter(item => !["corriendo", "pendiente"].includes(item.estado));
  const row = (item, index) => {
    const total = item.total || 0;
    const percent = total ? Math.round(100 * item.hechos / total) : 0;
    return el("tr", {class: item.estado === "corriendo" ? "on" : ""},
      el("td", {}, item.estado === "pendiente" ? `${index + 1}°` : ""),
      el("td", {}, `#${item.lote}`),
      el("td", {}, el("span", {class: "badge " + (STATE_CLASS[item.estado] || "")}, item.estado)),
      el("td", {}, el("div", {}, item.etiqueta || `${item.ids.length} nodos`),
        item.actual ? el("div", {class: "why"}, "▶ " + item.actual) : null,
        item.resultado && item.estado !== "corriendo" ? el("div", {class: "why"}, item.resultado) : null),
      el("td", {style: "min-width:140px"}, total ? [el("div", {class: "bar"}, el("i", {style: `width:${percent}%;background:var(--accent)`})),
        el("div", {class: "why"}, `${item.hechos}/${total} pasos`)] : el("span", {class: "why"}, item.estado === "pendiente" ? "esperando" : "—")),
      el("td", {class: "why"}, (item.creado || "").replace("T", " ").slice(5, 16)),
      el("td", {}, item.estado === "pendiente" ? el("button", {class: "btn sm bad", onclick: async () => {
        try { await api("/api/lote_cancelar", {lote: item.lote}); toast(`Lote ${item.lote} cancelado`); refresh(); } catch (error) { toast("Error: " + error.message); }
      }}, "Cancelar") : null));
  };
  const box = el("div", {class: "panel", id: "cola-lotes"},
    el("div", {class: "row", style: "justify-content:space-between"},
      el("h3", {style: "margin:0"}, `Cola de generación · ${running.length ? "generando" : "quieta"} · ${waiting.length} esperando`),
      el("div", {class: "row"},
        waiting.length && !data.trabajador ? el("button", {class: "btn sm primary", onclick: async () => {
          await api("/api/cola_arrancar", {}); toast("Cola arrancada"); refresh(); }}, "Arrancar cola") : null,
        el("button", {class: "btn sm", onclick: async () => { await api("/api/pausa", {pausar: !data.pausa}); toast(data.pausa ? "Sigue la cola" : "La cola frena después del paso actual"); refresh(); }},
          data.pausa ? "Sacar pausa" : "Pausar"),
        done.length ? el("button", {class: "btn sm", onclick: async () => { await api("/api/lotes_limpiar", {}); refresh(); }}, "Limpiar terminados") : null)),
    el("p", {class: "why"}, "Cada pedido (regenerar, ficha completa, clip, generar con Ollama, revisión) entra como un lote y se hace en orden, uno por vez. Podés seguir pidiendo mientras genera."),
    data.lotes.length ? el("table", {class: "shots"},
      el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", {}, "Lote"), el("th", {}, "Estado"), el("th", {}, "Qué"), el("th", {}, "Avance"), el("th", {}, "Pedido"), el("th", {}, ""))),
      el("tbody", {}, [...running.map(row), ...waiting.map(row), ...done.slice(0, 15).map(row)]))
      : el("p", {class: "why"}, "La cola está vacía."));
  return box;
}

async function refresh() {
  const box = document.getElementById("cola-lotes");
  if (!box) return clearInterval(timer);
  const data = await api("/api/log" + (filter ? "?nodo=" + encodeURIComponent(filter) : ""));
  box.replaceWith(queuePanel(data));
  const history = document.getElementById("log-historial");
  if (history && document.activeElement !== history) history.textContent = data.historial.slice().reverse().join("\n");
  const now = document.getElementById("log-ahora");
  const current = data.estado && data.estado.actual;
  if (now) now.textContent = data.corriendo ? (current ? `${current.nodo} ${current.paso || ""}` : "preparando") : "nada";
  const comfy = document.getElementById("log-comfy");
  if (comfy) comfy.textContent = data.comfyui.prendido ? `prendido · ${data.comfyui.vram_libre_gb} GB libres` : "apagado";
  const ollama = document.getElementById("log-ollama");
  if (ollama) ollama.textContent = data.ollama_cargado.length ? data.ollama_cargado.join(", ") : "descargado";
  const comfyLog = document.getElementById("log-comfyui");
  if (comfyLog) comfyLog.textContent = data.comfyui_log.join("\n") || "Sin log de ComfyUI en este proyecto.";
}

export async function logPage() {
  const data = await api("/api/log" + (filter ? "?nodo=" + encodeURIComponent(filter) : ""));
  const current = data.estado && data.estado.actual;
  const search = el("input", {value: filter, placeholder: "filtrar por nodo (ej: retrato/kaito_veyra, toma/2051)"});
  clearInterval(timer);
  timer = setInterval(refresh, 2000);   // en vivo mientras esta pagina este abierta
  return [head("Herramientas", "Log", "La cola de generación y qué está pasando ahora (se actualiza sola cada 2 s)."),
    el("div", {class: "stats", style: "margin-bottom:12px"},
      el("div", {class: "stat"}, el("div", {class: "k"}, "Generando ahora"), el("div", {class: "v", id: "log-ahora", style: "font-size:16px"},
        data.corriendo ? (current ? `${current.nodo} ${current.paso || ""}` : "preparando") : "nada")),
      el("div", {class: "stat"}, el("div", {class: "k"}, "ComfyUI"), el("div", {class: "v", id: "log-comfy", style: "font-size:16px"},
        data.comfyui.prendido ? `prendido · ${data.comfyui.vram_libre_gb} GB libres` : "apagado")),
      el("div", {class: "stat"}, el("div", {class: "k"}, "Ollama"), el("div", {class: "v", id: "log-ollama", style: "font-size:16px"},
        data.ollama_cargado.length ? data.ollama_cargado.join(", ") : "descargado"))),
    queuePanel(data),
    el("div", {class: "grid", style: "margin-top:14px"},
      el("div", {class: "panel"}, el("h3", {}, `Pendiente para generar (${data.plan.length})`),
        el("p", {class: "why"}, "Lo que todavía falta en el proyecto (entra a la cola con «Regenerar» o desde cada tarjeta)."),
        el("pre", {class: "log", style: "max-height:240px"}, data.plan.map(job => `${job.motivo.padEnd(15)} ${job.nodo}`).join("\n") || "Nada.")),
      el("div", {class: "panel"}, el("h3", {}, "Pedidos a Ollama"),
        el("pre", {class: "log", style: "max-height:240px"}, data.pedidos.slice().reverse().map(item =>
          `${item.estado.padEnd(10)} ${JSON.stringify(item.pedido)} ${item.fecha}`).join("\n") || "Ninguno."))),
    el("h2", {}, "Historial"),
    el("div", {class: "row", style: "margin-bottom:8px"}, search,
      el("button", {class: "btn", onclick: () => { filter = search.value.trim(); window.sfRender(true); }}, "Filtrar"),
      filter ? el("button", {class: "btn", onclick: () => { filter = ""; window.sfRender(true); }}, "Ver todo") : null),
    el("pre", {class: "log", id: "log-historial", style: "max-height:420px"}, data.historial.slice().reverse().join("\n") || "Sin registro todavía."),
    el("h2", {}, "ComfyUI (últimas líneas)"),
    el("pre", {class: "log", id: "log-comfyui", style: "max-height:240px"}, data.comfyui_log.join("\n") || "Sin log de ComfyUI en este proyecto.")];
}
