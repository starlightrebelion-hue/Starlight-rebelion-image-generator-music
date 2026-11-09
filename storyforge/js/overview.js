// Overview (de la v3): poster, premisa editable, metricas, estado por tipo, lo que falta y la cola.
import {el, api, head, toast, STATES, STATE_COLORS} from "./ui.js";

export async function overview() {
  const [project, summary] = await Promise.all([api("/api/proyecto"), api("/api/resumen")]);
  const m = project.metricas;
  const poster = el("div", {class: "poster", style: project.poster ? `background-image:url('${project.poster}')` : ""},
    el("div", {class: "poster-content"},
      el("div", {class: "poster-title"}, project.titulo),
      el("div", {class: "poster-logline"}, project.logline),
      el("div", {class: "eyebrow"}, `${project.genero} · ${project.formato}`)));
  const fields = {};
  const premise = el("details", {class: "panel", style: "margin-top:12px"}, el("summary", {}, "Editar premisa"),
    ["titulo", "logline", "genero", "formato", "tono", "concepto"].map(key => {
      fields[key] = el(key === "concepto" || key === "logline" ? "textarea" : "input", {value: project[key] || ""});
      return el("div", {class: "field"}, el("label", {}, key), fields[key]);
    }),
    el("button", {class: "btn primary", onclick: async () => {
      const body = {};
      for (const [key, input] of Object.entries(fields)) body[key] = input.value;
      await api("/api/proyecto", body);
      toast("Premisa guardada");
    }}, "Guardar"));
  const stats = el("div", {class: "stats"},
    [["Escenas (temas)", m.escenas], ["Tomas con elenco", m.tomas], ["Tomas aprobadas", m.aprobadas],
     ["Rechazadas", m.rechazadas], ["Desactualizadas", m.desactualizadas], ["Personajes", m.personajes], ["Lugares", m.lugares]]
      .map(([k, v]) => el("div", {class: "stat"}, el("div", {class: "k"}, k), el("div", {class: "v"}, v))));
  const types = el("div", {class: "stats", style: "margin-top:12px"});
  for (const [tipo, counts] of Object.entries(summary.conteos)) {
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    types.append(el("div", {class: "stat"}, el("div", {class: "k"}, summary.nombres[tipo] || tipo), el("div", {class: "v"}, total),
      el("div", {class: "bar"}, STATES.filter(s => counts[s]).map(s =>
        el("i", {style: `width:${100 * counts[s] / total}%;background:${STATE_COLORS[s]}`, title: `${s}: ${counts[s]}`}))),
      el("div", {class: "why"}, STATES.filter(s => counts[s]).map(s => `${s} ${counts[s]}`).join(" · "))));
  }
  const review = Object.entries(summary.conteos).flatMap(([tipo, counts]) =>
    ["generado", "rechazado", "desactualizado"].filter(s => counts[s]).map(s => ({tipo, s, n: counts[s]})));
  const pageOf = {retrato: "personajes", vista: "personajes", expresion: "personajes", cinematico: "personajes", tela: "personajes",
    hoja: "personajes", vestuario: "vestuario", objeto: "objetos", lugar: "lugares", toma: "storyboard"};
  const plan = summary.plan;
  return [
    head("Ejemplo 1 · Dashboard", "Overview del proyecto",
      "Estado de la preproducción. Cada imagen se aprueba o se rechaza con una nota; al regenerar se rehace solo lo rechazado y lo que depende de eso."),
    el("div", {class: "overview"},
      el("div", {}, poster, premise),
      el("div", {},
        stats,
        el("h2", {}, "Para revisar"),
        review.length ? el("div", {class: "row"}, review.map(item => el("button", {class: "chip", onclick: () => window.sfGo(pageOf[item.tipo])},
          `${summary.nombres[item.tipo] || item.tipo}: ${item.n} ${item.s}`))) : el("div", {class: "why"}, "Nada para revisar."),
        el("h2", {}, "Estado por tipo"), types,
        el("h2", {}, `Para generar (${plan.length})`),
        plan.length ? el("pre", {class: "log"}, plan.map(job => `${job.motivo.padEnd(15)} ${job.nodo}  ${job.detalle || ""}`).join("\n"))
          : el("div", {class: "empty"}, "Nada pendiente."),
        el("h2", {}, "Reglas del universo"),
        typeof project.reglas === "string" ? el("p", {class: "why", style: "white-space:pre-wrap"}, project.reglas)
          : el("ul", {class: "why"}, (Array.isArray(project.reglas) ? project.reglas.map(rule => [null, rule]) : Object.entries(project.reglas || {}))
            .map(([key, rule]) => el("li", {}, key ? el("b", {}, key + ": ") : null, typeof rule === "string" ? rule : JSON.stringify(rule)))),
        el("h2", {}, "Registro de la cola"),
        el("pre", {class: "log", id: "log"}, summary.cola.registro.join("\n") || "Sin registro todavía."),
        summary.cola.pedidos.length ? [el("h2", {}, "Pedidos a Ollama"),
          el("pre", {class: "log"}, summary.cola.pedidos.map(item => `${item.estado.padEnd(10)} ${JSON.stringify(item.pedido)} ${item.fecha}`).join("\n"))] : null)),
  ];
}
