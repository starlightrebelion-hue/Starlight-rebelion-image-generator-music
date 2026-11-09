// Edicion (timeline de la v5): un clip por tema en el orden de publicacion. Se reordena arrastrando, se marca
// "publicar" y la fecha. Sin render: se renderiza solo cuando lo pidas.
import {el, api, head, toast, zoom} from "./ui.js";

const SCALE = 0.35;   // pixeles por segundo
let selected = null;

export async function edicion() {
  const data = await api("/api/edicion");
  const clips = data.clips;
  if (!selected || !clips.some(clip => clip.semilla === selected)) selected = clips.length ? clips[0].semilla : null;
  const total = clips.reduce((sum, clip) => sum + clip.duracion, 0);
  let dragging = null;
  const saveOrder = async () => {
    await api("/api/edicion", {orden: clips.map(clip => clip.semilla)});
    toast("Orden guardado");
    window.sfRender(true);
  };
  const video = el("div", {class: "track"}, el("div", {class: "track-label"}, "V1 · fondo"),
    clips.map((clip, index) => el("div", {class: "clip" + (clip.semilla === selected ? " on" : "") + (clip.publicar ? " pub" : ""), draggable: "true",
      style: `width:${Math.max(40, clip.duracion * SCALE)}px;${clip.miniatura ? `background-image:url('${clip.miniatura}')` : ""}`,
      title: `${clip.titulo} · ${Math.round(clip.duracion)} s`,
      onclick: () => { selected = clip.semilla; window.sfRender(true); },
      ondragstart: () => { dragging = index; },
      ondragover: event => { event.preventDefault(); event.currentTarget.classList.add("drop"); },
      ondragleave: event => event.currentTarget.classList.remove("drop"),
      ondrop: event => {
        event.preventDefault();
        if (dragging === null || dragging === index) return;
        const [moved] = clips.splice(dragging, 1);
        clips.splice(index, 0, moved);
        dragging = null;
        saveOrder();
      }}, el("span", {}, clip.titulo))));
  const audio = el("div", {class: "track"}, el("div", {class: "track-label"}, "A1 · tema"),
    clips.map(clip => el("div", {class: "audio", style: `width:${Math.max(40, clip.duracion * SCALE)}px`}, `${clip.paleta || ""}`)));
  const marks = [];
  for (let s = 0; s <= total; s += 600) marks.push(el("span", {style: `width:${600 * SCALE - 2}px;flex:none`}, `${Math.floor(s / 60)}:00`));
  const clip = clips.find(item => item.semilla === selected);
  const publish = clip ? el("input", {type: "checkbox", checked: clip.publicar}) : null;
  const date = clip ? el("input", {type: "date", value: clip.fecha}) : null;

  const exportProduction = async () => {
    const res = await api("/api/exportar_timeline", {
      orden: clips.map(c => c.semilla),
      publicar_solo: false // Generar todo el timeline procedimentalmente
    });
    toast(res.ok ? `Producción lanzada: ${res.total} clips en cola` : "Error al exportar");
    window.sfRender(true);
  };

  return [head("Edición", "Edición", `Orden de publicación de los temas (${clips.length} clips, ${Math.round(total / 60)} min). Arrastrá los clips para reordenar.`),
    clip ? el("div", {class: "monitor"},
      clip.miniatura ? el("img", {src: clip.miniatura, onclick: () => zoom(clip.miniatura), alt: ""}) : el("div", {class: "empty"}, "Sin fondo"),
      el("div", {class: "panel"},
        el("div", {class: "eyebrow"}, `${clip.semilla} · ${Math.round(clip.duracion)} s · ${clip.paleta || ""}`),
        el("h2", {style: "margin:4px 0"}, clip.titulo),
        el("p", {class: "why"}, clip.titulo_youtube || "Sin título de YouTube todavía."),
        el("p", {class: "why"}, clip.sinopsis),
        el("div", {class: "row"}, el("label", {class: "why"}, publish, " publicar"), date,
          el("button", {class: "btn primary", onclick: async () => {
            await api("/api/edicion", {clips: {[clip.semilla]: {publicar: publish.checked, fecha: date.value}}});
            toast("Guardado"); window.sfRender(true); }}, "Guardar")),
        el("div", {class: "row", style: "margin-top:10px"},
          el("button", {class: "btn", onclick: () => window.sfGo("guion", {semilla: clip.semilla})}, "Abrir escena"),
          el("button", {class: "btn", onclick: exportProduction, title: "Lanza la generación de todo el timeline"}, "🚀 Exportar Producción"))),
    el("div", {class: "timeline"}, el("div", {class: "ruler"}, marks), video, audio)];
}
