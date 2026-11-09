// Personajes: ficha de produccion como "personajes ficha.png" (retrato anotado, giro de 5 vistas, cine, expresiones,
// telas y objetos). Cada imagen abre su tarjeta de revision; la ficha completa se genera a pedido por personaje.
import {el, api, head, toast, queued, slot, badge, confirmBox, zoom, currentCandidate} from "./ui.js";

let selected = null;
const VIEW_NAMES = {frente: "Frente", tres_cuartos: "3/4 frente", perfil: "Perfil", tres_cuartos_espalda: "3/4 espalda", espalda: "Espalda"};
const FACE_NAMES = {neutral: "Neutral", determinada: "Determinada", sonrisa: "Sonrisa", enojo: "Enojo", preocupacion: "Preocupación", sorpresa: "Sorpresa"};

export async function personajes(params = {}) {
  const list = await api("/api/personajes");
  if (params.id) selected = params.id;
  if (!selected) selected = list.personajes[0] && list.personajes[0].id;
  const picker = el("div", {class: "char-list"}, list.personajes.map(person =>
    el("button", {class: "char-pick" + (person.id === selected ? " on" : ""), onclick: () => { selected = person.id; window.sfGo("personajes"); }},
      person.retrato ? el("img", {src: person.retrato, loading: "lazy", alt: ""}) : el("div", {class: "ph"}),
      el("div", {}, el("b", {}, person.nombre), `${person.alias || ""} · ${person.edad || ""}`, el("br"), badge(person.estado),
        person.temas.length ? el("span", {class: "why"}, ` ${person.temas.length} temas`) : null))));
  const sheet = selected ? await characterSheet(selected) : el("div", {class: "empty"}, "Sin personajes.");
  return [head("Casting", "Personajes", "Ficha de producción de cada personaje. Tocá una imagen para aprobarla, rechazarla con una nota o subir otra."), picker, sheet];
}

async function characterSheet(id) {
  const c = await api("/api/personaje?id=" + encodeURIComponent(id));
  const d = c.datos;
  const refresh = () => window.sfRender(true);
  const portraitOk = c.retrato.estado === "aprobado";
  const waiting = [...c.vistas, ...c.expresiones, c.cinematico, ...c.telas, c.hoja].filter(node => node.estado === "a pedido").length;
  const request = el("button", {class: "btn primary", disabled: !portraitOk || c.ficha_pedida, title: portraitOk ? "" : "Primero aprobá el retrato",
    onclick: () => confirmBox(`Se generan con Kontext a partir del retrato aprobado de ${d.nombre}:\n· 5 vistas de giro\n· 6 expresiones\n· 1 retrato de cine\n· 3 telas\n· la hoja de producción (cuando apruebes todo)\n\nEsperan tu aprobación como el resto.`,
      async () => { const r = await api("/api/ficha_pedir", {personaje: id}); queued(r, `Ficha (${r.ids.length} imágenes)`); refresh(); },
      "Generar ficha completa")}, c.ficha_pedida ? "Ficha pedida" : "Generar ficha completa");
  const sheetNode = c.hoja;
  const sheetImage = currentCandidate(sheetNode);
  const notes = [["Aspecto", d.aspecto], ["Vestuario", d.vestuario], ["Implantes", (d.implantes || []).join(", ")], ["Oficio", d.oficio]];
  const editable = (field, label, value) => {
    const input = el("textarea", {class: "cs-edit", value: value || ""});
    return el("details", {}, el("summary", {}, el("b", {}, label), " — editar"), input,
      el("button", {class: "btn sm", style: "margin-top:4px", onclick: async () => {
        await api("/api/texto", {tipo: "personaje", id, campo: field, valor: input.value});
        toast(`${label} guardado: lo que depende queda desactualizado`); refresh(); }}, "Guardar"));
  };
  return el("div", {},
    !c.ficha_pedida && waiting ? el("div", {class: "cs-pending"},
      `La ficha completa de ${d.nombre} se genera a pedido (${waiting} imágenes). ${portraitOk ? "El retrato está aprobado: ya se puede pedir." : "Primero aprobá el retrato."}`) : null,
    el("div", {class: "charsheet"},
      el("header", {class: "cs-head"},
        el("div", {},
          el("div", {class: "cs-role"}, "Ficha de personaje · Neo-Kansai Delta"),
          el("h1", {}, d.nombre, d.alias ? [", ", el("i", {}, d.alias)] : null),
          el("div", {class: "cs-sub"}, [d.arquetipo, d.edad && `${d.edad} años`, d.genero].filter(Boolean).join(" · "))),
        el("div", {class: "cs-actions"}, request,
          sheetImage ? el("button", {class: "btn", onclick: () => zoom(sheetImage.url)}, "Ver hoja") : null,
          el("button", {class: "btn", onclick: () => window.print()}, "Imprimir / PDF"))),
      el("div", {class: "cs-top"},
        el("div", {},
          slot(c.retrato, "portrait", "RETRATO", refresh),
          el("div", {class: "cs-caption"}, "Retrato de referencia"),
          el("div", {class: "cs-notes"}, notes.filter(([, v]) => v).map(([k, v]) => el("div", {}, el("b", {}, k), el("span", {}, v))))),
        el("div", {},
          el("div", {class: "cs-views-row"}, Object.entries(VIEW_NAMES).map(([key, label]) => {
            const node = c.vistas.find(item => item.id.endsWith("__" + key));
            return el("figure", {}, slot(node, "view", label.toUpperCase(), refresh), el("figcaption", {}, label));
          })),
          el("div", {class: "cs-caption"}, "Giro del personaje · vestuario completo"))),
      el("div", {class: "cs-mid"},
        el("div", {}, slot(c.cinematico, "cine", "RETRATO DE CINE", refresh), el("div", {class: "cs-caption"}, "Cinematic portrait shot")),
        el("div", {}, el("div", {class: "cs-caption", style: "text-align:left"}, "Estudios de cara · expresiones"),
          el("div", {class: "cs-faces-grid"}, Object.entries(FACE_NAMES).map(([key, label]) => {
            const node = c.expresiones.find(item => item.id.endsWith("__" + key));
            return el("div", {}, slot(node, "face", label, refresh), el("div", {class: "cs-caption"}, label));
          })))),
      el("div", {class: "cs-bottom"},
        el("div", {}, el("h3", {}, "Vestuario y telas"),
          el("div", {class: "cs-item"}, slot(c.vestuario, "small", "VEST.", refresh), el("div", {}, el("b", {}, "Vestuario"), el("br"), d.vestuario)),
          c.telas.map(node => el("div", {class: "cs-item"}, slot(node, "small", "TELA", refresh), el("div", {}, node.info.tela || "")))),
        el("div", {}, el("h3", {}, "Objetos de firma"),
          c.objetos.map(node => el("div", {class: "cs-item"}, slot(node, "small", "OBJ.", refresh), el("div", {}, node.info.objeto || ""))))),
      el("div", {class: "cs-desc"},
        el("div", {}, el("h3", {}, "Historia"),
          el("p", {}, d.historia), el("p", {}, el("b", {}, "Deseo: "), d.deseo), el("p", {}, el("b", {}, "Miedo: "), d.miedo),
          el("p", {}, el("b", {}, "Contradicción: "), d.contradiccion), el("p", {}, el("b", {}, "Secreto: "), d.secreto)),
        el("div", {}, el("h3", {}, "Arco en los temas"),
          (d.arco || []).length ? el("ul", {class: "why", style: "color:#3a3020"}, d.arco.map(step => el("li", {}, el("b", {}, `${step.tema} ${step.titulo}: `), step.que_hizo)))
            : el("p", {}, "Todavía sin temas."),
          el("h3", {style: "margin-top:12px"}, "Escenas"),
          el("div", {class: "row"}, c.escenas.map(scene => el("button", {class: "btn sm", onclick: () => window.sfGo("guion", {semilla: scene.semilla})}, `${scene.semilla} ${scene.titulo}`))))),
      el("div", {class: "cs-desc"},
        el("div", {}, el("h3", {}, "Editar textos"), editable("aspecto", "Aspecto", d.aspecto), editable("vestuario", "Vestuario", d.vestuario),
          editable("historia", "Historia", d.historia)),
        el("div", {}, el("h3", {}, " "), editable("deseo", "Deseo", d.deseo), editable("miedo", "Miedo", d.miedo),
          editable("secreto", "Secreto", d.secreto)))));
}
