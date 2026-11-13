// ochsner2mqtt – Gastgeber für das Wärmepumpen-Dashboard (aus OTS-HomeAssistant, MIT).
// Stellt dem unveränderten Dashboard ein "hass"-Objekt bereit, das statt mit
// Home Assistant mit dem LoxBerry-Daemon spricht (über ajax.php → lokale API).

import { registerCards } from "./lib/card.js";

const LIVE_INTERVAL = 5000;

// Sprache und Texte aus LoxBerry (index.php: data-lang, window.O2M_L aus language_<sprache>.ini)
const APP_ROOT = document.getElementById("o2m-app");
const LANG = String((APP_ROOT && APP_ROOT.dataset.lang) || document.documentElement.lang || "en").slice(0, 2).toLowerCase();
const LT = window.O2M_L || {};
function T(key, params) {
  let s = LT[`APP.${key}`];
  if (s === undefined) s = key;
  if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined ? params[k] : m));
  return s;
}
const LIVE_INTERVAL_HIDDEN = 30000;

function apiUrl(ep, params) {
  const q = new URLSearchParams({ action: "api", ep });
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null) q.set(k, v);
  return `ajax.php?${q}`;
}

function toError(json, res) {
  const e = new Error((json && json.error && json.error.message) || `HTTP ${res.status}`);
  e.code = (json && json.error && json.error.code) || "error";
  return e;
}

async function apiGet(ep, params) {
  const res = await fetch(apiUrl(ep, params), { cache: "no-store", credentials: "same-origin" });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || (json && json.error)) throw toError(json, res);
  return json;
}

async function apiPost(ep, body) {
  const res = await fetch(apiUrl(ep), {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-O2M": "1" },
    body: JSON.stringify(body || {}),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || (json && json.error)) throw toError(json, res);
  return json;
}

/** Nachbildung von hass.connection (home-assistant-js-websocket) für den PlantStore. */
class Connection {
  constructor(host) {
    this.host = host;
    this.subs = new Set();
  }

  async sendMessagePromise(msg) {
    switch (msg && msg.type) {
      case "ochsner_local_ots/plants":
        return apiGet("plants");
      case "ochsner_local_ots/schedules":
        return apiGet("schedules", msg.force ? { force: 1 } : null);
      case "ochsner_local_ots/schedule/set": {
        const res = await apiPost("schedule_set", { circuit: msg.circuit, days: msg.days });
        this.host.refreshSoon();
        return res;
      }
      default: {
        const e = new Error(`Unbekannte Nachricht ${msg && msg.type}`);
        e.code = "unknown_command";
        throw e;
      }
    }
  }

  subscribeMessage(cb, msg) {
    if (!msg || msg.type !== "ochsner_local_ots/subscribe") return Promise.reject(new Error("unbekanntes Abo"));
    this.subs.add(cb);
    if (this.host.lastEvent) setTimeout(() => cb(this.host.lastEvent), 0);
    this.host.ensurePolling();
    return Promise.resolve(() => { this.subs.delete(cb); });
  }

  addEventListener() {}
  removeEventListener() {}
}

export class O2MHost {
  constructor(root) {
    this.root = root;
    this.statusEl = root.querySelector("[data-o2m=status]");
    this.connection = new Connection(this);
    this.states = {};
    this.status = null;
    this.lastEvent = null;
    this.timer = null;
    this.busy = false;
    this.dark = this._initialDark();
    this.card = document.createElement("ochsner-heatpump-card");
    this.card.setConfig({ view: "all", color_scheme: "ochsner", write_delay: 1500 });
    root.querySelector("[data-o2m=card]").appendChild(this.card);
    this._applyTheme();
    document.addEventListener("hass-more-info", (e) => this.moreInfo(e.detail && e.detail.entityId));
    document.addEventListener("visibilitychange", () => this.ensurePolling(true));
    const darkBtn = root.querySelector("[data-o2m=dark]");
    if (darkBtn) darkBtn.addEventListener("click", () => this.toggleDark());
    this.pushHass();
    this.poll();
  }

  // ---------------------------------------------------------------- hass-Objekt
  get hass() {
    return this._hass;
  }

  pushHass() {
    const tz = (this.status && this.status.time_zone) || Intl.DateTimeFormat().resolvedOptions().timeZone;
    this._hass = {
      connection: this.connection,
      states: this.states,
      language: LANG,
      locale: { language: LANG, number_format: "language", time_format: "24" },
      config: { unit_system: { temperature: "°C" }, time_zone: tz },
      themes: { darkMode: this.dark },
      panels: {},
      user: { is_admin: true },
      callService: (domain, service, data) => this.callService(domain, service, data),
      callWS: (msg) => this.callWS(msg),
    };
    this.card.hass = this._hass;
  }

  async callService(domain, service, data) {
    try {
      const res = await apiPost("service", { domain, service, data });
      this.refreshSoon();
      return res;
    } catch (err) {
      this.toast(err.message, "err");
      throw err;
    }
  }

  async callWS(msg) {
    if (msg && msg.type === "history/history_during_period") {
      return apiGet("history", { start: msg.start_time, end: msg.end_time, entity_ids: (msg.entity_ids || []).join(",") });
    }
    const e = new Error(T("NOT_SUPPORTED", { type: msg && msg.type }));
    e.code = "not_supported";
    throw e;
  }

  // ---------------------------------------------------------------- Live-Daten
  ensurePolling(now = false) {
    if (this.timer) clearTimeout(this.timer);
    const ms = now ? 50 : document.hidden ? LIVE_INTERVAL_HIDDEN : LIVE_INTERVAL;
    this.timer = setTimeout(() => this.poll(), ms);
  }

  refreshSoon() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => this.poll(), 700);
  }

  async poll() {
    if (this.busy) return this.ensurePolling();
    this.busy = true;
    try {
      const live = await apiGet("live");
      this.status = live.status || {};
      this.states = live.states || {};
      this.lastEvent = live.event;
      this.pushHass();
      for (const cb of [...this.connection.subs]) cb(live.event);
      this.renderStatus(null);
    } catch (err) {
      this.renderStatus(err);
    } finally {
      this.busy = false;
      this.ensurePolling();
    }
  }

  // ---------------------------------------------------------------- Statusleiste
  renderStatus(err) {
    if (!this.statusEl) return;
    const s = this.status || {};
    const chip = (cls, text, title = "") => `<span class="o2m-chip ${cls}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;
    const parts = [];
    if (err) parts.push(chip("bad", T("DAEMON_ERROR", { error: err.message })));
    else if (!s.connected) parts.push(chip("bad", T("HP_UNREACHABLE") + (s.error ? ": " + s.error : "")));
    else parts.push(chip("ok", T("HP_CONNECTED"), s.last_ok ? T("LAST_POLL", { time: new Date(s.last_ok).toLocaleTimeString(LANG) }) : ""));
    if (s.mqtt_topic !== undefined) parts.push(chip(s.mqtt_connected ? "ok" : "warn", s.mqtt_connected ? `MQTT ${s.mqtt_topic}/…` : T("MQTT_DOWN")));
    if (s.writes_enabled === false) parts.push(`<a class="o2m-chip warn" href="index.php?form=settings" title="${esc(T("LOCKED_TITLE"))}">${esc(T("LOCKED"))}</a>`);
    else if (s.flash) parts.push(chip("", T("WRITES_TODAY", { today: s.flash.today ?? 0, max: s.write_max_per_day ?? "–" }), T("WRITES_TOTAL", { total: s.flash.total ?? 0 })));
    this.statusEl.innerHTML = parts.join("");
  }

  toast(text, cls = "") {
    const t = document.createElement("div");
    t.className = `o2m-toast ${cls}`;
    t.textContent = text;
    this.root.appendChild(t);
    setTimeout(() => t.classList.add("show"), 10);
    setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 400); }, 6000);
  }

  // ---------------------------------------------------------------- Theme
  _initialDark() {
    try {
      const v = localStorage.getItem("o2m-dark");
      if (v === "1" || v === "0") return v === "1";
    } catch (_e) { /* Speicher nicht verfügbar */ }
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  toggleDark() {
    this.dark = !this.dark;
    try { localStorage.setItem("o2m-dark", this.dark ? "1" : "0"); } catch (_e) { /* egal */ }
    this._applyTheme();
    this.pushHass();
  }

  _applyTheme() {
    this.root.classList.toggle("o2m-dark", this.dark);
  }

  // ---------------------------------------------------------------- Detaildialog
  async moreInfo(entityId) {
    if (!entityId) return;
    const st = this.states[entityId];
    const dlg = this.root.querySelector("dialog.o2m-more");
    if (!dlg) return;
    const a = (st && st.attributes) || {};
    const name = a.friendly_name || entityId;
    const unit = a.unit_of_measurement ? ` ${a.unit_of_measurement}` : "";
    const rows = [];
    const label = (k) => (LT[`APP.ATTR_${k.toUpperCase()}`] !== undefined ? LT[`APP.ATTR_${k.toUpperCase()}`] : k);
    const tempish = /^(temperature|current_temperature|min_temp|max_temp|flow_temperature|flow_target|effective_target)$/;
    const unitOf = (k) => (tempish.test(k) ? " °C" : k === "current_humidity" ? " %" : k === "room_offset" || k === "offset" ? " K" : "");
    for (const [k, v] of Object.entries(a)) {
      if (["friendly_name", "unit_of_measurement", "hvac_modes", "preset_modes", "operation_list", "options", "target_temp_step"].includes(k)) continue;
      if (v === null || v === undefined || v === "") continue;
      const shown = typeof v === "number" ? v.toLocaleString(LANG) + unitOf(k) : word(v);
      rows.push(`<tr><th>${esc(label(k))}</th><td>${esc(shown)}</td></tr>`);
    }
    const stateText = st ? (Number.isFinite(Number(st.state)) && st.state !== "" ? Number(st.state).toLocaleString(LANG) : word(st.state)) : "–";
    dlg.innerHTML = `<form method="dialog"><header><h3>${esc(name)}</h3><button class="x" aria-label="${esc(T("CLOSE"))}">✕</button></header>
      <div class="big">${esc(stateText)}${esc(unit)}</div>
      ${rows.length ? `<table>${rows.join("")}</table>` : ""}
      <div class="chart" data-chart></div>
      <p class="muted"><code>${esc(entityId)}</code></p></form>`;
    if (typeof dlg.showModal === "function") dlg.showModal();
    try {
      const end = new Date(), start = new Date(end.getTime() - 24 * 3600 * 1000);
      const hist = await apiGet("history", { start: start.toISOString(), end: end.toISOString(), entity_ids: entityId });
      const series = (hist[entityId] || []).map((r) => [r.lu * 1000, Number(r.s)]).filter((p) => Number.isFinite(p[1]));
      if (series.length > 1) dlg.querySelector("[data-chart]").innerHTML = sparkline(series, start.getTime(), end.getTime(), unit);
    } catch (_e) { /* kein Verlauf */ }
  }
}

/** Zustandswörter (heat, eco, idle …) aus der Sprachdatei, sonst unverändert. */
function word(v) {
  const k = `APP.W_${String(v).toUpperCase()}`;
  return LT[k] !== undefined ? LT[k] : v;
}

function esc(v) {
  return String(v === undefined || v === null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function sparkline(series, t0, t1, unit) {
  const W = 520, H = 140, pad = 28;
  const vals = series.map((p) => p[1]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (hi - lo < 1e-6) { lo -= 1; hi += 1; }
  const x = (t) => pad + ((t - t0) / (t1 - t0)) * (W - pad - 6);
  const y = (v) => 8 + (1 - (v - lo) / (hi - lo)) * (H - 30);
  let d = "";
  series.forEach((p, i) => {
    const nx = x(Math.max(p[0], t0));
    if (i === 0) d += `M${nx.toFixed(1)},${y(p[1]).toFixed(1)}`;
    else d += `H${nx.toFixed(1)}V${y(p[1]).toFixed(1)}`;
  });
  d += `H${x(t1).toFixed(1)}`;
  const fmt = (v) => v.toLocaleString(LANG, { maximumFractionDigits: 1 });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(T("HISTORY_24H"))}">
    <text x="2" y="14" class="ax">${fmt(hi)}${esc(unit)}</text><text x="2" y="${H - 22}" class="ax">${fmt(lo)}${esc(unit)}</text>
    <path d="${d}" fill="none" stroke="var(--o2m-accent)" stroke-width="2"/>
    <text x="${pad}" y="${H - 4}" class="ax">${esc(T("AGO_24H"))}</text><text x="${W - 40}" y="${H - 4}" class="ax">${esc(T("NOW"))}</text></svg>`;
}

registerCards();
if (APP_ROOT) window.o2mHost = new O2MHost(APP_ROOT);
