// Previz 3D de un plano (port de previz.py de Doble Fondo): la locacion como caja, las personas como prismas con
// cabeza, los objetos como cajas, luces key/fill/contra con sombreado Lambert y orden del pintor. Sin librerias.
// Planta: x izquierda->derecha, y fondo->frente, z altura (1 unidad = 1 metro).

const FOCAL = {PG: 24, PC: 28, PA: 32, PM: 40, PP: 60, PPP: 85, escorzo: 45, inserto: 70, POV: 35};
const EYE = {PG: 1.8, PC: 1.6, inserto: 1.1};
const COLORS = [[224, 179, 84], [111, 177, 214], [215, 122, 140], [140, 192, 132], [180, 142, 224], [224, 138, 79]];
const WALLS = {piso: [92, 84, 74], fondo: [128, 116, 100], frente: [110, 100, 88], izq: [118, 106, 92], der: [118, 106, 92]};

const P = (x, y, z) => [x, z, y];   // planta -> mundo (X derecha, Y arriba, Z hacia el frente)
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = a => Math.hypot(a[0], a[1], a[2]) || 1;
const unit = a => mul(a, 1 / norm(a));

function position(plan, name) {
  const person = (plan.personajes || {})[name];
  if (person) return person;
  return (plan.objetos || []).find(item => item.id === name) || null;
}

function target(plan, shot) {
  const names = (shot.apunta_a && shot.apunta_a.length) ? shot.apunta_a : Object.keys(plan.personajes || {});
  const points = names.map(name => position(plan, name)).filter(Boolean);
  if (!points.length) return [5, 5, 1.4];
  const z = shot.tipo === "inserto" ? 0.9 : 1.5;
  return [points.reduce((s, p) => s + p.x, 0) / points.length, points.reduce((s, p) => s + p.y, 0) / points.length, z];
}

// misma camara que decoupage_sf.camera: sin keyframes sale de la planta 2D
export function camera(plan, shot, t = 0) {
  const flat = shot.camara || {x: 5, y: 9.5};
  const base = {x: Number(flat.x), y: Number(flat.y), z: EYE[shot.tipo] || 1.55, mira: target(plan, shot), focal: FOCAL[shot.tipo] || 35};
  const start = {...base, ...(shot.cam_ini || {})};
  const end = {...start, ...(shot.cam_fin || {})};
  if (t <= 0) return start;
  const mix = (a, b) => a + (b - a) * t;
  return {x: mix(start.x, end.x), y: mix(start.y, end.y), z: mix(start.z, end.z),
    mira: [0, 1, 2].map(i => mix(start.mira[i], end.mira[i])), focal: mix(start.focal, end.focal)};
}

export function peopleAt(plan, shot, t = 0) {
  const out = {};
  for (const [name, person] of Object.entries(plan.personajes || {})) {
    const a = {...person, ...((shot.pers_ini || {})[name] || {})};
    const b = {...a, ...((shot.pers_fin || {})[name] || {})};
    out[name] = {x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, mira: person.mira, nombre: person.nombre || name};
  }
  return out;
}

// pan (giro en planta) y tilt (inclinacion) de una camara, en grados
export function angles(cam) {
  const dx = cam.mira[0] - cam.x, dy = cam.mira[1] - cam.y, dz = cam.mira[2] - cam.z;
  return {pan: Math.atan2(dy, dx) * 180 / Math.PI, tilt: Math.atan2(dz, Math.hypot(dx, dy)) * 180 / Math.PI};
}

export function aim(cam, pan, tilt, distance = 3) {
  const a = pan * Math.PI / 180, b = tilt * Math.PI / 180;
  return {...cam, mira: [cam.x + Math.cos(b) * Math.cos(a) * distance, cam.y + Math.cos(b) * Math.sin(a) * distance, cam.z + Math.sin(b) * distance]};
}

export function dolly(cam, meters) {
  const dx = cam.mira[0] - cam.x, dy = cam.mira[1] - cam.y, dz = cam.mira[2] - cam.z;
  const length = Math.hypot(dx, dy, dz) || 1;
  const k = meters / length;
  const clamp = v => Math.max(0, Math.min(10, v));
  return {...cam, x: clamp(cam.x + dx * k), y: clamp(cam.y + dy * k), z: Math.max(0.1, cam.z + dz * k),
    mira: [cam.mira[0] + dx * k, cam.mira[1] + dy * k, cam.mira[2] + dz * k]};
}

function box(x0, y0, z0, x1, y1, z1, color, inside = false) {
  const v = {a: P(x0, y0, z0), b: P(x1, y0, z0), c: P(x1, y1, z0), d: P(x0, y1, z0),
    e: P(x0, y0, z1), f: P(x1, y0, z1), g: P(x1, y1, z1), h: P(x0, y1, z1)};
  const faces = {piso: "adcb", techo: "efgh", fondo: "abfe", frente: "dhgc", izq: "aehd", der: "bcgf"};
  const center = P((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
  return Object.entries(faces).map(([part, idx]) => ({pts: [...idx].map(k => v[k]),
    color: typeof color === "function" ? color(part) : color, part, center, inside}));
}

function prism(cx, cy, z0, z1, r, color, sides = 8) {
  const out = [];
  const angle = k => 2 * Math.PI * k / sides;
  for (let k = 0; k < sides; k += 1) {
    const a = angle(k), b = angle(k + 1);
    out.push({pts: [P(cx + r * Math.cos(a), cy + r * Math.sin(a), z0), P(cx + r * Math.cos(b), cy + r * Math.sin(b), z0),
      P(cx + r * Math.cos(b), cy + r * Math.sin(b), z1), P(cx + r * Math.cos(a), cy + r * Math.sin(a), z1)], color, center: P(cx, cy, (z0 + z1) / 2)});
  }
  out.push({pts: Array.from({length: sides}, (_, k) => P(cx + r * Math.cos(angle(k)), cy + r * Math.sin(angle(k)), z1)), color, center: P(cx, cy, (z0 + z1) / 2)});
  return out;
}

function sphere(cx, cy, cz, r, color, n = 8, m = 5) {
  const out = [];
  const q = (t, a) => P(cx + r * Math.cos(t) * Math.cos(a), cy + r * Math.cos(t) * Math.sin(a), cz + r * Math.sin(t));
  for (let i = 0; i < m; i += 1) {
    const t0 = Math.PI * i / m - Math.PI / 2, t1 = Math.PI * (i + 1) / m - Math.PI / 2;
    for (let j = 0; j < n; j += 1) {
      const a0 = 2 * Math.PI * j / n, a1 = 2 * Math.PI * (j + 1) / n;
      out.push({pts: [q(t0, a0), q(t0, a1), q(t1, a1), q(t1, a0)], color, center: P(cx, cy, cz)});
    }
  }
  return out;
}

function polygons(plan, shot, t) {
  const set = plan.set3d || {};
  const room = set.caja || {ancho: 10, fondo: 10, alto: 3.4};
  const W = room.ancho, F = room.fondo, H = room.alto;
  const list = box(0, 0, 0, W, F, H, part => WALLS[part] || [60, 60, 60], true).filter(p => p.part !== "techo");
  for (let k = 1; k < W; k += 1) {
    list.push({pts: [P(k - 0.01, 0, 0.002), P(k + 0.01, 0, 0.002), P(k + 0.01, F, 0.002), P(k - 0.01, F, 0.002)], color: [70, 64, 56], flat: true});
  }
  for (const item of plan.objetos || []) {
    const w = item.ancho || 0.6, f = item.fondo || 0.5, h = item.alto || 0.8;
    list.push(...box(item.x - w / 2, item.y - f / 2, 0, item.x + w / 2, item.y + f / 2, h, [150, 140, 130]));
  }
  const labels = [];
  const people = peopleAt(plan, shot, t);
  Object.entries(people).forEach(([name, p], k) => {
    const color = COLORS[k % COLORS.length];
    const tall = (set.alturas || {})[name] || 1.72;
    list.push(...prism(p.x, p.y, 0, tall * 0.82, 0.21, color));
    list.push(...sphere(p.x, p.y, tall * 0.9, 0.12, color.map(c => Math.min(255, c * 1.1))));
    const look = p.mira && (people[p.mira] || position(plan, p.mira));
    if (look) {
      const a = Math.atan2(look.y - p.y, look.x - p.x);
      const nx = p.x + Math.cos(a) * 0.14, ny = p.y + Math.sin(a) * 0.14;
      list.push(...box(nx - 0.04, ny - 0.04, tall * 0.88, nx + 0.04, ny + 0.04, tall * 0.93, [30, 30, 30]));
    }
    labels.push([p.nombre, P(p.x, p.y, tall + 0.12), color]);
  });
  return {list, labels, lights: set.luces || []};
}

function basis(cam) {
  const C = P(cam.x, cam.y, cam.z);
  const T = P(...cam.mira);
  const f = unit(sub(T, C));
  let r = cross(f, [0, 1, 0]);
  if (norm(r) < 1e-6) r = [1, 0, 0];
  r = unit(r);
  return {C, f, r, u: cross(r, f)};
}

function clipNear(points, near = 0.05) {
  const out = [];
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i], b = points[(i + 1) % points.length];
    const inA = a[2] > near, inB = b[2] > near;
    if (inA) out.push(a);
    if (inA !== inB) out.push(add(a, mul(sub(b, a), (near - a[2]) / (b[2] - a[2]))));
  }
  return out;
}

// dibuja el cuadro del plano en el canvas (t: 0 inicio, 1 fin)
export function render(canvas, plan, shot, t = 0, cam = null) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width, height = canvas.height;
  cam = cam || camera(plan, shot, t);
  const {list, labels, lights} = polygons(plan, shot, t);
  const {C, f, r, u} = basis(cam);
  const fpx = (cam.focal || 35) / 36 * width;
  const faces = [];
  for (const poly of list) {
    const pts = poly.pts;
    let n = cross(sub(pts[1], pts[0]), sub(pts[2], pts[0]));
    if (norm(n) < 1e-9) continue;
    n = unit(n);
    const center = mul(pts.reduce((s, p) => add(s, p), [0, 0, 0]), 1 / pts.length);
    if (poly.center) {
      const outward = dot(n, sub(center, poly.center)) >= 0;
      if (outward === Boolean(poly.inside)) n = mul(n, -1);
    } else if (poly.flat) n = [0, 1, 0];
    if (dot(n, sub(C, center)) <= 0 && !poly.flat) continue;
    const view = clipNear(pts.map(q => { const d = sub(q, C); return [dot(d, r), dot(d, u), dot(d, f)]; }));
    if (view.length < 3) continue;
    const xy = view.map(v => [width / 2 + v[0] / v[2] * fpx, height / 2 - v[1] / v[2] * fpx]);
    const light = [0.28, 0.28, 0.28];
    for (const L of lights) {
      const toLight = sub(P(L.x, L.y, L.z), center);
      const distance = norm(toLight);
      const lambert = Math.max(0, dot(n, mul(toLight, 1 / distance)));
      const k = (L.intensidad || 1) * lambert / (1 + 0.04 * distance * distance) * 1.6;
      (L.color || [255, 255, 255]).forEach((c, i) => { light[i] += c / 255 * k; });
    }
    const color = poly.color.map((c, i) => Math.min(255, Math.round(c * light[i])));
    faces.push({depth: view.reduce((s, v) => s + v[2], 0) / view.length, xy, color, flat: Boolean(poly.flat)});
  }
  faces.sort((a, b) => (a.flat === b.flat ? b.depth - a.depth : a.flat ? -1 : 1));
  ctx.fillStyle = "#121212";
  ctx.fillRect(0, 0, width, height);
  for (const face of faces) {
    ctx.beginPath();
    face.xy.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.fillStyle = `rgb(${face.color.join(",")})`;
    ctx.strokeStyle = `rgb(${face.color.map(c => Math.max(0, c - 25)).join(",")})`;
    ctx.fill();
    ctx.stroke();
  }
  ctx.font = `${Math.max(11, Math.round(width / 50))}px system-ui, sans-serif`;
  ctx.textAlign = "center";
  for (const [name, point, color] of labels) {
    const d = sub(point, C);
    const v = [dot(d, r), dot(d, u), dot(d, f)];
    if (v[2] > 0.1) {
      ctx.fillStyle = `rgb(${color.join(",")})`;
      ctx.fillText(name, width / 2 + v[0] / v[2] * fpx, height / 2 - v[1] / v[2] * fpx - 4);
    }
  }
  // guias de tercios
  ctx.strokeStyle = "rgba(255,255,255,.12)";
  ctx.beginPath();
  for (const k of [1, 2]) {
    ctx.moveTo(width * k / 3, 0); ctx.lineTo(width * k / 3, height);
    ctx.moveTo(0, height * k / 3); ctx.lineTo(width, height * k / 3);
  }
  ctx.stroke();
  return cam;
}
