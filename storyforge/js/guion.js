// Etapa 3: Guion como Guion@1x.png. Izquierda la estructura (secuencias -> escenas), centro el papel en Fountain,
// derecha el detalle de la escena y sus planos. Generar = Ollama por la cola, siempre como propuesta.
import {el, api, head, toast, queued, zoom, badge, confirmBox} from "./ui.js";

let selected = null;      // id de la escena elegida
let doc = null;           // ultimo /api/guion_doc

const STATE_LABELS = {guardada: "GUARDADA", revision: "REVISIÓN", oculta: "OCULTA"};
const SHOT_TYPES = ["PG", "PC", "PA", "PM", "PP", "PPP", "escorzo", "inserto", "POV"];

async function generate(tipo, objetivo, label) {
  confirmBox(`${label}\n\nLo hace Ollama en la cola; queda como propuesta para aceptar o descartar (no pisa nada).\nSi Ollama no responde, el pedido queda en fallo: no se inventa nada.`,
    async () => {
      const result = await api("/api/generar", {tipo, objetivo});
      queued(result, label);
    }, label);
}

async function saveStructure(structure, message = "Guardado") {
  const result = await api("/api/guion_doc", {estructura: structure});
  toast(`${message} · versión ${result.version}`);
  window.sfRender(true);
}

function allScenes(structure) {
  return structure.secuencias.flatMap(sequence => sequence.escenas.map(scene => ({sequence, scene})));
}

export async function guion(params = {}) {
  doc = await api("/api/guion_doc");
  const structure = doc.estructura;
  const scenes = allScenes(structure);
  if (params.semilla) selected = `t${params.semilla}`;
  if (!selected || !scenes.some(item => item.scene.id === selected)) selected = scenes.length ? scenes[0].scene.id : null;
  const proposals = Object.entries(doc.propuestas || {});
  return [
    head("Etapa 3", "Guion", "Premisa → secuencias → escenas → planos. Editá el texto en el papel o generá cada paso con Ollama.",
      el("div", {class: "row"},
        el("button", {class: "btn", onclick: () => generate("premisa", null, "Generar la premisa desde la idea")}, "✦ Premisa"),
        el("button", {class: "btn", onclick: () => generate("secuencias", null, "Generar las secuencias desde la premisa")}, "✦ Secuencias"),
        el("span", {class: "why"}, doc.premisa.logline ? `Premisa: ${doc.premisa.logline}` : "Sin premisa todavía (etapa 2)."))),
    proposals.length ? proposalsPanel(proposals) : null,
    el("div", {class: "script3"}, structurePanel(structure), paperPanel(structure), detailPanel(structure))];
}

function proposalsPanel(proposals) {
  return el("div", {class: "proposal"}, el("h3", {}, `Propuestas de Ollama (${proposals.length})`),
    proposals.map(([key, item]) => {
      const answer = item.propuesta;
      let preview;
      if (item.tipo === "premisa") preview = el("p", {class: "why"}, el("b", {}, answer.titulo || ""), " — ", answer.logline || "");
      else if (item.tipo === "secuencias") preview = el("ol", {class: "why"}, (answer.secuencias || []).map(seq => el("li", {}, el("b", {}, seq.titulo), " — ", seq.sinopsis)));
      else if (item.tipo === "escenas") preview = el("ol", {class: "why"}, (answer.escenas || []).map(scene => el("li", {},
        el("b", {}, `${scene.int_ext || ""} ${scene.lugar} - ${scene.momento}`), " — ", scene.accion)));
      else preview = el("ol", {class: "why"}, (answer.planos || []).map(shot => el("li", {}, el("b", {}, shot.tipo), " — ", shot.que_se_ve, ": ", shot.accion)));
      return el("div", {class: "panel", style: "margin-bottom:8px"},
        el("div", {class: "row", style: "justify-content:space-between"}, el("b", {}, `${item.tipo}${item.objetivo ? " · " + item.objetivo : ""}`), el("span", {class: "why"}, item.fecha)),
        preview,
        el("div", {class: "row"},
          el("button", {class: "btn ok", onclick: async () => { await api("/api/propuesta_guion", {clave: key, accion: "aceptar"}); toast("Aceptada: se agregó al guion"); window.sfRender(true); }}, "Aceptar"),
          el("button", {class: "btn bad", onclick: async () => { await api("/api/propuesta_guion", {clave: key, accion: "descartar"}); window.sfRender(true); }}, "Descartar")));
    }));
}

function structurePanel(structure) {
  let number = 0;
  return el("div", {class: "script-side"},
    el("div", {class: "row", style: "justify-content:space-between"}, el("div", {class: "eyebrow"}, "Estructura"),
      el("button", {class: "btn sm", onclick: () => {
        structure.secuencias.push({id: "", titulo: `Secuencia ${structure.secuencias.length + 1}`, sinopsis: "", escenas: []});
        saveStructure(structure, "Secuencia agregada"); }}, "+ Secuencia")),
    el("p", {class: "why"}, "Lo que ves acá es el mismo guion: cada fila es una escena."),
    structure.secuencias.map(sequence => el("details", {open: true, class: "seq"},
      el("summary", {}, el("b", {}, sequence.titulo), el("span", {class: "tag-sm"}, `${sequence.escenas.length} esc.`)),
      sequence.sinopsis ? el("div", {class: "why", style: "margin:2px 0 4px 14px"}, sequence.sinopsis) : null,
      sequence.escenas.map(scene => {
        number += 1;
        return el("div", {class: "scene-item" + (scene.id === selected ? " on" : ""), onclick: () => { selected = scene.id; window.sfRender(true); }},
          scene.miniatura || scene.miniatura_lugar ? el("img", {src: scene.miniatura || scene.miniatura_lugar, loading: "lazy", alt: ""}) : el("div", {class: "ph"}),
          el("span", {style: "flex:1"}, `${number} ${scene.int_ext || ""} ${scene.lugar || ""} – ${scene.momento || ""}`),
          el("span", {class: "state-" + (scene.estado || "guardada")}, STATE_LABELS[scene.estado] || "GUARDADA"));
      }),
      el("div", {class: "row", style: "margin:4px 0 8px 14px"},
        el("button", {class: "btn sm", onclick: () => {
          sequence.escenas.push({id: "", int_ext: "INT.", lugar: "LUGAR", momento: "NOCHE", accion: "", dialogos: [], elenco: [], estado: "revision", planos: []});
          saveStructure(structure, "Escena agregada"); }}, "+ Escena"),
        el("button", {class: "btn sm", onclick: () => generate("escenas", sequence.id, `Generar las escenas de "${sequence.titulo}"`)}, "✦ Escenas")))),
    el("p", {class: "why", style: "margin-top:12px"}, "Estados: Guardada · Revisión · Oculta = no aparece en el papel ni en el storyboard."));
}

function paperPanel(structure) {
  const paper = el("textarea", {class: "paper", spellcheck: "false", value: doc.fountain});
  const exec = command => { paper.focus(); document.execCommand(command); };
  const moveScene = delta => {
    for (const sequence of structure.secuencias) {
      const index = sequence.escenas.findIndex(scene => scene.id === selected);
      if (index < 0) continue;
      const target = index + delta;
      if (target < 0 || target >= sequence.escenas.length) return toast("No se puede mover más");
      [sequence.escenas[index], sequence.escenas[target]] = [sequence.escenas[target], sequence.escenas[index]];
      return saveStructure(structure, "Escena movida");
    }
  };
  const duplicate = () => {
    for (const sequence of structure.secuencias) {
      const index = sequence.escenas.findIndex(scene => scene.id === selected);
      if (index < 0) continue;
      const copy = JSON.parse(JSON.stringify(sequence.escenas[index]));
      copy.id = ""; delete copy.tema; copy.estado = "revision";
      copy.planos = (copy.planos || []).map(shot => ({...shot, id: "", estado: "pendiente"}));
      sequence.escenas.splice(index + 1, 0, copy);
      return saveStructure(structure, "Escena duplicada");
    }
  };
  const download = async format => {
    const data = await api("/api/guion_export?formato=" + format);
    const link = el("a", {href: URL.createObjectURL(new Blob([data.texto], {type: "text/plain"})), download: `${data.nombre}.${format}`});
    link.click();
  };
  return el("div", {class: "paper-wrap"},
    el("div", {class: "toolbar"},
      el("button", {class: "btn sm", onclick: () => exec("cut")}, "Cortar"),
      el("button", {class: "btn sm", onclick: () => exec("copy")}, "Copiar"),
      el("button", {class: "btn sm", onclick: async () => { paper.focus(); try { document.execCommand("insertText", false, await navigator.clipboard.readText()); } catch (error) { toast("El navegador no dejó pegar: usá Ctrl+V"); } }}, "Pegar"),
      el("span", {class: "sep"}),
      el("button", {class: "btn sm", onclick: () => exec("undo")}, "Deshacer"),
      el("button", {class: "btn sm", onclick: () => exec("redo")}, "Rehacer"),
      el("span", {class: "sep"}),
      el("button", {class: "btn sm", onclick: () => moveScene(-1)}, "Mover ↑"),
      el("button", {class: "btn sm", onclick: () => moveScene(1)}, "Mover ↓"),
      el("button", {class: "btn sm", onclick: duplicate}, "Duplicar"),
      el("span", {class: "sep"}),
      doc.versiones.length ? el("select", {onchange: async event => {
        if (!event.target.value) return;
        await api("/api/guion_version", {nombre: event.target.value}); toast("Versión restaurada (la actual quedó guardada)"); window.sfRender(true); }},
        el("option", {value: ""}, `Versiones (${doc.versiones.length})`), doc.versiones.map(name => el("option", {value: name}, name.replace("guion_", "").replace(".json", "")))) : null,
      el("button", {class: "btn sm", onclick: () => download("fountain")}, ".fountain"),
      el("button", {class: "btn sm", onclick: () => download("fdx")}, ".fdx"),
      el("button", {class: "btn sm primary", onclick: async () => {
        try {
          const result = await api("/api/guion_doc", {fountain: paper.value});
          toast(`Guion guardado · versión ${result.version}`); paper.blur(); window.sfRender(true);
        } catch (error) { toast("Error: " + error.message); }
      }}, "Guardar")),
    paper,
    el("p", {class: "why"}, "Formato: «# Secuencia [[s1]]» abre una secuencia; «EXT. LUGAR - NOCHE #e1#» una escena (el #id# la conecta con sus planos); NOMBRE en mayúsculas y abajo el diálogo."));
}

function detailPanel(structure) {
  const found = allScenes(structure).find(item => item.scene.id === selected);
  if (!found) return el("div", {class: "panel"}, el("div", {class: "empty"}, "Elegí o agregá una escena."));
  const {sequence, scene} = found;
  const people = doc.personajes;
  const cast = new Set(scene.elenco || []);
  const castBox = el("div", {class: "tags"}, people.map(person => el("label", {class: "why", style: "white-space:nowrap"},
    el("input", {type: "checkbox", checked: cast.has(person.id), onchange: event => { event.target.checked ? cast.add(person.id) : cast.delete(person.id); }}), " ", person.nombre)));
  const place = el("select", {}, el("option", {value: ""}, "— lugar del texto —"),
    doc.lugares.map(item => el("option", {value: item.id, selected: item.id === scene.lugar_id}, item.nombre)));
  const moment = el("input", {value: scene.momento || ""});
  const state = el("select", {}, Object.entries(STATE_LABELS).map(([value, label]) => el("option", {value, selected: value === (scene.estado || "guardada")}, label)));
  const notes = el("textarea", {value: scene.notas || "", placeholder: "Notas de dirección para esta escena"});
  const shotsBox = el("div", {});
  const shots = JSON.parse(JSON.stringify(scene.planos || []));
  const drawShots = () => shotsBox.replaceChildren(...shots.map((shot, index) => el("div", {class: "shot-row"},
    el("select", {onchange: e => (shot.tipo = e.target.value)}, SHOT_TYPES.map(type => el("option", {value: type, selected: type === shot.tipo}, type))),
    el("input", {value: shot.que_se_ve || "", placeholder: "qué se ve", oninput: e => (shot.que_se_ve = e.target.value)}),
    el("input", {value: shot.accion || "", placeholder: "acción", oninput: e => (shot.accion = e.target.value)}),
    el("input", {type: "number", value: shot.duracion || "", placeholder: "s", style: "width:56px", oninput: e => (shot.duracion = Number(e.target.value) || null)}),
    el("button", {class: "btn sm bad", onclick: () => { shots.splice(index, 1); drawShots(); }}, "✕"))));
  drawShots();
  const placeInfo = doc.lugares.find(item => item.id === scene.lugar_id);
  const save = () => {
    const chosen = doc.lugares.find(item => item.id === place.value);
    if (chosen && chosen.id !== scene.lugar_id) scene.lugar = chosen.nombre.toUpperCase();   // el encabezado sigue al lugar
    Object.assign(scene, {elenco: [...cast], lugar_id: place.value || null, momento: moment.value, estado: state.value, notas: notes.value, planos: shots});
    return saveStructure(structure, "Escena guardada");
  };
  return el("div", {class: "detail-side"},
    el("div", {class: "eyebrow"}, `Escena · ${sequence.titulo}`),
    el("h3", {style: "margin:4px 0 10px"}, `${scene.int_ext || ""} ${scene.lugar || ""} – ${scene.momento || ""}`),
    scene.miniatura || (placeInfo && placeInfo.miniatura) ? el("img", {class: "detail-img", src: scene.miniatura || placeInfo.miniatura, alt: "", onclick: () => zoom(scene.miniatura || placeInfo.miniatura)}) : null,
    el("div", {class: "card-mini"}, el("div", {class: "why"}, "Premisa vinculada"), el("b", {}, doc.premisa.logline || "[sin premisa]")),
    el("div", {class: "card-mini"}, el("div", {class: "why"}, "Elenco"), castBox),
    el("div", {class: "card-mini"}, el("div", {class: "why"}, "Ambiente"), place, el("div", {class: "row", style: "margin-top:6px"}, el("span", {class: "why"}, "Momento"), moment),
      scene.tema ? el("p", {class: "why"}, `Tema ${scene.tema}${scene.gesto ? " · gesto: " + scene.gesto : ""}`) : null),
    el("div", {class: "card-mini"}, el("div", {class: "why"}, "Notas · Dirección"), notes),
    el("div", {class: "card-mini"}, el("div", {class: "row", style: "justify-content:space-between"}, el("div", {class: "why"}, `Planos (${shots.length})`),
      el("div", {class: "row"},
        el("button", {class: "btn sm", onclick: () => { shots.push({id: "", tipo: "PM", que_se_ve: "", accion: "", estado: "pendiente"}); drawShots(); }}, "+ plano"),
        el("button", {class: "btn sm", onclick: () => generate("planos", scene.id, `Generar los planos de la escena ${scene.lugar}`)}, "✦ Planos"))),
      shotsBox),
    el("div", {class: "row"}, el("span", {class: "why"}, "Estado"), state),
    el("div", {class: "row", style: "margin-top:10px"},
      el("button", {class: "btn primary", onclick: save}, "Guardar escena"),
      el("button", {class: "btn", onclick: () => window.sfGo("tecnico", scene.tema ? {semilla: scene.tema} : {id: scene.id})}, "Dirección →")));
}
