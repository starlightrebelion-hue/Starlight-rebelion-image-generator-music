// Etapa 7: Storyboard tipo LTX. Una fila por secuencia; una tarjeta por plano (en Ejemplo 1, un plano por tema).
// La miniatura es la imagen de inicio del plano, o la toma del tema, o el cuadro de previz, o la foto del lugar.
import {el, api, head, badge, openNode} from "./ui.js";

export async function storyboard() {
  const doc = await api("/api/guion_doc");
  const groups = doc.estructura.secuencias.filter(sequence => sequence.escenas.some(scene => scene.estado !== "oculta"));
  return [head("Etapa 7", "Storyboard", "Doble clic en una tarjeta abre la revisión de su imagen; ✎ lleva a la Dirección de esa escena."),
    groups.length ? groups.map(sequence => el("div", {class: "ltx-scene-group"},
      el("div", {class: "ltx-scene-header"}, el("h3", {}, sequence.titulo),
        el("span", {class: "why"}, `${sequence.escenas.length} escenas · ${sequence.escenas.reduce((sum, scene) => sum + (scene.planos || []).length, 0)} planos`)),
      el("div", {class: "ltx-cards-container"}, sequence.escenas.filter(scene => scene.estado !== "oculta").flatMap((scene, sceneIndex) =>
        (scene.planos.length ? scene.planos : [{id: "p1", tipo: "", que_se_ve: scene.accion}]).map((shot, shotIndex) => {
          const image = scene.tema ? scene.miniatura : (shot.miniatura || shot.previz || scene.miniatura_lugar);
          const source = scene.tema ? "toma" : shot.miniatura ? "inicio" : shot.previz ? "previz" : scene.miniatura_lugar ? "locación" : "";
          const node = scene.tema ? `toma/${scene.tema}` : `plano/${scene.id}__${shot.id}_ini`;

          // Determinar el estado actual para el badge
          let status = shot.estado_imagen;
          if (!status && scene.tema) {
            // Para tomas, el estado viene en la estructura del doc si el servidor lo envió
            // pero aquí usamos la info que ya tenemos en el objeto shot/scene
            status = shot.estado_imagen || "pendiente";
          }

          return [sceneIndex + shotIndex ? el("div", {class: "ltx-arrow"}, "→") : null,
            el("div", {class: "ltx-card", ondblclick: () => openNode(node, () => window.sfRender(true))},
              el("div", {class: "ltx-card-head"}, el("span", {}, `${scene.lugar || ""} · ${shot.id}`),
                status ? badge(status) : scene.tema ? el("span", {class: "badge"}, "tema") : null),
              el("div", {class: "ltx-card-img"}, image ? el("img", {src: image, loading: "lazy", alt: ""}) : "Sin imagen",
                source ? el("span", {class: "src"}, source) : null),
              el("div", {class: "ltx-card-body"},
                el("div", {}, [shot.tipo, shot.duracion ? `${shot.duracion}s` : null].filter(Boolean).map(tag => el("span", {class: "ltx-tag"}, tag))),
                el("p", {}, shot.que_se_ve || scene.accion || ""),
                el("div", {class: "row", style: "justify-content:space-between"},
                  el("span", {class: "why"}, shot.accion ? shot.accion.slice(0, 60) : ""),
                  el("button", {class: "btn sm", onclick: () => window.sfGo("tecnico", {id: scene.id})}, "✎"))))];
        }))))) : el("div", {class: "empty"}, "El guion todavía no tiene escenas.")];
}
