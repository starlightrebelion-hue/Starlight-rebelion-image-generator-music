// Etapa Audio: musica (el plan de cada tema, separado del guion), voces y fx.
import {el, api, head} from "./ui.js";

let tab = "musica";
const LABELS = {tonica: "Tónica", escala: "Escala", bpm: "BPM", duracion_seg: "Duración (s)", compases: "Compases",
  estructura: "Estructura", ensamble: "Ensamble", lead: "Lead", ambiente: "Ambiente (Pigments)", densidad: "Densidad",
  arpegio: "Arpegio", bajo: "Bajo", bateria: "Batería", progresion_verso: "Progresión verso", progresion_coro: "Progresión coro",
  contorno: "Contorno", melodia: "Melodía", acordes: "Acordes", efecto: "Efecto", reverb: "Reverb", delay: "Delay"};

export async function audio() {
  const tabs = el("div", {class: "tabs"}, [["musica", "Música"], ["voces", "Voces"], ["fx", "FX"]].map(([id, label]) =>
    el("button", {class: "tab" + (tab === id ? " on" : ""), onclick: () => { tab = id; window.sfRender(true); }}, label)));
  let body;
  if (tab === "musica") {
    const data = await api("/api/musica");
    body = data.temas.length ? el("div", {class: "grid"}, data.temas.map(song => el("div", {class: "panel"},
      el("div", {class: "eyebrow"}, `${song.semilla} · ${song.bpm || "?"} BPM · ${song.tonica || ""} ${song.escala || ""}`),
      el("h3", {style: "margin:4px 0 8px"}, song.titulo || song.nombre),
      song.idea ? el("p", {class: "why"}, song.idea) : null,
      el("table", {class: "shots"}, el("tbody", {}, Object.entries(LABELS).filter(([key]) => song[key]).map(([key, label]) =>
        el("tr", {}, el("td", {class: "why"}, label), el("td", {}, String(song[key])))))),
      song.flp ? el("p", {class: "why", style: "margin-top:8px"}, "Proyecto FL: " + song.flp) : el("p", {class: "why"}, "Sin proyecto de FL."))))
      : el("div", {class: "empty"}, "Este proyecto no tiene temas con plan musical.");
  } else if (tab === "voces") {
    body = el("div", {class: "empty"}, "Voces: los diálogos salen del guion (planos con diálogo). La generación con las voces de Doble Fondo (qwen_voz) se suma en la etapa de audio siguiente.");
  } else {
    body = el("div", {class: "empty"}, "FX: lista de efectos por plano (pendiente para la etapa de audio siguiente).");
  }
  return [head("Etapa 8", "Audio", "La música de cada tema vive acá, separada del guion y de la imagen."), tabs, body];
}
