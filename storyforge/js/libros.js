// Libros de Doble Fondo (solo lectura): estilos de guionista, fichas y busqueda de pasajes para el tono.
import {el, api, head, toast} from "./ui.js";

let query = "";
let results = null;

export async function libros() {
  const data = await api("/api/libros");
  if (data.error_libros) return [head("Herramientas", "Libros", ""), el("div", {class: "empty"}, "No se encontraron los libros de Doble Fondo (C:\\canal starlight rebelion\\scripts\\libros.py).")];
  const style = el("select", {}, el("option", {value: ""}, "sin estilo (los agentes no reciben libros)"),
    Object.entries(data.estilos).map(([id, item]) => el("option", {value: id, selected: id === data.elegido}, `${item.nombre || id} — ${item.genero || ""}`)));
  const search = el("input", {value: query, placeholder: "buscar un pasaje (ej: entrega en un guardarropa de noche)", style: "flex:1"});
  const chosen = data.estilos[data.elegido] || null;
  return [
    head("Herramientas", "Libros", "Los libros que indexó el Estudio de Doble Fondo. El estilo elegido le pasa a los agentes de guion fichas y pasajes como referencia de TONO (nunca para copiar frases, nombres ni tramas)."),
    el("div", {class: "panel", style: "margin-bottom:12px"},
      el("div", {class: "row"}, el("b", {}, "Estilo de guionista del proyecto"), style,
        el("button", {class: "btn primary", onclick: async () => { await api("/api/config", {config: {estilo_guion: style.value || null}}); toast("Estilo guardado"); window.sfRender(true); }}, "Usar")),
      chosen ? el("p", {class: "why"}, `${chosen.notas || ""} · Ficción: ${(chosen.ficcion || []).join(", ")} · Oficio: ${(chosen.oficio || []).join(", ")}`) : null),
    el("div", {class: "row", style: "margin-bottom:10px"}, search,
      el("button", {class: "btn", onclick: async () => {
        query = search.value.trim();
        results = query ? (await api(`/api/libros_buscar?q=${encodeURIComponent(query)}${data.elegido ? "&estilo=" + data.elegido : ""}`)).pasajes : null;
        window.sfRender(true);
      }}, "Buscar")),
    results ? el("div", {}, results.map(item => el("details", {class: "panel", style: "margin-bottom:6px"},
      el("summary", {}, el("b", {}, item.libro || item.titulo || "pasaje"), item.puntaje ? ` · ${item.puntaje}` : ""),
      el("p", {style: "white-space:pre-wrap"}, item.texto || "")))) : null,
    el("h2", {}, `Fichas (${data.libros.length})`),
    el("div", {class: "grid"}, data.libros.map(book => el("div", {class: "panel"},
      el("div", {class: "eyebrow"}, book.tipo || ""), el("h3", {}, book.titulo), el("div", {class: "why"}, book.autor || ""),
      Object.entries(book.ficha).map(([key, value]) => el("p", {class: "why"}, el("b", {}, key + ": "), Array.isArray(value) ? value.join(" · ") : String(value).slice(0, 400)))))),
  ];
}
