// Helpers compartidos: DOM, API, avisos, zoom, cajon de revision y la tarjeta de revision de un nodo.
export const $ = (sel, root = document) => root.querySelector(sel);

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "value") node.value = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export async function api(path, body) {
  const options = body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

// mensaje comun cuando un pedido entra a la cola de generacion
export function queued(result, what = "Pedido") {
  const info = result && (result.cola || result);
  if (!info || !info.lote) return toast(`${what}: guardado`);
  toast(info.posicion > 1 ? `${what}: en la cola (lote ${info.lote}, ${info.posicion - 1} antes)` : `${what}: generando (lote ${info.lote})`);
}

export function toast(message) {
  const box = $("#toast");
  box.textContent = message;
  box.style.display = "block";
  clearTimeout(box._t);
  box._t = setTimeout(() => (box.style.display = "none"), 3500);
}

export function zoom(url) {
  const box = $("#lightbox");
  $("img", box).src = url;
  box.classList.add("open");
}

export function text(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(text).join(" · ");
  if (typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}: ${text(v)}`).join("\n");
  return String(value);
}

export function head(eyebrow, title, lead, ...extra) {
  return el("div", {class: "page-head"}, el("div", {class: "eyebrow"}, eyebrow), el("h1", {}, title),
    lead ? el("p", {class: "lead"}, lead) : null, extra);
}

export const STATES = ["a pedido", "pendiente", "generado", "aprobado", "rechazado", "desactualizado", "bloqueado"];
export const STATE_COLORS = {"a pedido": "#555b66", pendiente: "var(--accent)", generado: "var(--blue)",
  aprobado: "var(--ok)", rechazado: "var(--red)", desactualizado: "var(--warn)", bloqueado: "var(--line)"};
const ROLES = ["escritor", "director", "casting", "vestuario", "arte", "fotografo"];

export function badge(status) {
  return el("span", {class: "badge b-" + status.replace(" ", "-")}, status);
}

// confirmacion propia (sin dialogos del navegador, que traban la automatizacion)
export function confirmBox(message, onConfirm, label = "Confirmar") {
  const content = $("#content");
  const box = el("div", {class: "panel confirm"},
    el("pre", {class: "log", style: "max-height:220px"}, message),
    el("div", {class: "actions", style: "margin-top:10px"},
      el("button", {class: "btn primary", onclick: async () => { box.remove(); await onConfirm(); }}, label),
      el("button", {class: "btn", onclick: () => box.remove()}, "Cancelar")));
  content.prepend(box);
  window.scrollTo(0, 0);
}

// cajon lateral con la tarjeta de revision de un nodo
export async function openNode(id, onChange) {
  const drawer = $("#drawer");
  drawer.replaceChildren(el("div", {class: "empty"}, "Cargando…"));
  drawer.classList.add("open");
  const data = await api("/api/estado?tipo=" + encodeURIComponent(id.split("/")[0]));
  const node = data.nodos.find(item => item.id === id);
  drawer.replaceChildren(el("button", {class: "btn sm close", onclick: closeDrawer}, "Cerrar ✕"),
    node ? nodeCard(node, {onChange: async () => { await openNode(id, onChange); onChange && onChange(); }})
      : el("div", {class: "empty"}, "No existe."));
}
export function closeDrawer() { $("#drawer").classList.remove("open"); }

function actionOptions(tipo) {
  const options = [["semilla", "Otra semilla (mismo texto)"]];
  if (tipo === "toma") {
    options.push(["mas_parecido", "Más parecido a las referencias"], ["mas_estilo", "Más estilo OVA"]);
    for (const role of ROLES) options.push([`rol:${role}`, `Rehacer ${role} (Ollama)`]);
  } else if (["retrato", "vestuario", "lugar", "objeto"].includes(tipo)) {
    options.push(["descripcion", "Corregir la descripción (Ollama)"]);
  }
  return options;
}

export function uploadButton(id, onDone, label = "Subir imagen") {
  const input = el("input", {type: "file", accept: "image/png,image/jpeg", style: "display:none", onchange: async () => {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) return toast("La imagen pesa más de 15 MB");
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        await api("/api/subir", {id, datos: reader.result});
        toast("Imagen subida y aprobada");
        onDone && onDone();
      } catch (error) { toast("Error: " + error.message); }
    };
    reader.readAsDataURL(file);
  }});
  return el("span", {}, input, el("button", {class: "btn sm", onclick: () => input.click()}, label));
}

export function currentCandidate(node) {
  const all = node.versiones.flatMap(v => v.candidatos.map((c, i) => ({...c, v: v.v, i})));
  return all.find(c => c.hash === node.elegido) || all[all.length - 1] || null;
}

// tarjeta de revision: imagen elegida, versiones y candidatos, aprobar, rechazar con nota, cascada, regenerar
export function nodeCard(node, {onChange, upload = true} = {}) {
  const current = currentCandidate(node);
  const refresh = () => onChange && onChange();
  const hero = el("div", {class: "hero", onclick: () => current && zoom(current.url)},
    current ? el("img", {src: current.url, alt: node.titulo, loading: "lazy"}) : (node.estado === "a pedido" ? "A pedido" : "Sin imagen todavía"));
  const thumbs = el("div", {class: "thumbs"});
  for (const version of node.versiones.slice().reverse()) {
    if (!version.candidatos.length) continue;
    thumbs.append(el("div", {class: "vlabel"}, `v${version.v}${version.legado ? " · legado" : ""} · ${version.modelo || ""} · ${version.fecha || ""}`));
    version.candidatos.forEach((cand, index) => {
      const verdict = cand.revision && cand.revision.estado;
      thumbs.append(el("img", {src: cand.url, loading: "lazy", title: verdict ? `${verdict}: ${cand.revision.nota || ""}` : "sin revisar",
        class: (current && cand.hash === current.hash ? "on " : "") + (verdict === "aprobado" ? "ok" : verdict === "rechazado" ? "bad" : ""),
        onclick: async () => { await api("/api/elegir", {id: node.id, v: version.v, candidato: index}); refresh(); }}));
    });
  }
  const info = node.info || {};
  const details = el("details", {}, el("summary", {}, "Ficha"),
    Object.entries(info).filter(([k, v]) => v && !["referencias", "personaje"].includes(k)).map(([k, v]) =>
      el("p", {}, el("b", {}, k + ": "), text(v))));
  const note = el("textarea", {placeholder: "¿Qué está mal? (ej: la cara se ve mayor, falta lluvia, la mano no sostiene nada)"});
  const action = el("select", {}, actionOptions(node.tipo).map(([value, label]) => el("option", {value}, label)));
  const reject = el("div", {class: "reject"}, note, action,
    el("div", {class: "actions"},
      el("button", {class: "btn bad", onclick: async () => {
        await api("/api/revisar", {id: node.id, hash: current.hash, estado: "rechazado", nota: note.value, accion: action.value});
        toast(`Rechazado: ${node.cascada} cosas dependen de esto`); refresh(); }}, "Confirmar rechazo"),
      el("button", {class: "btn", onclick: () => reject.classList.remove("open")}, "Cancelar")));
  const cascade = el("div", {class: "casc"});
  const verdict = current && current.revision;
  const refs = info.referencias && info.referencias.length ? el("div", {class: "refs", title: "Referencias que usa esta toma"},
    info.referencias.map(url => el("img", {src: url, loading: "lazy", onclick: () => zoom(url)}))) : null;
  return el("div", {class: "card", "data-id": node.id},
    hero,
    el("div", {class: "body"},
      el("div", {class: "title-row"}, el("h3", {}, node.titulo || node.id), badge(node.estado)),
      node.motivo ? el("div", {class: "why"}, node.motivo) : null,
      verdict && verdict.nota ? el("div", {class: "why"}, `Nota: ${verdict.nota} (${verdict.accion || "-"})`) : null,
      info.que_hace ? el("div", {class: "why"}, info.que_hace) : null,
      refs, thumbs, details, reject, cascade,
      el("div", {class: "actions"},
        el("button", {class: "btn ok", disabled: !current, onclick: async () => {
          await api("/api/revisar", {id: node.id, hash: current.hash, estado: "aprobado"});
          toast(node.tipo === "toma" ? "Aprobada: pasa a ser el fondo del tema" : "Aprobado"); refresh(); }}, "Aprobar"),
        el("button", {class: "btn bad", disabled: !current, onclick: () => reject.classList.toggle("open")}, "Rechazar…"),
        el("button", {class: "btn", onclick: async () => {
          const data = await api("/api/cascada?id=" + encodeURIComponent(node.id));
          cascade.textContent = data.cascada.length ? `Si cambia, se rehacen: ${data.cascada.join(", ")}` : "Nada depende de esto.";
          cascade.classList.toggle("open"); }}, `Cascada (${node.cascada})`),
        el("button", {class: "btn", disabled: ["bloqueado", "a pedido"].includes(node.estado), onclick: async () => {
          const result = await api("/api/regenerar", {ids: [node.id], etiqueta: `regenerar ${node.titulo || node.id}`});
          queued(result, `${result.plan.length} trabajos`); }}, "Regenerar"),
        upload && node.tipo !== "hoja" ? uploadButton(node.id, refresh) : null)));
}

// imagen chica de un nodo (para la ficha y el storyboard): abre la tarjeta en el cajon
export function slot(node, cls, placeholder, onChange) {
  if (!node) return el("div", {class: "slot " + cls}, placeholder);
  const current = currentCandidate(node);
  return el("button", {class: "slot " + cls, title: `${node.titulo} · ${node.estado}`, onclick: () => openNode(node.id, onChange)},
    current ? el("img", {src: current.url, loading: "lazy", alt: ""}) : el("span", {}, placeholder, el("br"), el("small", {}, node.estado)),
    el("i", {class: "dot", style: `background:${STATE_COLORS[node.estado] || "#777"}`}));
}
