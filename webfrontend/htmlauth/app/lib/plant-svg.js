// o2m: Anlagenschema – Neufassung für ochsner2mqtt. Ersetzt plant-svg.js aus
// permissionBRICK/OTS-HomeAssistant (MIT, commit 17a787e); Schnittstelle (vm) und
// die Hilfen textWidth/fitText/fitParts sind kompatibel geblieben.
// See app/LICENSE-OTS-HomeAssistant.txt.
//
// Hydraulik als geschlossene Kreise: Vorlauf oben, Rücklauf unten, Speicher
// (Warmwasser, Puffer) liegen zwischen beiden Leitungen. Jeder Weg des Wassers
// ist ein durchgehender Pfad (WP → Ventil → Heizkreis, Heizkreis → Rücklauf → WP,
// WP → Speicherwendel → Rücklauf). Die Fließanimation läuft über SMIL auf der
// gemeinsamen Zeitachse des SVG und ist an Abzweigen und Zusammenführungen
// phasengleich: Vorläufe zählen ab ihrer Quelle, Rückläufe bis zu ihrem Ziel.
// Zwei Layouts: breit (Heizkreise rechts) und schmal (Heizkreise darunter).

import { esc } from "./dom.js";
import { kindIcon } from "./icons.js";

const C = {
  heat: "var(--ohp-heat)",
  cool: "var(--ohp-cool)",
  dhw: "var(--ohp-dhw)",
  defrost: "var(--ohp-defrost)",
  standby: "var(--ohp-idle)",
  pool: "var(--ohp-pool)",
};
const OFF = "var(--ohp-pipe-off)";
const DASH = 16; // Periode des Strichmusters (px)
const SHIFT = 32; // Weg je Animationszyklus (px)
const DUR = "1.25s";

export const textWidth = (s, size) => String(s).length * size * 0.56;

export function fitText(s, maxW, size) {
  const str = String(s || "");
  if (textWidth(str, size) <= maxW) return str;
  const n = Math.max(1, Math.floor(maxW / (size * 0.56)) - 1);
  return str.slice(0, n) + "…";
}

/**
 * Join sub-line parts ([{t, keep}]) with " · ", dropping the lowest `keep`
 * first until the line fits maxW; a lone part that still does not fit is cut.
 */
export function fitParts(parts, maxW, size) {
  if (!Array.isArray(parts)) return fitText(parts, maxW, size);
  let list = parts.slice();
  const join = () => list.map((p) => p.t).join(" · ");
  while (list.length > 1 && textWidth(join(), size) > maxW) {
    const low = list.reduce((m, p) => (p.keep < m.keep ? p : m));
    list = list.filter((p) => p !== low);
  }
  return fitText(join(), maxW, size);
}

const r = (v) => Math.round(v * 10) / 10;
const label = (x, y, t, anchor = "middle", cls = "lbl", extra = "") =>
  `<text x="${r(x)}" y="${r(y)}" text-anchor="${anchor}" class="${cls}"${extra}>${esc(t)}</text>`;
const mix = (col, pct) => `color-mix(in srgb, ${col} ${pct}%, var(--ohp-card))`;

function reducedMotion() {
  try {
    return !!(globalThis.matchMedia && globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches);
  } catch (e) {
    return false;
  }
}

function polyLen(pts) {
  let l = 0;
  for (let i = 1; i < pts.length; i++) l += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  return l;
}

const polyD = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${r(p[0])} ${r(p[1])}`).join(" ");

/**
 * Leitungen in Ebenen: Ummantelung, Ruheleitung, aktive Leitung (Schimmer +
 * wandernde Striche). Überlappende Wege teilen sich die Phase, weil Vorläufe ab
 * ihrer Quelle (anchor "start") und Rückläufe bis zu ihrem Ziel (anchor "end")
 * gezählt werden.
 */
class Pipes {
  constructor(motion) {
    this.motion = motion;
    this.cas = [];
    this.base = [];
    this.glow = [];
    this.on = [];
    this.inner = [];
  }

  add(pts, { w = 5, col, active, anchor = "start", casing = true, innerLayer = false }) {
    const d = polyD(pts);
    const join = ` fill="none" stroke-linecap="round" stroke-linejoin="round"`;
    if (casing) this.cas.push(`<path d="${d}" stroke="var(--ohp-pipe)" stroke-width="${w + 4}"${join}/>`);
    const base = innerLayer ? this.inner : this.base;
    base.push(`<path d="${d}" stroke="${innerLayer ? "var(--ohp-ink2)" : OFF}" stroke-width="${w}"${innerLayer ? ` stroke-opacity=".35"` : ""}${join}/>`);
    if (!active) return;
    const len = polyLen(pts);
    let o = anchor === "end" ? -len : 0;
    o = (((o % DASH) + DASH) % DASH) - DASH; // (-16, 0]
    const anim = this.motion
      ? `<animate attributeName="stroke-dashoffset" values="${r(o)};${r(o - SHIFT)}" dur="${DUR}" repeatCount="indefinite"/>`
      : "";
    // Schimmer in einer Gruppe mit gemeinsamer Deckkraft: überlappende Wege
    // (Stamm mehrerer Heizkreise) werden dadurch nicht dunkler.
    (innerLayer ? this.inner : this.glow).push(`<path d="${d}" stroke="${col}" stroke-width="${w}"${innerLayer ? ` stroke-opacity=".3"` : ""}${join}/>`);
    (innerLayer ? this.inner : this.on).push(`<path d="${d}" stroke="${col}" stroke-width="${w}" stroke-dasharray="7 9" stroke-dashoffset="${r(o)}" fill="none" class="flowing">${anim}</path>`);
  }

  pipes() {
    return this.cas.join("") + this.base.join("") + `<g opacity=".3">${this.glow.join("")}</g>` + this.on.join("");
  }

  coils() {
    return this.inner.join("");
  }
}

function fan(cx, cy, rad, col, spin) {
  const blade = (a) =>
    `<path d="M${cx} ${cy} q ${r(rad * 0.3)} ${r(-rad * 0.75)} 0 ${r(-rad * 0.85)} q ${r(-rad * 0.35)} ${r(rad * 0.15)} 0 ${r(rad * 0.85)}" fill="${col}" fill-opacity=".85" transform="rotate(${a} ${cx} ${cy})"/>`;
  return (
    `<circle cx="${cx}" cy="${cy}" r="${r(rad + 5)}" fill="var(--ohp-card)" stroke="var(--ohp-line)" stroke-width="1.5"/>` +
    `<circle cx="${cx}" cy="${cy}" r="${r(rad + 1)}" fill="none" stroke="var(--ohp-line)" stroke-width="1" stroke-dasharray="2 3"/>` +
    `<g class="fan${spin ? " spin" : ""}" style="transform-origin:${cx}px ${cy}px">${[0, 120, 240].map(blade).join("")}` +
    `<circle cx="${cx}" cy="${cy}" r="${r(rad * 0.16)}" fill="var(--ohp-ink2)"/></g>`
  );
}

function zigzag(x, y, on, scale = 1) {
  const s = 6 * scale, h = 7 * scale;
  return `<path d="M${r(x)} ${r(y)} l${s} -${h} l${s} ${h} l${s} -${h} l${s} ${h} l${s} -${h} l${s} ${h}" fill="none" stroke="${on ? "var(--ohp-aux)" : "var(--ohp-pipe-off)"}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"><title>${on ? "on" : "off"}</title></path>`;
}

function snowflake(x, y, size) {
  const a = size;
  return `<g stroke="var(--ohp-defrost)" stroke-width="2" stroke-linecap="round" class="pulse">` +
    `<path d="M${x} ${y - a} V${y + a} M${r(x - a * 0.87)} ${r(y - a / 2)} L${r(x + a * 0.87)} ${r(y + a / 2)} M${r(x - a * 0.87)} ${r(y + a / 2)} L${r(x + a * 0.87)} ${r(y - a / 2)}"/></g>`;
}

/** Umwälzpumpe (Normsymbol: Kreis mit Dreieck in Fließrichtung). */
function pump(x, y, dir, col, on) {
  const t = dir > 0
    ? `M${r(x - 3.5)} ${r(y - 5)} L${r(x + 5)} ${y} L${r(x - 3.5)} ${r(y + 5)} Z`
    : `M${r(x + 3.5)} ${r(y - 5)} L${r(x - 5)} ${y} L${r(x + 3.5)} ${r(y + 5)} Z`;
  return `<circle cx="${r(x)}" cy="${r(y)}" r="8.5" fill="var(--ohp-card)" stroke="${on ? col : "var(--ohp-ink2)"}" stroke-width="1.6"/>` +
    `<path d="${t}" fill="${on ? col : "var(--ohp-ink2)"}" fill-opacity="${on ? 1 : 0.45}"/>`;
}

/** Umschaltventil Heizung/Warmwasser (Dreiwege-Symbol). */
function valve(x, y, toDhw, heatCol) {
  const tri = (pts, fill, op) => `<path d="M${pts.map((p) => `${r(p[0])} ${r(p[1])}`).join(" L")} Z" fill="${fill}" fill-opacity="${op}" stroke="var(--ohp-ink2)" stroke-width="1.1" stroke-linejoin="round"/>`;
  return `<g class="valve">` +
    tri([[x - 10, y - 6.5], [x - 10, y + 6.5], [x, y]], "var(--ohp-ink2)", 0.55) +
    tri([[x + 10, y - 6.5], [x + 10, y + 6.5], [x, y]], toDhw ? "var(--ohp-card)" : heatCol, toDhw ? 1 : 0.9) +
    tri([[x - 6.5, y + 10], [x + 6.5, y + 10], [x, y]], toDhw ? C.dhw : "var(--ohp-card)", toDhw ? 0.95 : 1) +
    `</g>`;
}

const dot = (x, y, col = "var(--ohp-ink2)") => `<circle cx="${r(x)}" cy="${r(y)}" r="3.4" fill="${col}"/>`;

function clickable(entity, aria, body, cls = "") {
  if (!entity) return `<g${cls ? ` class="${cls}"` : ""}>${body}</g>`;
  return `<g class="hit${cls ? " " + cls : ""}" data-more="${esc(entity)}" tabindex="0" role="button" aria-label="${esc(aria)}">${body}</g>`;
}

function rowColor(rw) {
  return rw.type === "pool" ? C.pool : rw.cooling ? C.cool : C.heat;
}

function row(rw, x, y, w, h, narrow) {
  const col = rowColor(rw);
  const chipSize = 11.5;
  const tw = textWidth(rw.chip || "", chipSize) + 18;
  let s = `<rect x="${r(x)}" y="${r(y - h / 2)}" width="${r(w)}" height="${h}" rx="12" class="rowbg${rw.active ? " on" : ""}" style="--rc:${col}"/>`;
  s += `<circle cx="${r(x + 26)}" cy="${r(y)}" r="17" fill="${rw.active ? col : OFF}" fill-opacity=".18"/>`;
  s += kindIcon(rw.kind, x + 26, y, rw.active ? col : "var(--ohp-ink2)");
  const chipX = x + w - 10 - tw;
  const chipY = narrow ? y - 20 : y - 12;
  const chipH = narrow ? 20 : 24;
  const nameMax = chipX - (x + 52) - 8;
  s += label(x + 52, y - 4, fitText(rw.name, nameMax, 14), "start", "name");
  const subMax = narrow ? w - 60 : chipX - (x + 52) - 8;
  s += label(x + 52, y + 15, fitParts(rw.sub, subMax, 12), "start", "lbl dim");
  if (rw.chip) {
    s += `<rect x="${r(chipX)}" y="${r(chipY)}" width="${r(tw)}" height="${chipH}" rx="${chipH / 2}" fill="${rw.chipColor || (rw.active ? col : OFF)}" fill-opacity=".2"/>`;
    s += label(chipX + tw / 2, chipY + chipH / 2 + 4, rw.chip, "middle", "chip");
  }
  return clickable(rw.entity, rw.name, s);
}

/**
 * vm = { id, mode, spin, moving, hpLabel, hpSub, flowT, retT, flowShort, retShort,
 *        buffer: {label, t, tNum, aux, auxOn, entity} | null,
 *        aux: {on} | null  (Zusatzheizung ohne Puffer),
 *        dhw: {label, t, tNum, targetNum, sub, active, charging, chargingText, entity} | null,
 *        hpEntity, rows: [{type, name, kind, sub, chip, active, cooling, entity}] }
 */
export function plantSVG(vm, width) {
  const W = Math.min(1600, Math.max(300, Math.round(width)));
  const st = flows(vm);
  if (W >= 560) {
    const g = wideGeometry(vm, W);
    if (g.rowW >= 230 || !vm.rows.length) return draw(vm, st, g);
  }
  return draw(vm, st, narrowGeometry(vm, W));
}

/** Wer fließt wohin, in welcher Farbe. */
function flows(vm) {
  const producing = !!vm.moving;
  const dhwCharge = !!(vm.dhw && vm.dhw.active && producing);
  const toHeat = producing && !dhwCharge;
  const flowCol = vm.mode === "cool" ? C.cool : vm.mode === "defrost" ? C.defrost : C.heat;
  const retCol = vm.mode === "cool" ? mix(C.heat, 60) : mix(C.cool, 75);
  return { producing, dhwCharge, toHeat, flowCol, retCol, hpCol: C[vm.mode] || C.standby };
}

function dhwTextWidth(vm, size) {
  const d = vm.dhw;
  if (!d) return 0;
  return Math.max(textWidth(d.label, size), textWidth(d.sub || "", size), textWidth(d.t || "", 17),
    d.charging ? textWidth(d.chargingText || "", size) + 12 : 0) + 4;
}

function wideGeometry(vm, W) {
  const g = { wide: true, W, size: 12 };
  g.hpX = 8; g.hpW = 116; g.hpR = g.hpX + g.hpW;
  g.fy = 40; g.ry = g.fy + 168;
  g.tankW = 54; g.tankTop = g.fy + 26; g.tankBot = g.ry - 26;
  g.bufW = 66; g.bufTop = g.fy + 18; g.bufBot = g.ry - 18;
  let x = g.hpR + 76;
  if (vm.dhw) {
    g.vx = x;
    g.dhwTx = g.vx + g.tankW / 2 + 10;
    g.dhwTw = Math.min(110, dhwTextWidth(vm, 12));
    x = g.dhwTx + g.dhwTw + 16;
  }
  if (vm.buffer) {
    g.bufX = vm.dhw ? x : g.hpR + 56;
    x = g.bufX + g.bufW + 42;
  } else if (!vm.dhw) x = g.hpR + 100;
  g.Tf = x;
  g.rowX = g.Tf + 46;
  g.rowR = W - 30;
  g.rowW = g.rowR - g.rowX;
  g.xr = W - 14;
  g.rowH = 54; g.gap = 10;
  const n = vm.rows.length;
  const block = n * g.rowH + Math.max(0, n - 1) * g.gap;
  const top = Math.max(10, (g.fy + g.ry) / 2 - block / 2);
  g.ys = vm.rows.map((_, i) => top + g.rowH / 2 + i * (g.rowH + g.gap));
  const yLast = n ? g.ys[n - 1] : g.ry;
  g.yb = n && yLast + g.rowH / 2 + 16 > g.ry ? yLast + g.rowH / 2 + 20 : g.ry;
  g.xUp = g.Tf - 20;
  g.H = Math.max(g.ry + 34, g.yb + 14, n ? yLast + g.rowH / 2 + 8 : 0);
  return g;
}

function narrowGeometry(vm, W) {
  const g = { wide: false, W, size: 11 };
  g.hpX = 8; g.hpW = W < 360 ? 80 : 92; g.hpR = g.hpX + g.hpW;
  g.fy = 34; g.ry = g.fy + 140;
  g.tankW = 44; g.tankTop = g.fy + 22; g.tankBot = g.ry - 22;
  g.bufW = 48; g.bufTop = g.fy + 16; g.bufBot = g.ry - 16;
  g.Tf = W - 12;
  let x = g.hpR + 62;
  if (vm.dhw) {
    g.vx = x;
    g.dhwTx = g.vx + g.tankW / 2 + 7;
    const room = (vm.buffer ? g.Tf - 16 - g.bufW - 10 : g.Tf - 14) - g.dhwTx;
    g.dhwTw = Math.max(36, Math.min(dhwTextWidth(vm, 11), room));
    x = g.dhwTx + g.dhwTw + 10;
  }
  if (vm.buffer) g.bufX = vm.dhw ? x : g.hpR + 40;
  g.yc = g.ry + 30;
  g.rowH = 54; g.gap = 8;
  g.rowL = 28; g.rowRt = W - 40; g.rowW = g.rowRt - g.rowL; g.xl = 12;
  const rowsTop = g.yc + 16;
  g.ys = vm.rows.map((_, i) => rowsTop + g.rowH / 2 + i * (g.rowH + g.gap));
  const n = vm.rows.length;
  g.H = n ? g.ys[n - 1] + g.rowH / 2 + 6 : g.ry + 30;
  return g;
}

function draw(vm, st, g) {
  const P = new Pipes(!reducedMotion());
  const rows = vm.rows;
  const n = rows.length;
  const hasBuf = !!vm.buffer;
  const bufR = hasBuf ? g.bufX + g.bufW : 0;
  const portIn = hasBuf ? g.bufX + (g.wide ? 14 : 12) : 0; // Puffer: Ein-/Ausgänge links/rechts
  const portOut = hasBuf ? bufR - (g.wide ? 14 : 12) : 0;
  const anyRow = rows.some((x) => x.active);
  const fw = g.wide ? 6 : 5; // Hauptleitung
  const bw = g.wide ? 5 : 4.5; // Abzweige

  // --- Warmwasser: WP → Ventil → Speicher, Wendel, Speicher → Rücklauf → WP
  if (vm.dhw) {
    P.add([[g.hpR, g.fy], [g.vx, g.fy], [g.vx, g.tankTop]], { w: bw, col: C.dhw, active: st.dhwCharge });
    const coil = [[g.vx, g.tankTop], [g.vx, g.tankTop + (g.wide ? 30 : 24)]];
    const dx = g.tankW / 2 - 11;
    let y = g.tankTop + (g.wide ? 34 : 28), left = true;
    while (y < g.tankBot - 14) {
      coil.push([g.vx + (left ? -dx : dx), y]);
      left = !left;
      y += g.wide ? 9 : 8;
    }
    coil.push([g.vx, g.tankBot]);
    P.add(coil, { w: 2.6, col: C.dhw, active: st.dhwCharge, casing: false, innerLayer: true });
    P.add([[g.vx, g.tankBot], [g.vx, g.ry], [g.hpR, g.ry]], { w: bw, col: st.retCol, active: st.dhwCharge, anchor: "end" });
  }

  // --- Heizseite
  const rowFlowPts = (i, srcPts) => {
    const y = g.ys[i];
    return g.wide
      ? [...srcPts, [g.Tf, g.fy], [g.Tf, y], [g.rowX, y]]
      : [...srcPts, [g.Tf, g.fy], [g.Tf, y], [g.rowRt, y]];
  };
  const retTarget = hasBuf ? [[portOut, g.wide ? g.ry : g.yc], [portOut, g.bufBot]] : null;
  const rowRetPts = (i) => {
    const y = g.ys[i];
    let pts;
    if (g.wide) {
      pts = [[g.rowR, y], [g.xr, y], [g.xr, g.yb]];
      if (g.yb !== g.ry) pts.push([g.xUp, g.yb], [g.xUp, g.ry]);
    } else {
      const xUp = hasBuf ? portOut : vm.dhw ? g.vx + 26 : g.hpR + 34;
      pts = [[g.rowL, y], [g.xl, y], [g.xl, g.yc], [xUp, g.yc]];
      if (!hasBuf) pts.push([xUp, g.ry]);
    }
    if (hasBuf) {
      if (g.wide) pts.push(...retTarget);
      else pts.push([portOut, g.bufBot]);
    } else pts.push([g.hpR, g.ry]);
    return pts;
  };

  if (hasBuf) {
    // Primärkreis WP ↔ Puffer
    P.add([[g.hpR, g.fy], [portIn, g.fy], [portIn, g.bufTop]], { w: fw, col: st.flowCol, active: st.toHeat });
    P.add([[portIn, g.bufBot], [portIn, g.ry], [g.hpR, g.ry]], { w: fw, col: st.retCol, active: st.toHeat, anchor: "end" });
    // Sekundärkreis Puffer ↔ Heizkreise
    const src = [[portOut, g.bufTop], [portOut, g.fy]];
    rows.forEach((rw, i) => {
      P.add(rowFlowPts(i, src), { w: bw, col: rowColor(rw), active: rw.active });
      P.add(rowRetPts(i), { w: bw, col: st.retCol, active: rw.active, anchor: "end" });
    });
  } else if (n) {
    const circ = (rw) => rw.active && !st.dhwCharge;
    const fcol = (rw) => (st.producing ? (rw.type === "pool" ? C.pool : st.flowCol) : C.standby);
    // Hauptleitung nur eigens zeichnen, wenn kein Heizkreis läuft (sonst deckt sie der Weg zum Heizkreis ab)
    const mainOn = st.toHeat && !rows.some(circ);
    const mainCol = st.flowCol;
    P.add([[g.hpR, g.fy], [g.Tf, g.fy]], { w: fw, col: mainCol, active: mainOn });
    const joinX = g.wide ? (g.yb !== g.ry ? g.xUp : g.Tf) : vm.dhw ? g.vx + 26 : g.hpR + 34;
    P.add([[joinX, g.ry], [g.hpR, g.ry]], { w: fw, col: st.retCol, active: mainOn, anchor: "end" });
    rows.forEach((rw, i) => {
      P.add(rowFlowPts(i, [[g.hpR, g.fy]]), { w: bw, col: fcol(rw), active: circ(rw) });
      P.add(rowRetPts(i), { w: bw, col: st.retCol, active: circ(rw), anchor: "end" });
    });
  } else {
    // keine Heizkreise sichtbar (z. B. Gebäudeleittechnik): nur Anschluss andeuten
    const xe = Math.min(g.W - 20, g.hpR + 200);
    P.add([[g.hpR, g.fy], [xe, g.fy]], { w: fw, col: st.flowCol, active: st.toHeat });
    P.add([[xe, g.ry], [g.hpR, g.ry]], { w: fw, col: st.retCol, active: st.toHeat, anchor: "end" });
  }

  let s = `<svg viewBox="0 0 ${g.W} ${r(g.H)}" class="plant${g.wide ? "" : " narrow"}" role="img" aria-label="${esc(vm.aria || "")}">`;
  s += defs(vm, st);

  // Hintergrundkörper: Außeneinheit, Speicher
  s += hpUnit(vm, st, g);
  if (vm.dhw) s += clickable(vm.dhw.entity, vm.dhw.label, tankBody(vm, g), "tank");
  if (hasBuf) s += clickable(vm.buffer.entity, vm.buffer.label, bufferBody(vm, st, g), "tank");

  s += `<g class="pipes">${P.pipes()}</g>`;
  s += `<g class="coil">${P.coils()}</g>`;

  // Armaturen
  let fx = "";
  if (vm.dhw) {
    fx += valve(g.vx, g.fy, st.dhwCharge, st.flowCol);
    fx += dot(g.vx, g.ry);
  }
  if (n > 1) {
    const yMin = Math.min(...g.ys), yMax = Math.max(...g.ys);
    g.ys.forEach((y) => {
      if (y > Math.min(g.fy, yMin) && y < Math.max(g.fy, yMax)) fx += dot(g.Tf, y);
      if (g.wide ? y > yMin : y < yMax) fx += dot(g.wide ? g.xr : g.xl, y);
    });
  }
  rows.forEach((rw, i) => {
    const on = rw.active && (hasBuf || !st.dhwCharge);
    const px = g.wide ? g.Tf + 23 : (g.Tf + g.rowRt) / 2;
    fx += pump(px, g.ys[i], g.wide ? 1 : -1, rowColor(rw), on);
  });
  s += `<g class="fittings">${fx}</g>`;

  // Beschriftung der Hauptleitungen
  const lsz = g.wide ? "lbl halo" : "lbl sm halo";
  if (vm.flowT) s += label(g.hpR + 6, g.fy - (g.wide ? 11 : 9), `${vm.flowShort} ${vm.flowT}`, "start", lsz);
  if (vm.retT) s += label(g.hpR + 6, g.ry + (g.wide ? 19 : 16), `${vm.retShort} ${vm.retT}`, "start", lsz + " dim");

  if (vm.dhw) s += clickable(vm.dhw.entity, vm.dhw.label, dhwText(vm, st, g));
  if (hasBuf) s += clickable(vm.buffer.entity, vm.buffer.label, bufferText(vm, g));

  rows.forEach((rw, i) => {
    s += g.wide ? row(rw, g.rowX, g.ys[i], g.rowW, g.rowH, false) : row(rw, g.rowL, g.ys[i], g.rowW, g.rowH, true);
  });
  return s + `</svg>`;
}

function heatShare(t, lo, hi) {
  if (t === undefined || t === null || !Number.isFinite(Number(t))) return 0.45;
  return Math.max(0.08, Math.min(1, (Number(t) - lo) / (hi - lo)));
}

function defs(vm, st) {
  const id = vm.id;
  const d = vm.dhw ? heatShare(vm.dhw.tNum, 18, Math.max(40, (vm.dhw.targetNum || 50) + 2)) : 0;
  const b = vm.buffer ? heatShare(vm.buffer.tNum, 18, 50) : 0;
  const bcol = vm.mode === "cool" ? C.cool : C.heat;
  return `<defs>` +
    `<linearGradient id="dhw${id}" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0" stop-color="${C.dhw}" stop-opacity="${r(0.25 + 0.6 * d)}"/>` +
    `<stop offset="${r(0.35 + 0.4 * d)}" stop-color="${C.dhw}" stop-opacity="${r(0.12 + 0.35 * d)}"/>` +
    `<stop offset="1" stop-color="${C.cool}" stop-opacity=".12"/></linearGradient>` +
    `<linearGradient id="buf${id}" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0" stop-color="${bcol}" stop-opacity="${r(0.2 + 0.55 * b)}"/>` +
    `<stop offset="${r(0.3 + 0.4 * b)}" stop-color="${bcol}" stop-opacity="${r(0.1 + 0.3 * b)}"/>` +
    `<stop offset="1" stop-color="${C.cool}" stop-opacity=".14"/></linearGradient>` +
    `<linearGradient id="unit${id}" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0" stop-color="var(--ohp-card2)"/><stop offset="1" stop-color="color-mix(in srgb, var(--ohp-ink) 8%, var(--ohp-card))"/></linearGradient>` +
    `</defs>`;
}

function hpUnit(vm, st, g) {
  const x = g.hpX, w = g.hpW;
  const y = g.fy - (g.wide ? 30 : 26);
  const h = g.ry + (g.wide ? 26 : 18) - y;
  const cx = x + w / 2;
  const rad = g.wide ? 34 : 29;
  const cy = y + rad + (g.wide ? 22 : 16);
  const col = vm.spin ? st.hpCol : "var(--ohp-ink2)";
  let s = `<rect x="${x}" y="${r(y)}" width="${w}" height="${r(h)}" rx="14" fill="url(#unit${vm.id})" stroke="var(--ohp-line)" class="unit"/>`;
  s += fan(cx, r(cy), rad, col, vm.spin);
  // Lüftungsschlitze
  const ly = cy + rad + (g.wide ? 18 : 13);
  for (let i = 0; i < 3; i++) {
    s += `<path d="M${r(x + 16)} ${r(ly + i * 7)} H${r(x + w - 16)}" stroke="var(--ohp-line)" stroke-width="2" stroke-linecap="round"/>`;
  }
  const by = y + h - (g.wide ? 30 : 24);
  s += label(cx, by, fitText(vm.hpLabel, w - 12, g.wide ? 13 : 11), "middle", `lbl unitname${g.wide ? "" : " sm"}`);
  if (vm.hpSub) s += label(cx, by + (g.wide ? 16 : 14), fitText(vm.hpSub, w - 12, 11), "middle", "lbl sm dim");
  if (vm.mode === "defrost") s += snowflake(x + 16, y + 16, 7);
  if (vm.aux && !vm.buffer) s += `<g>${zigzag(cx - 13.5, ly + 30, vm.aux.on, 0.75)}<title>${esc(vm.auxTitle || "")}</title></g>`;
  // Anschlüsse
  s += `<rect x="${r(g.hpR - 3)}" y="${r(g.fy - 6)}" width="6" height="12" rx="2" fill="var(--ohp-ink2)" opacity=".5"/>`;
  s += `<rect x="${r(g.hpR - 3)}" y="${r(g.ry - 6)}" width="6" height="12" rx="2" fill="var(--ohp-ink2)" opacity=".5"/>`;
  return clickable(vm.hpEntity, vm.hpLabel, s, "unitg");
}

function tankBody(vm, g) {
  const x = g.vx - g.tankW / 2;
  const h = g.tankBot - g.tankTop;
  let s = `<rect x="${r(x - 3)}" y="${r(g.tankTop - 3)}" width="${g.tankW + 6}" height="${r(h + 6)}" rx="${g.tankW / 2 - 2}" fill="none" stroke="var(--ohp-line)" stroke-width="1" opacity=".7"/>`;
  s += `<rect x="${r(x)}" y="${r(g.tankTop)}" width="${g.tankW}" height="${r(h)}" rx="${g.tankW / 2 - 5}" fill="url(#dhw${vm.id})" stroke="var(--ohp-line)" stroke-width="1.5" class="tankbody"/>`;
  // Fühlerposition
  s += `<circle cx="${r(x + g.tankW - 7)}" cy="${r(g.tankTop + h * 0.42)}" r="2.6" fill="var(--ohp-ink2)" opacity=".55"/>`;
  return s;
}

function dhwText(vm, st, g) {
  const d = vm.dhw;
  const mid = (g.fy + g.ry) / 2;
  const x = g.dhwTx, w = g.dhwTw;
  const sz = g.wide ? 12 : 11;
  let s = "";
  const showLabel = w >= textWidth(d.label, sz) * 0.7;
  if (showLabel) s += label(x, mid - 20, fitText(d.label, w, sz), "start", `lbl dim${g.wide ? "" : " sm"}`);
  s += label(x, mid + 2, d.t || "–", "start", "big");
  if (d.sub) s += label(x, mid + 19, fitText(d.sub, w, sz), "start", `lbl dim${g.wide ? "" : " sm"}`);
  if (st.dhwCharge && d.chargingText) {
    const tw = Math.min(w, textWidth(d.chargingText, 10.5) + 12);
    s += `<rect x="${r(x)}" y="${r(mid + 27)}" width="${r(tw)}" height="16" rx="8" fill="${C.dhw}" fill-opacity=".28"/>`;
    s += label(x + tw / 2, mid + 38.5, fitText(d.chargingText, tw - 6, 10.5), "middle", "chip sm");
  }
  return s;
}

function bufferBody(vm, st, g) {
  const h = g.bufBot - g.bufTop;
  let s = `<rect x="${r(g.bufX - 3)}" y="${r(g.bufTop - 3)}" width="${g.bufW + 6}" height="${r(h + 6)}" rx="${g.bufW / 2 - 4}" fill="none" stroke="var(--ohp-line)" stroke-width="1" opacity=".7"/>`;
  s += `<rect x="${g.bufX}" y="${r(g.bufTop)}" width="${g.bufW}" height="${r(h)}" rx="${g.bufW / 2 - 7}" fill="url(#buf${vm.id})" stroke="var(--ohp-line)" stroke-width="1.5" class="tankbody"/>`;
  if (vm.buffer.aux) s += zigzag(g.bufX + g.bufW / 2 - 18, g.bufBot - 18, vm.buffer.auxOn, 1);
  return s;
}

function bufferText(vm, g) {
  const cx = g.bufX + g.bufW / 2;
  const mid = (g.bufTop + g.bufBot) / 2;
  let s = label(cx, mid - 12, fitText(vm.buffer.label, g.bufW - 6, g.wide ? 12 : 11), "middle", `lbl ink${g.wide ? "" : " sm"}`);
  s += label(cx, mid + 10, vm.buffer.t || "–", "middle", "big");
  return s;
}
