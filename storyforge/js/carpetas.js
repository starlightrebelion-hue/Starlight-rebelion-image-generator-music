// Carpetas: que guarda el proyecto y donde, con un boton para abrir cada carpeta en el Explorador.
import {el, api, head, toast} from "./ui.js";

const ICONS = {proyecto: "📄", universo: "📄", asignaciones: "📄", guion: "📄", edicion: "📄", temas: "📁", direccion: "📁",
  referencias: "📁", revisiones: "📁", versiones: "📁", exportes: "📁"};

export async function carpetas() {
  const data = await api("/api/proyecto_carpetas");
  const open = async key => {
    try { const result = await api("/api/abrir_carpeta", {clave: key}); toast("Abierta: " + result.ruta); }
    catch (error) { toast("Error: " + error.message); }
  };
  const linked = data.entradas.some(item => item.enlazada);
  return [
    head("Proyecto", `Carpetas · ${data.nombre}`, "Todo lo del proyecto vive en su carpeta. Se guarda solo mientras trabajás; el botón Guardar además deja una copia del guion en versiones/ y anota la fecha."),
    el("div", {class: "panel", style: "margin-bottom:12px"},
      el("div", {class: "row", style: "justify-content:space-between"},
        el("div", {}, el("div", {class: "why"}, "Carpeta del proyecto"), el("b", {style: "word-break:break-all"}, data.carpeta),
          el("div", {class: "why"}, data.guardado ? `Último guardado: ${data.guardado.replace("T", " ")}` : "Todavía no se usó el botón Guardar.")),
        el("div", {class: "row"},
          el("button", {class: "btn primary", onclick: async () => { await api("/api/proyecto_guardar_aqui", {}); toast("Guardado"); window.sfRender(true); }}, "Guardar ahora"),
          el("button", {class: "btn", onclick: () => open("carpeta")}, "Abrir carpeta")))),
    linked ? el("p", {class: "why"}, "Ejemplo 1 comparte universo\\ y Agente Frequency\\ con el agente musical: esas carpetas quedan donde estaban (marcadas «enlazada»). Para tener todo junto en una carpeta independiente usá «Copia en…».") : null,
    el("table", {class: "shots folders"},
      el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", {}, "Qué"), el("th", {}, "Qué guarda"), el("th", {}, "Archivos"), el("th", {}, "Dónde"), el("th", {}, ""))),
      el("tbody", {}, data.entradas.map(item => el("tr", {},
        el("td", {}, ICONS[item.clave] || "📁"),
        el("td", {}, el("b", {}, item.nombre), item.enlazada ? el("div", {}, el("span", {class: "badge"}, "enlazada")) : null),
        el("td", {class: "why"}, item.descripcion),
        el("td", {}, item.existe ? `${item.archivos} · ${item.mb} MB` : el("span", {class: "why"}, "vacío")),
        el("td", {class: "why", style: "word-break:break-all;max-width:360px"}, item.ruta),
        el("td", {}, el("button", {class: "btn sm", onclick: () => open(item.clave)}, "Abrir")))))),
    el("p", {class: "why", style: "margin-top:10px"}, "En la carpeta también hay un LEEME.md que explica lo mismo."),
  ];
}
