// Configuracion del proyecto: Ollama, ComfyUI, post de la imagen, ajustes de las tomas y rutas.
import {el, api, head, toast} from "./ui.js";

export async function configuracion() {
  const data = await api("/api/config");
  const config = data.config;
  const model = el("select", {}, [...new Set([config.ollama_modelo, ...data.modelos_ollama])].map(name =>
    el("option", {value: name, selected: name === config.ollama_modelo}, name)));
  const context = el("input", {type: "number", value: config.num_ctx, min: 2048, step: 1024});
  const comfy = el("input", {value: config.comfy_url});
  const bloom = el("select", {}, data.opciones.bloom.map(name => el("option", {value: name, selected: name === config.bloom}, name)));
  const blacks = el("select", {}, data.opciones.negros.map(name => el("option", {value: name, selected: name === config.negros}, name)));
  const tuning = data.ajustes;
  const fields = {modo: ["stitch", "chain"], lora: ["glif90", "ninguno"], persona_ref: ["vestuario", "retrato"],
    denoise: [0.3, 0.4, 0.5], hires_denoise: [0.3, "ninguno"]};
  const selects = {};
  const row = (label, node, hint) => el("div", {class: "field"}, el("label", {}, label), node, hint ? el("span", {class: "hint"}, hint) : null);
  return [head("Herramientas", "Configuración", "Se guarda en proyecto.json de este proyecto y se aplica al abrirlo y en la cola."),
    el("div", {class: "grid"},
      el("div", {class: "panel"}, el("h3", {}, "Texto (Ollama)"),
        row("Modelo", model, "Los modelos instalados en Ollama."),
        row("Contexto (num_ctx)", context, "Más contexto = más RAM (con 16384 ocupa ~25 GB).")),
      el("div", {class: "panel"}, el("h3", {}, "Imagen (ComfyUI)"),
        row("URL de ComfyUI", comfy, "Solo local."),
        row("Bloom", bloom), row("Negros", blacks)),
      el("div", {class: "panel"}, el("h3", {}, "Tomas (lo que eligió el piloto)"),
        Object.entries(fields).map(([key, values]) => {
          const current = tuning[key] === null ? "ninguno" : tuning[key];
          selects[key] = el("select", {}, values.map(value => el("option", {value, selected: String(value) === String(current)}, value)));
          return row(key, selects[key]);
        })),
      el("div", {class: "panel"}, el("h3", {}, "Rutas del proyecto"),
        el("table", {class: "shots"}, el("tbody", {}, Object.entries(data.rutas).map(([key, value]) =>
          el("tr", {}, el("td", {class: "why"}, key), el("td", {style: "word-break:break-all"}, value))))))),
    el("div", {class: "row", style: "margin-top:14px"}, el("button", {class: "btn primary", onclick: async () => {
      const ajustes = {};
      for (const [key, select] of Object.entries(selects)) {
        const raw = select.value;
        ajustes[key] = raw === "ninguno" ? null : isNaN(Number(raw)) ? raw : Number(raw);
      }
      try {
        await api("/api/config", {config: {ollama_modelo: model.value, num_ctx: Number(context.value), comfy_url: comfy.value,
          bloom: bloom.value, negros: blacks.value}, ajustes});
        toast("Configuración guardada");
      } catch (error) { toast("Error: " + error.message); }
    }}, "Guardar configuración"))];
}
