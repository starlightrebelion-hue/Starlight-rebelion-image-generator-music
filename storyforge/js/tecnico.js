// Etapa 6: Direccion. Planta 2D (personas, objetos, camara, eje de 180) + previz 3D de cada plano con camara de
// INICIO y de FIN (pan, tilt, dolly, altura, lente), animacion entre las dos y los cuadros que van a ComfyUI.
// De estudio_tecnico.py + decoupage.py + previz.py de Doble Fondo.
import {el, api, head, toast, queued, nodeCard, badge, slot, confirmBox, currentCandidate} from "./ui.js";
import {render, camera, angles, aim, dolly} from "./previz3d.js";

let sceneId = null;
let data = null;
let plan = null;
let current = 0;
let key = "ini";          // keyframe que se edita
let t = 0;
let playing = null;

export async function tecnico(params = {}) {
  if (params.semilla) sceneId = `t${params.semilla}`;
  else if (params.id) sceneId = params.id;
  let list = (await api("/api/guion_doc")).estructura.secuencias.flatMap(sequence => sequence.escenas.filter(scene => scene.estado !== "oculta"));
  if (!sceneId || !list.some(scene => scene.id === sceneId)) sceneId = list.length ? list[0].id : null;
  if (!sceneId) return [head("Etapa 6", "Dirección", ""), el("div", {class: "empty"}, "Todavía no hay escenas en el guion.")];
  data = await api("/api/tecnico?escena=" + encodeURIComponent(sceneId));
  plan = data.planta ? JSON.parse(JSON.stringify(data.planta)) : null;
  if (plan && !plan.set3d) plan.set3d = data.set3d;
  if (current >= ((plan && plan.planos.length) || 0)) current = 0;
  clearInterval(playing);
  playing = null;
  const picker = el("select", {onchange: e => window.sfGo("tecnico", {id: e.target.value})},
    list.map(scene => el("option", {value: scene.id, selected: scene.id === sceneId},
      `${scene.tema ? scene.tema + " · " : ""}${scene.int_ext || ""} ${scene.lugar || ""} - ${scene.momento || ""}`)));
  const staging = el("div", {class: "staging"}, data.puesta || "Sin puesta.");
  if (!plan) {
    return [head("Etapa 6", "Dirección", "", el("div", {class: "row"}, picker)), el("div", {class: "empty"}, data.motivo || "Sin planta.")];
  }
  const movement = el("div", {class: "staging", id: "mov"});
  const canvas = el("canvas", {class: "previz", width: 768, height: 432});
  const plantSvg = plant(staging, movement, canvas);
  const controls = el("div", {class: "cam-controls"});
  const table = shotTable(staging, movement, canvas, controls);
  const redraw = () => drawPreviz(canvas, movement, controls);
  const timeline = el("input", {type: "range", min: 0, max: 1, step: 0.01, value: 0, oninput: e => { t = Number(e.target.value); stop(); redraw(); }});
  const stop = () => { clearInterval(playing); playing = null; };
  const play = () => {
    stop();
    let start = performance.now();
    playing = setInterval(() => {
      const shot = plan.planos[current];
      const seconds = (shot && shot.duracion) || 3;
      t = ((performance.now() - start) / 1000 / seconds) % 1;
      timeline.value = t;
      redraw();
    }, 40);
  };
  setTimeout(redraw, 0);
  return [
    head("Etapa 6", `Dirección · ${data.escena.titulo || data.escena.lugar || sceneId}`,
      "Ubicá la cámara de INICIO y de FIN de cada plano: arrastrá en la vista 3D (pan y tilt), rueda = dolly, Ctrl+rueda = lente. La planta corrige los 180° y la puesta y el movimiento pasan a ComfyUI.",
      el("div", {class: "row"}, picker, data.guardada ? badge("guardada") : el("span", {class: "why"}, "planta inicial sin guardar"))),
    el("div", {class: "direction"},
      el("div", {},
        el("h3", {}, "Planta"), plantSvg,
        el("p", {class: "why"}, "Verde: lado del eje donde pueden ir las cámaras. Arrastrá personas, objetos y cámaras."),
        el("h3", {style: "margin-top:12px"}, "Planos"), table,
        el("h3", {style: "margin-top:12px"}, "Puesta para el prompt"), staging),
      el("div", {},
        el("div", {class: "row", style: "justify-content:space-between"},
          el("div", {class: "tabs", style: "margin:0;border:0"}, ["ini", "fin"].map(name => el("button", {class: "tab" + (key === name ? " on" : ""),
            onclick: () => { key = name; t = name === "ini" ? 0 : 1; timeline.value = t; window.sfRender(true); }}, name === "ini" ? "Cámara de INICIO" : "Cámara de FIN"))),
          el("span", {class: "why"}, "1 unidad = 1 metro")),
        canvas,
        el("div", {class: "row", style: "margin:6px 0"},
          el("button", {class: "btn sm", onclick: play}, "▶ Animar inicio → fin"),
          el("button", {class: "btn sm", onclick: stop}, "■"), timeline, el("span", {class: "why"}, "t")),
        controls,
        el("h3", {style: "margin-top:10px"}, "Movimiento (va al prompt de Wan)"), movement,
        el("div", {class: "row", style: "margin-top:10px"},
          el("button", {class: "btn primary", onclick: () => save(staging, movement, true)}, "Guardar dirección"),
          el("button", {class: "btn", onclick: () => exportFrames()}, "Guardar cuadros de previz"),
          el("button", {class: "btn", onclick: () => redo()}, "Rehacer imágenes con esta dirección")),
        outputs())),
  ];
}

function shotCamera(shot, moment) {
  return camera(plan, shot, moment === "ini" ? 0 : 1);
}

function drawPreviz(canvas, movement, controls) {
  const shot = plan.planos[current];
  if (!shot) return;
  const cam = render(canvas, plan, shot, t, playing || (t > 0 && t < 1) ? null : shotCamera(shot, key));
  drawControls(controls, canvas, movement);
  return cam;
}

function setKey(shot, cam) {
  shot[key === "ini" ? "cam_ini" : "cam_fin"] = {x: round(cam.x), y: round(cam.y), z: round(cam.z), mira: cam.mira.map(round), focal: Math.round(cam.focal)};
  if (key === "ini" && !shot.cam_fin) shot.cam_fin = {...shot.cam_ini, mira: [...shot.cam_ini.mira]};
}
const round = value => Math.round(value * 100) / 100;

// los controles se arman una vez por plano y keyframe; cada uno lee la camara actual al moverse
const SLIDERS = [
  ["X", 0, 10, 0.05, cam => cam.x, (cam, v) => ({...cam, x: v, mira: [cam.mira[0] + v - cam.x, cam.mira[1], cam.mira[2]]})],
  ["Y", 0, 10, 0.05, cam => cam.y, (cam, v) => ({...cam, y: v, mira: [cam.mira[0], cam.mira[1] + v - cam.y, cam.mira[2]]})],
  ["Altura", 0.2, 4, 0.05, cam => cam.z, (cam, v) => ({...cam, z: v, mira: [cam.mira[0], cam.mira[1], cam.mira[2] + v - cam.z]})],
  ["Pan °", -180, 180, 1, cam => angles(cam).pan, (cam, v) => aim(cam, v, angles(cam).tilt)],
  ["Tilt °", -60, 60, 1, cam => angles(cam).tilt, (cam, v) => aim(cam, angles(cam).pan, v)],
  ["Lente mm", 14, 135, 1, cam => cam.focal, (cam, v) => ({...cam, focal: v})],
];

function drawControls(box, canvas, movement) {
  const shot = plan.planos[current];
  movement.textContent = describeMove(shot);
  const signature = `${current}:${key}`;
  const refresh = () => {   // solo valores y etiquetas, sin reconstruir (no corta el arrastre de un slider)
    const cam = shotCamera(shot, key);
    box.querySelectorAll(".cam-slider").forEach((label, index) => {
      const [name, , , step, read] = SLIDERS[index];
      const value = read(cam);
      label.firstChild.textContent = `${name} ${Number(value).toFixed(step < 1 ? 2 : 0)}`;
      if (document.activeElement !== label.lastChild) label.lastChild.value = value;
    });
  };
  const update = next => {
    setKey(shot, next);
    t = key === "ini" ? 0 : 1;
    render(canvas, plan, shot, t, shotCamera(shot, key));
    movement.textContent = describeMove(shot);
    refresh();
  };
  if (box.dataset.signature !== signature) {
    box.dataset.signature = signature;
    box.replaceChildren(
      ...SLIDERS.map(([name, min, max, step, , apply]) => el("label", {class: "cam-slider"}, el("span", {}, name),
        el("input", {type: "range", min, max, step, oninput: e => update(apply(shotCamera(shot, key), Number(e.target.value)))}))),
      el("div", {class: "row"},
        el("button", {class: "btn sm", onclick: () => update(dolly(shotCamera(shot, key), 0.25))}, "Dolly in"),
        el("button", {class: "btn sm", onclick: () => update(dolly(shotCamera(shot, key), -0.25))}, "Dolly out"),
        el("button", {class: "btn sm", onclick: () => { const other = shotCamera(shot, key === "ini" ? "fin" : "ini"); update({...other, mira: [...other.mira]}); }},
          key === "ini" ? "Copiar desde FIN" : "Copiar desde INICIO"),
        el("button", {class: "btn sm", onclick: () => { delete shot[key === "ini" ? "cam_ini" : "cam_fin"]; update(shotCamera(shot, key)); delete shot[key === "ini" ? "cam_ini" : "cam_fin"]; }}, "Restablecer")));
  }
  refresh();
  // arrastrar = pan/tilt, rueda = dolly, Ctrl+rueda = lente
  canvas.onpointerdown = event => {
    const cam = shotCamera(shot, key);
    const start = {x: event.clientX, y: event.clientY, ...angles(cam)};
    canvas.setPointerCapture(event.pointerId);
    canvas.onpointermove = move => update(aim(shotCamera(shot, key), start.pan - (move.clientX - start.x) * 0.3,
      Math.max(-60, Math.min(60, start.tilt - (move.clientY - start.y) * 0.3))));
    canvas.onpointerup = () => { canvas.onpointermove = null; };
  };
  canvas.onwheel = event => {
    event.preventDefault();
    const cam = shotCamera(shot, key);
    if (event.ctrlKey) update({...cam, focal: Math.max(14, Math.min(135, cam.focal - Math.sign(event.deltaY) * 3))});
    else update(dolly(cam, -Math.sign(event.deltaY) * 0.2));
  };
}

function describeMove(shot) {
  const a = camera(plan, shot, 0), b = camera(plan, shot, 1);
  const parts = [];
  const forward = [a.mira[0] - a.x, a.mira[1] - a.y];
  const length = Math.hypot(...forward) || 1;
  const f = [forward[0] / length, forward[1] / length], r = [-f[1], f[0]];
  const move = [b.x - a.x, b.y - a.y, b.z - a.z];
  const ahead = move[0] * f[0] + move[1] * f[1], side = move[0] * r[0] + move[1] * r[1];
  if (Math.abs(ahead) > 0.3) parts.push(`slow dolly ${ahead > 0 ? "in" : "out"}`);
  if (Math.abs(side) > 0.3) parts.push(`tracking shot moving ${side > 0 ? "right" : "left"}`);
  if (Math.abs(move[2]) > 0.25) parts.push(`crane ${move[2] > 0 ? "up" : "down"}`);
  const turn = ((angles(b).pan - angles(a).pan + 540) % 360) - 180;
  if (Math.abs(turn) > 4.5 && Math.abs(side) <= 0.3) parts.push(`camera pans ${turn > 0 ? "right" : "left"}`);
  if (Math.abs((b.mira[2] - b.z) - (a.mira[2] - a.z)) > 0.4) parts.push(`camera tilts ${(b.mira[2] - b.z) > (a.mira[2] - a.z) ? "up" : "down"}`);
  if (Math.abs(b.focal - a.focal) > 5) parts.push(`slow zoom ${b.focal > a.focal ? "in" : "out"}`);
  return parts.join(", ") || "static camera, locked off";
}

async function save(staging, movement, store) {
  const result = await api("/api/tecnico", {escena: sceneId, planta: plan, guardar: store});
  const keep = plan.set3d;
  plan = result.planta;
  plan.set3d = plan.set3d || keep;
  staging.textContent = result.puesta || "Sin puesta.";
  if (result.movimientos && movement) movement.textContent = result.movimientos[current] ? result.movimientos[current][0] : movement.textContent;
  if (result.corregidas.length) toast(`Regla de 180°: se espejó la cámara de ${result.corregidas.join(", ")}`);
  else if (store) toast("Dirección guardada: las imágenes de este plano quedan desactualizadas");
  return result;
}

async function exportFrames() {
  const off = el("canvas", {width: 1024, height: 576});
  const shots = plan.planos;
  for (const shot of shots) {
    for (const moment of ["ini", "fin"]) {
      render(off, plan, shot, moment === "ini" ? 0 : 1, camera(plan, shot, moment === "ini" ? 0 : 1));
      await api("/api/previz", {escena: sceneId, plano: shot.id || "p1", momento: moment, datos: off.toDataURL("image/png")});
    }
  }
  toast(`Cuadros de previz guardados (${shots.length * 2}): van como referencia de composición`);
  window.sfRender(true);
}

async function redo() {
  await save(document.querySelector(".staging"), document.getElementById("mov"), true);
  const ids = [];
  for (const shot of data.planos) for (const node of Object.values(shot.nodos || {})) ids.push(node.id);
  if (data.semilla) ids.push(`toma/${data.semilla}`);
  if (!ids.length) return toast("No hay imágenes para este plano todavía");
  confirmBox(`Se rehacen con la dirección nueva:\n${ids.join("\n")}`, async () => {
    const result = await api("/api/regenerar", {ids, etiqueta: `dirección ${sceneId}`});
    queued(result, "Rehacer");
  }, "Rehacer");
}

function outputs() {
  const shot = data.planos[current];
  if (!shot) return null;
  const clip = shot.clip;
  const video = clip && currentCandidate(clip);
  return el("div", {class: "panel", style: "margin-top:12px"},
    el("h3", {}, `Plano ${current + 1}: imágenes y clip`),
    el("div", {class: "row", style: "align-items:flex-start"},
      ["ini", "fin"].map(moment => el("div", {style: "width:200px"}, el("div", {class: "why"}, moment === "ini" ? "Inicio" : "Fin"),
        shot.nodos && shot.nodos[moment] ? slot(shot.nodos[moment], "cine", moment.toUpperCase(), () => window.sfRender(true))
          : (shot.previz && shot.previz[moment] ? el("img", {src: shot.previz[moment], style: "width:100%;border-radius:6px"}) : el("div", {class: "empty"}, data.semilla ? "toma del tema" : "sin imagen")))),
      el("div", {style: "flex:1;min-width:220px"}, el("div", {class: "why"}, "Clip (Wan 2.2, inicio → fin)"),
        video && video.url.includes(".mp4") ? el("video", {src: video.url, controls: true, loop: true, style: "width:100%;border-radius:6px"}) : null,
        clip ? el("div", {class: "row"}, badge(clip.estado),
          clip.estado === "a pedido" ? el("button", {class: "btn sm primary", onclick: () => confirmBox(
            `Wan 2.2 hace el clip entre la imagen de inicio y la de fin con este movimiento:\n${shot.movimiento[0]}\n\nTarda unos minutos y usa la GPU (Ollama se descarga antes).`,
            async () => { const r = await api("/api/clip_pedir", {id: clip.id}); queued(r, "Clip"); window.sfRender(true); }, "Pedir clip")}, "Pedir clip") : null)
          : el("p", {class: "why"}, "Sin clip para este plano.")),
      data.toma ? el("div", {style: "width:260px"}, nodeCard(data.toma, {onChange: () => window.sfRender(true), upload: false})) : null));
}

function shotTable(staging, movement, canvas, controls) {
  const body = el("tbody");
  const draw = () => body.replaceChildren(...plan.planos.map((shot, index) => el("tr", {class: index === current ? "on" : "", onclick: () => { current = index; draw(); drawPreviz(canvas, movement, controls); }},
    el("td", {}, shot.toma), el("td", {}, shot.id || ""),
    el("td", {}, el("select", {onchange: e => { shot.tipo = e.target.value; save(staging, movement, false); }},
      data.tipos.map(type => el("option", {value: type, selected: type === shot.tipo}, type)))),
    el("td", {}, `${Number(shot.camara.x).toFixed(1)}, ${Number(shot.camara.y).toFixed(1)}`),
    el("td", {}, el("label", {class: "why"}, el("input", {type: "checkbox", checked: shot.cruza_eje, onchange: e => { shot.cruza_eje = e.target.checked; save(staging, movement, false); }}), " salto")))));
  draw();
  return el("table", {class: "shots"}, el("thead", {}, el("tr", {}, el("th", {}, "#"), el("th", {}, "id"), el("th", {}, "Plano"), el("th", {}, "Cámara"), el("th", {}, "Eje"))), body);
}

const NS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS(NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  for (const child of children) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}

function plant(staging, movement, canvas) {
  const svg = svgEl("svg", {class: "plant", viewBox: "-0.5 -0.5 11 11"});
  let drag = null;
  const point = event => {
    const rect = svg.getBoundingClientRect();
    return {x: Math.max(0, Math.min(10, (event.clientX - rect.left) / rect.width * 11 - 0.5)),
      y: Math.max(0, Math.min(10, (event.clientY - rect.top) / rect.height * 11 - 0.5))};
  };
  const pos = name => plan.personajes[name] || plan.objetos.find(item => item.id === name);
  const draw = () => {
    svg.replaceChildren();
    for (let i = 0; i <= 10; i += 1) {
      svg.append(svgEl("line", {x1: i, y1: 0, x2: i, y2: 10, stroke: "#1d2026", "stroke-width": 0.02}),
        svgEl("line", {x1: 0, y1: i, x2: 10, y2: i, stroke: "#1d2026", "stroke-width": 0.02}));
    }
    svg.append(svgEl("text", {x: 4.4, y: -0.15, class: "lbl"}, "FONDO"), svgEl("text", {x: 4.4, y: 10.4, class: "lbl"}, "FRENTE"));
    if (plan.eje.length === 2 && pos(plan.eje[0]) && pos(plan.eje[1])) {
      const a = pos(plan.eje[0]), b = pos(plan.eje[1]);
      const dx = b.x - a.x, dy = b.y - a.y, k = 20;
      const p1 = {x: a.x - dx * k, y: a.y - dy * k}, p2 = {x: b.x + dx * k, y: b.y + dy * k};
      const side = plan.lado || 1, nx = -dy * side * 40, ny = dx * side * 40;
      svg.append(svgEl("polygon", {points: `${p1.x},${p1.y} ${p2.x},${p2.y} ${p2.x + nx},${p2.y + ny} ${p1.x + nx},${p1.y + ny}`, fill: "rgba(80,160,90,.13)"}),
        svgEl("line", {x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, stroke: "#6c6", "stroke-width": 0.03, "stroke-dasharray": "0.08 0.08"}));
    }
    plan.planos.forEach((shot, index) => {
      const cam = camera(plan, shot, 0);
      const end = camera(plan, shot, 1);
      const angle = Math.atan2(cam.mira[1] - cam.y, cam.mira[0] - cam.x);
      const spread = Math.atan(18 / cam.focal), length = 1.2;
      const color = index === current ? "#ff5555" : "#888";
      const group = svgEl("g", {style: "cursor:grab"},
        svgEl("polygon", {points: `${cam.x},${cam.y} ${cam.x + Math.cos(angle - spread) * length},${cam.y + Math.sin(angle - spread) * length} ${cam.x + Math.cos(angle + spread) * length},${cam.y + Math.sin(angle + spread) * length}`,
          fill: index === current ? "rgba(255,85,85,.18)" : "rgba(160,160,160,.1)", stroke: color, "stroke-width": 0.02}),
        (Math.hypot(end.x - cam.x, end.y - cam.y) > 0.05) ? svgEl("line", {x1: cam.x, y1: cam.y, x2: end.x, y2: end.y, stroke: color, "stroke-width": 0.03, "stroke-dasharray": "0.1 0.06"}) : svgEl("g"),
        svgEl("circle", {cx: cam.x, cy: cam.y, r: 0.2, fill: color}),
        svgEl("text", {x: cam.x + 0.25, y: cam.y + 0.1}, `${shot.toma} ${shot.tipo}`));
      group.addEventListener("pointerdown", event => { current = index; drag = {kind: "camara", shot}; svg.setPointerCapture(event.pointerId); });
      svg.append(group);
    });
    for (const item of plan.objetos) {
      const group = svgEl("g", {style: "cursor:grab"}, svgEl("rect", {x: item.x - 0.18, y: item.y - 0.18, width: 0.36, height: 0.36, fill: "#555", stroke: "#aaa", "stroke-width": 0.02}),
        svgEl("text", {x: item.x - 0.6, y: item.y + 0.55, class: "lbl"}, (item.nombre || "objeto").slice(0, 24)));
      group.addEventListener("pointerdown", event => { drag = {kind: "objeto", item}; svg.setPointerCapture(event.pointerId); });
      svg.append(group);
    }
    for (const [name, person] of Object.entries(plan.personajes)) {
      const look = pos(person.mira);
      const group = svgEl("g", {style: "cursor:grab"},
        look ? svgEl("line", {x1: person.x, y1: person.y, x2: person.x + (look.x - person.x) * 0.35, y2: person.y + (look.y - person.y) * 0.35, stroke: "#e0b354", "stroke-width": 0.05}) : svgEl("g"),
        svgEl("circle", {cx: person.x, cy: person.y, r: 0.3, fill: "#e0b354"}),
        svgEl("text", {x: person.x - 0.5, y: person.y + 0.65}, person.nombre || name));
      group.addEventListener("pointerdown", event => { drag = {kind: "persona", person}; svg.setPointerCapture(event.pointerId); });
      svg.append(group);
    }
  };
  svg.addEventListener("pointermove", event => {
    if (!drag) return;
    const p = point(event);
    if (drag.kind === "camara") {
      const shot = drag.shot;
      const dx = round(p.x) - shot.camara.x, dy = round(p.y) - shot.camara.y;
      shot.camara.x = round(p.x); shot.camara.y = round(p.y);
      for (const name of ["cam_ini", "cam_fin"]) {   // los keyframes se mueven con la camara de la planta
        if (shot[name]) { shot[name].x = round(shot[name].x + dx); shot[name].y = round(shot[name].y + dy); shot[name].mira = [shot[name].mira[0] + dx, shot[name].mira[1] + dy, shot[name].mira[2]]; }
      }
    } else {
      const target = drag.kind === "objeto" ? drag.item : drag.person;
      target.x = round(p.x); target.y = round(p.y);
    }
    draw();
    drawPreviz(canvas, movement, document.querySelector(".cam-controls"));
  });
  svg.addEventListener("pointerup", async () => {
    if (!drag) return;
    drag = null;
    await save(staging, movement, false);   // el servidor corrige el eje y devuelve la puesta (se guarda con el boton)
    draw();
    drawPreviz(canvas, movement, document.querySelector(".cam-controls"));
  });
  draw();
  return svg;
}
