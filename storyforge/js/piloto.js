// Piloto: grillas de prueba de Kontext y de la pasada de estilo, y el formulario para guardar los ganadores.
import {el, api, head, toast, zoom} from "./ui.js";

export async function piloto() {
  const data = await api("/api/piloto");
  const settings = data.ajustes;
  const fields = {modo: ["stitch", "chain"], lora: ["glif90", "ninguno"], persona_ref: ["vestuario", "retrato"],
    denoise: [0.3, 0.4, 0.5], hires_denoise: [0.3, "ninguno"]};
  const selects = {};
  const form = el("div", {class: "settings"},
    Object.entries(fields).map(([key, values]) => {
      const current = settings[key] === null ? "ninguno" : settings[key];
      selects[key] = el("select", {}, values.map(value => el("option", {value, selected: String(value) === String(current)}, value)));
      return el("label", {}, key, selects[key]);
    }),
    el("button", {class: "btn primary", onclick: async () => {
      const values = {};
      for (const [key, select] of Object.entries(selects)) {
        const raw = select.value;
        values[key] = raw === "ninguno" ? null : isNaN(Number(raw)) ? raw : Number(raw);
      }
      await api("/api/ajustes", {ajustes: values});
      toast("Ajustes guardados: las tomas nuevas usan estos valores");
    }}, "Guardar ganadores"));
  const names = {A: "A · Referencias base (Z-Image)", B: "B · Composición con Kontext", C: "C · Pasada de estilo", hojas: "Hojas de contacto"};
  const runs = data.corridas.map(run => [el("h2", {}, `Corrida ${run.carpeta} (${run.imagenes} imágenes)`),
    Object.entries(run.etapas).map(([stage, images]) => [el("h3", {}, names[stage] || stage),
      el("div", {class: "pilot"}, images.map(image => el("figure", {},
        el("img", {src: image.url, loading: "lazy", onclick: () => zoom(image.url), alt: ""}), el("figcaption", {}, image.nombre))))])]);
  return [head("F0", "Piloto", "Comparar modos de Kontext (pegado / encadenado, con o sin LoRA, retrato o vestuario) y la fuerza de la pasada de estilo. Elegí los ganadores y guardalos."),
    form, runs.length ? runs : el("div", {class: "empty"}, "Todavía no se corrió el piloto (python piloto_referencias.py).")];
}
