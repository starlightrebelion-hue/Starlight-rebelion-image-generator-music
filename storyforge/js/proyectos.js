// Proyecto activo: elegir, nuevo, guardar (en su carpeta), guardar una copia en otra carpeta, cargar e importar DF.
import {$, el, api, toast} from "./ui.js";

const slug = name => name.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "proyecto";

export async function projectMenu() {
  const data = await api("/api/proyectos");
  const select = $("#project");
  select.replaceChildren(...data.proyectos.map(project =>
    el("option", {value: project.id, selected: project.id === data.activo}, project.nombre)));
  const active = data.proyectos.find(item => item.id === data.activo) || {};
  $("#projectNote").replaceChildren(el("span", {title: active.carpeta || ""}, active.nota || "Carpeta: " + (active.carpeta || "").split("\\").slice(-2).join("\\")));
  select.onchange = async () => {
    try {
      await api("/api/proyecto_activo", {id: select.value});
      toast("Proyecto abierto");
      location.hash = "#overview";
      location.reload();
    } catch (error) { toast("Error: " + error.message); select.value = data.activo; }
  };
  $("#projectActions").replaceChildren(
    el("button", {class: "btn sm primary", title: "Guarda en la carpeta del proyecto (y deja una copia del guion en versiones/)", onclick: async () => {
      try {
        const result = await api("/api/proyecto_guardar_aqui", {});
        toast("Guardado en " + result.carpeta);
        window.sfGo("carpetas");
      } catch (error) { toast("Error: " + error.message); }
    }}, "Guardar"),
    el("button", {class: "btn sm", onclick: () => window.sfGo("carpetas")}, "Carpetas"),
    el("button", {class: "btn sm", onclick: () => openForm("nuevo", active, data)}, "Nuevo"),
    el("button", {class: "btn sm", onclick: () => openForm("copia", active, data)}, "Copia en…"),
    el("button", {class: "btn sm", onclick: () => openForm("cargar", active, data)}, "Cargar"),
    el("button", {class: "btn sm", onclick: () => openForm("importar", active, data)}, "Importar DF"));
}

function openForm(kind, active, data) {
  const drawer = $("#drawer");
  const base = (data.carpeta_proyectos || "").replace(/\\$/, "");
  const name = el("input", {placeholder: "Nombre del proyecto", value: kind === "copia" ? `${active.nombre || ""} (copia)` : ""});
  const folder = el("input", {placeholder: kind === "importar" ? "C:\\canal starlight rebelion\\projects\\DF_005" : "C:\\carpeta\\del\\proyecto"});
  const preview = el("p", {class: "why"});
  const ideaText = el("textarea", {placeholder: "La idea en una o dos frases (después se genera la premisa)"});
  const showPreview = () => {
    if (kind === "nuevo" || kind === "copia") {
      const target = folder.value.trim() || `${base}\\${slug(name.value || "proyecto")}`;
      preview.textContent = `Se ${kind === "nuevo" ? "crea" : "copia"} en: ${target}  (con proyecto.json, universo.json, guion.json, temas\\, direccion\\, referencias\\, revisiones\\, versiones\\, exportes\\)`;
    }
  };
  name.oninput = showPreview;
  folder.oninput = showPreview;
  const titles = {nuevo: "Nuevo proyecto", copia: "Guardar una copia en otra carpeta", cargar: "Cargar un proyecto desde su carpeta",
    importar: "Importar un proyecto de Doble Fondo"};
  const help = {
    nuevo: "Cada proyecto tiene su propia carpeta. Si no elegís una, va a la carpeta de proyectos de StoryForge.",
    copia: "Arma una carpeta completa e independiente con todo el proyecto y la registra como proyecto nuevo (sirve para respaldarlo, llevarlo a otra máquina o pasar a trabajar en otra carpeta). Podés elegir una carpeta vacía que ya exista.",
    cargar: "Elegí la carpeta de un proyecto de StoryForge (la que tiene proyecto.json y universo.json).",
    importar: "Una carpeta de C:\\canal starlight rebelion\\projects (por ejemplo DF_005). Se crea un proyecto nuevo con su propia carpeta; el original no se toca.",
  };
  const submit = async () => {
    try {
      if (kind === "nuevo") {
        if (!name.value.trim()) return toast("Poné un nombre");
        await api("/api/proyecto_nuevo", {nombre: name.value, idea: ideaText.value, carpeta: folder.value || null});
      } else if (kind === "copia") {
        const target = folder.value.trim() || `${base}\\${slug(name.value || "copia")}`;
        const result = await api("/api/proyecto_guardar", {carpeta: target, nombre: name.value});
        drawer.replaceChildren(
          el("button", {class: "btn sm close", onclick: () => drawer.classList.remove("open")}, "Cerrar ✕"),
          el("h2", {}, "Copia guardada"),
          el("p", {}, "Quedó como un proyecto nuevo, con su propia carpeta:"), el("p", {}, el("b", {style: "word-break:break-all"}, result.carpeta)),
          el("p", {class: "why"}, "El proyecto que tenías abierto no cambió. Si querés seguir trabajando en la copia, abrila:"),
          el("div", {class: "row"},
            el("button", {class: "btn primary", onclick: async () => { await api("/api/proyecto_activo", {id: result.id}); location.hash = "#carpetas"; location.reload(); }}, "Abrir la copia"),
            el("button", {class: "btn", onclick: () => drawer.classList.remove("open")}, "Seguir en el actual")));
        return;
      } else if (kind === "importar") {
        if (!folder.value.trim()) return toast("Elegí la carpeta DF_xxx");
        const result = await api("/api/importar_df", {carpeta: folder.value});
        toast(`Importado: ${result.planos} planos, ${result.imagenes} imágenes`);
        await api("/api/proyecto_activo", {id: result.id});
      } else {
        if (!folder.value.trim()) return toast("Elegí la carpeta");
        await api("/api/proyecto_cargar", {carpeta: folder.value});
      }
      location.hash = kind === "nuevo" ? "#idea" : "#carpetas";
      location.reload();
    } catch (error) { toast("Error: " + error.message); }
  };
  drawer.replaceChildren(
    el("button", {class: "btn sm close", onclick: () => drawer.classList.remove("open")}, "Cerrar ✕"),
    el("h2", {}, titles[kind]), el("p", {class: "why"}, help[kind]),
    ["nuevo", "copia"].includes(kind) ? el("div", {class: "field"}, el("label", {}, "Nombre"), name) : null,
    el("div", {class: "field"}, el("label", {}, ["nuevo", "copia"].includes(kind) ? "Carpeta (opcional)" : "Carpeta"), folder),
    preview,
    kind === "nuevo" ? el("div", {class: "field"}, el("label", {}, "Idea"), ideaText) : null,
    el("button", {class: "btn primary", onclick: submit}, titles[kind]),
    el("h3", {style: "margin-top:18px"}, "Proyectos registrados"),
    el("table", {class: "shots"}, el("tbody", {}, data.proyectos.map(project => el("tr", {},
      el("td", {}, el("b", {}, project.nombre)), el("td", {class: "why", style: "word-break:break-all"}, project.carpeta || ""))))));
  showPreview();
  drawer.classList.add("open");
}
