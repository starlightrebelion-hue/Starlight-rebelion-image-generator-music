// Export: titulo, descripcion y etiquetas de YouTube por tema, listos para copiar.
import {el, api, head, toast} from "./ui.js";

export async function exportPage() {
  const data = await api("/api/temas");
  const copy = value => () => navigator.clipboard.writeText(value).then(() => toast("Copiado"));
  const rows = data.temas.filter(song => song.titulo_youtube).map(song => {
    const tags = (song.etiquetas || []).join(", ");
    return el("div", {class: "stat", style: "margin-bottom:12px"},
      el("div", {class: "eyebrow"}, song.nombre),
      el("div", {class: "row", style: "justify-content:space-between;margin:6px 0"}, el("h3", {style: "margin:0"}, song.titulo_youtube),
        el("button", {class: "btn sm", onclick: copy(song.titulo_youtube)}, "Copiar")),
      el("details", {}, el("summary", {}, "Descripción"),
        el("p", {style: "white-space:pre-wrap"}, song.descripcion || ""),
        el("button", {class: "btn sm", onclick: copy(song.descripcion || "")}, "Copiar descripción")),
      el("div", {class: "tags", style: "margin-top:8px"}, (song.etiquetas || []).map(tag => el("span", {}, tag)),
        el("button", {class: "btn sm", onclick: copy(tags)}, "Copiar etiquetas")));
  });
  return [head("Export", "SEO por tema", "Título, descripción y etiquetas listos para YouTube (los arma el agente SEO con los datos del canal)."),
    rows.length ? rows : el("div", {class: "empty"}, "Ningún tema tiene SEO todavía.")];
}
