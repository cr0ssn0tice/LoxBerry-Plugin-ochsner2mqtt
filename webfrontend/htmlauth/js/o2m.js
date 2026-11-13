// ochsner2mqtt – Logik der Plugin-Seiten (Störungen, Werte, Editor, Loxone, Konfiguration, Log).
// Texte kommen aus den LoxBerry-Sprachdateien (window.O2M_L, von index.php gesetzt).
'use strict';
const O2M = (() => {
  const root = document.getElementById('o2m');
  if (!root) return {};
  const form = root.dataset.form;
  const LANG = document.documentElement.lang || 'en';
  const LT = window.O2M_L || {};
  /** Text aus der Sprachdatei; {name}-Platzhalter werden ersetzt. */
  const L = (key, params) => {
    let s = (LT[key] !== undefined ? LT[key] : key).replace(/\\n/g, '\n');
    if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined ? params[k] : m));
    return s;
  };
  let state = null;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const api = (action) => fetch('ajax.php?action=' + action, {cache: 'no-store', credentials: 'same-origin'}).then(r => r.json());
  const post = (action, body) => fetch('ajax.php?action=' + action, {method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-O2M': '1'}, body: JSON.stringify(body || {})}).then(r => r.json());
  const num = (v) => (typeof v === 'number' ? v.toLocaleString(LANG) : v);
  const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString(LANG) : '–');
  const fmtVal = (p) => {
    if (p.text !== null && p.text !== undefined && p.text !== '' && p.platform !== 'number') return p.text;
    if (p.value === null || p.value === undefined) return '–';
    return num(p.value) + (p.unit ? ' ' + p.unit : '');
  };
  const topic = (p) => (state?.config?.mqtt_topic || 'ochsner') + '/' + p.slug;
  const setMsg = (el, cls, text) => { if (el) { el.className = 'o2m-msg ' + (cls ? 'o2m-' + cls : ''); el.textContent = text; } };
  const tile = ([k, v]) => {
    const plain = String(v).replace(/<small>.*?<\/small>/g, '').replace(/<[^>]+>/g, '');
    return `<div class="o2m-tile"><div class="k">${k}</div><div class="v${plain.length > 13 ? ' long' : ''}">${v}</div></div>`;
  };
  const callout = (cls, title, body) => `<div class="lb-callout ${cls}"><span class="lb-callout-title">${title}</span>${body}</div>`;
  const prettyModel = (m) => {
    const x = /^AIR\s*HAWK\s*(\d{3})/i.exec(m || '');
    return x ? `Air Hawk ${x[1]} <small>${esc(m)}</small>` : esc(m || '–');
  };
  const copyBtn = (text) => `<button type="button" class="copy" data-copy="${esc(text)}" title="${esc(L('COMMON.COPY_TITLE'))}">${esc(L('COMMON.COPY'))}</button>`;

  document.querySelectorAll('section[data-section]').forEach(s => { s.hidden = s.dataset.section !== form; });

  // ------------------------------------------------------------ Klicks (ohne Inline-Handler)
  root.addEventListener('click', (e) => {
    const copy = e.target.closest('button.copy');
    if (copy) return doCopy(copy);
    const show = e.target.closest('[data-showpass]');
    if (show) {
      const inp = $(show.dataset.showpass);
      inp.type = inp.type === 'password' ? 'text' : 'password';
      return;
    }
    const sel = e.target.closest('[data-sel]');
    if (sel) return lxSelect(sel.dataset.sel);
    const wr = e.target.closest('[data-write]');
    if (wr) return writePoint(wr.dataset.write);
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    if (act === 'poll' || act === 'rescan') cmd(act);
    else if (act === 'restart') daemon('restart');
    else if (act === 'ack') ackAlarm();
    else if (act === 'clear_history') { if (confirm(L('OV.CONFIRM_CLEAR'))) cmd('clear_alarm_history'); }
    else if (act === 'lx_apply') lxApply();
    else if (act === 'log_reload') loadLog();
  });
  function doCopy(b) {
    const t = b.dataset.copy;
    const done = () => {
      b.textContent = L('COMMON.COPIED'); b.classList.add('done');
      setTimeout(() => { b.textContent = L('COMMON.COPY'); b.classList.remove('done'); }, 1400);
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(t).then(done, () => fallbackCopy(t, done));
    else fallbackCopy(t, done);
  }
  function fallbackCopy(t, done) {
    const ta = document.createElement('textarea');
    ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); done(); } catch (e) { /* Kopieren nicht möglich */ }
    ta.remove();
  }

  async function loadState() { state = await api('state'); return state; }

  // ------------------------------------------------------------ Befehle an den Dienst
  async function waitResult(id, msgEl) {
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 750));
      const res = await api('cmd_results');
      const hit = res.find(r => r.cmd_id === id);
      if (hit) { setMsg(msgEl, hit.ok ? 'ok' : 'bad', hit.message || (hit.ok ? 'OK' : L('COMMON.ERROR'))); return hit; }
    }
    setMsg(msgEl, 'warn', L('COMMON.NO_ANSWER'));
    return null;
  }
  async function cmd(action, extra, msgEl) {
    msgEl = msgEl || $('ov-msg');
    setMsg(msgEl, 'muted', L('COMMON.SENT'));
    const r = await post('cmd', Object.assign({action}, extra || {}));
    if (!r.ok) { setMsg(msgEl, 'bad', r.error); return null; }
    const res = await waitResult(r.id, msgEl);
    setTimeout(refresh, 1500);
    return res;
  }
  async function daemon(op) {
    setMsg($('ov-msg'), 'muted', '…');
    const r = await post('daemon', {op});
    setMsg($('ov-msg'), r.ok ? 'ok' : 'bad', r.ok ? L('OV.RESTARTED') : (r.output || r.error || ''));
  }
  function ackAlarm() {
    const p = (state?.points || []).find(p => p.slug === 'error_quittieren');
    if (!p) return;
    const opt = Object.entries(p.choices || {}).find(([, v]) => /quittier|acknowl/i.test(v));
    if (!opt) { alert(L('OV.ACK_UNKNOWN')); return; }
    if (confirm(L('OV.CONFIRM_ACK'))) cmd('write', {slug: p.slug, value: opt[0]});
  }

  // ------------------------------------------------------------ Störungen
  async function renderOverview() {
    const s = await loadState();
    const st = s.status || {};
    const id = s.identity || {};
    const yes = (ok, a, b) => (ok ? `<span class="o2m-ok">● ${a}</span>` : `<span class="${b[0]}">● ${b[1]}</span>`);
    const tiles = [
      [L('OV.T_CONNECTION'), yes(st.connected, L('COMMON.CONNECTED'), ['o2m-bad', L('COMMON.DISCONNECTED')])],
      [L('OV.T_PLANT'), prettyModel(id.model)],
      [L('OV.T_SOFTWARE'), esc(id.sw_version || '–')],
      [L('OV.T_LAST_POLL'), esc(fmtTime(st.last_ok)) + (st.poll_ms ? ` <small>(${st.poll_ms} ms)</small>` : '')],
      [L('OV.T_POINTS'), (s.points || []).length + ` <small>${esc(L('OV.T_POINTS_OF', {n: s.catalog?.points || '–'}))}</small>`],
      ['MQTT', yes(s.mqtt_connected, L('COMMON.CONNECTED'), ['o2m-warn', L('COMMON.NOT_CONNECTED')])],
      [L('OV.T_WRITES'), (s.flash?.today ?? 0) + ` <small>${esc(L('OV.T_WRITES_SUB', {total: s.flash?.total ?? 0}))}</small>`],
      [L('OV.T_WRITE_MODE'), s.config?.writes_enabled ? `<span class="o2m-warn">${L('OV.ALLOWED')}</span>` : L('OV.LOCKED')],
    ];
    $('ov-tiles').innerHTML = tiles.map(tile).join('');
    const alarms = s.alarms_active || [];
    let html = '';
    if (st.error) html += callout('o2m-state-bad', L('OV.CONN_PROBLEM'), esc(st.error));
    if (alarms.length) {
      html += callout('o2m-state-bad', alarms.length === 1 ? L('OV.ONE_FAULT') : L('OV.N_FAULTS', {n: alarms.length}),
        '<ul>' + alarms.map(a => `<li>${esc(a.name)}${a.text ? ' – ' + esc(a.text) : ''}</li>`).join('') + '</ul>');
    } else if (st.connected) {
      html += callout('o2m-state-ok', L('OV.NO_FAULT'), L('OV.NO_FAULT_TEXT'));
    } else if (!st.error) {
      html += callout('lb-callout-warning', L('OV.NOT_CONNECTED'), L('OV.NOT_CONNECTED_TEXT'));
    }
    $('ov-alarm').innerHTML = html;
    $('ov-ack').hidden = !(s.config?.writes_enabled && (s.points || []).some(p => p.slug === 'error_quittieren'));
    const hist = await api('alarm_history');
    $('ov-history').innerHTML = hist.length ? hist.slice(0, 200).map(h =>
      `<tr><td class="num">${esc(fmtTime(h.ts))}</td><td>${h.event === 'kommt' ? `<span class="badge b-red">${esc(L('OV.EV_ON'))}</span>` : `<span class="badge b-green">${esc(L('OV.EV_OFF'))}</span>`}</td>
       <td>${esc(h.name)}</td><td>${esc(h.text ?? h.raw)}${h.token ? ' <code>' + esc(h.token) + '</code>' : ''}</td></tr>`).join('')
      : `<tr><td colspan="4" class="o2m-muted">${esc(L('OV.HISTORY_EMPTY'))}</td></tr>`;
  }
  /** LoxBerry-Benachrichtigungen des Plugins (gleicher Weg wie LBLog::get_notifications_html). */
  function loadNotifications() {
    const box = $('ov-notify');
    if (!box || !window.jQuery) return;
    jQuery.post('/admin/system/ajax/ajax-notification-handler.cgi',
      {action: 'get_notifications_html', package: root.dataset.package || 'ochsner2mqtt'})
      .done((html, _s, xhr) => { if (xhr.status === 200 && html) jQuery(box).html(html); })
      .fail(() => { /* kein LoxBerry-Handler (Entwicklung) */ });
  }

  // ------------------------------------------------------------ Alle Werte
  function renderValues() {
    if (!state) return;
    const f = ($('val-filter').value || '').toLowerCase();
    const onlyAlarms = $('val-alarms').checked;
    const pts = (state.points || []).filter(p =>
      (!onlyAlarms || p.alarm !== null) &&
      (!f || (p.name + ' ' + p.module + ' ' + topic(p)).toLowerCase().includes(f)));
    let html = '', grp = null;
    for (const p of pts) {
      const g = p.module + (p.hc && state.hc_names?.[p.hc] ? ' – ' + state.hc_names[p.hc] : '');
      if (g !== grp) { grp = g; html += `<tr class="grp"><td colspan="4">${esc(g)}</td></tr>`; }
      const badge = p.alarm === true ? ` <span class="badge b-red">${esc(L('VAL.B_FAULT'))}</span>` : (p.alarm === false ? ' <span class="badge b-green">ok</span>' : '');
      html += `<tr><td>${esc(p.name)}${badge}${p.writable ? ` <span class="badge b-grey">${esc(L('VAL.B_WRITABLE'))}</span>` : ''}</td>
        <td class="num">${esc(fmtVal(p))}</td><td><code>${esc(topic(p))}</code></td><td><code class="o2m-muted sm">${esc(p.id)}</code></td></tr>`;
    }
    $('val-body').innerHTML = html || `<tr><td colspan="4" class="o2m-muted">${esc(L('COMMON.NO_DATA'))}</td></tr>`;
    $('val-meta').textContent = L('VAL.META', {n: pts.length, time: fmtTime(state.updated)});
  }

  // ------------------------------------------------------------ Experten-Editor
  function inputFor(p) {
    const cur = p.value ?? '';
    if (p.platform === 'select' && p.choices) {
      return `<select class="lb-input lb-select" data-slug="${esc(p.slug)}" aria-label="${esc(p.name)}">` + Object.entries(p.choices).map(([k, v]) =>
        `<option value="${esc(k)}" ${String(k) === String(cur) ? 'selected' : ''}>${esc(v)}</option>`).join('') + '</select>';
    }
    if (p.platform === 'switch') {
      return `<select class="lb-input lb-select" data-slug="${esc(p.slug)}" aria-label="${esc(p.name)}"><option value="1" ${cur == 1 ? 'selected' : ''}>${esc(L('ED.ON'))}</option>
              <option value="0" ${cur == 0 ? 'selected' : ''}>${esc(L('ED.OFF'))}</option></select>`;
    }
    if (p.platform === 'number') {
      return `<input class="lb-input o2m-small" type="number" data-slug="${esc(p.slug)}" value="${esc(cur)}" aria-label="${esc(p.name)}"
              ${p.min !== null ? 'min="' + p.min + '"' : ''} ${p.max !== null ? 'max="' + p.max + '"' : ''} step="${p.step || 'any'}">`;
    }
    return `<input class="lb-input" data-slug="${esc(p.slug)}" value="${esc(cur)}" maxlength="20" aria-label="${esc(p.name)}">`;
  }
  async function renderEdit() {
    if (!state) await loadState();
    const enabled = !!state.config?.writes_enabled;
    $('ed-locked').hidden = enabled;
    $('ed-info').hidden = !enabled;
    $('ed-flash').textContent = L('ED.FLASH_TEXT', {max: state.config?.write_max_per_day, today: state.flash?.today ?? 0,
                                                     total: state.flash?.total ?? 0});
    const f = ($('ed-filter').value || '').toLowerCase();
    const pts = (state.points || []).filter(p => p.writable && (!f || (p.name + ' ' + p.module).toLowerCase().includes(f)));
    let html = '', grp = null;
    for (const p of pts) {
      const g = p.module + (p.hc && state.hc_names?.[p.hc] ? ' – ' + state.hc_names[p.hc] : '');
      if (g !== grp) { grp = g; html += `<tr class="grp"><td colspan="5">${esc(g)}</td></tr>`; }
      const range = p.platform === 'number' ? `${p.min ?? '–'} … ${p.max ?? '–'}${p.unit ? ' ' + esc(p.unit) : ''}${p.step ? `<br><span class="sm">${esc(L('ED.STEP', {step: p.step}))}</span>` : ''}` : '';
      html += `<tr><td>${esc(p.name)}<br><code class="o2m-muted sm">${esc(p.slug)}</code></td><td class="num">${esc(fmtVal(p))}</td><td class="o2m-muted num">${range}</td>
        <td>${inputFor(p)}</td><td><button type="button" class="lb-btn lb-btn-sm" ${enabled ? '' : 'disabled'} data-write="${esc(p.slug)}">${esc(L('ED.WRITE'))}</button></td></tr>`;
    }
    $('ed-body').innerHTML = html || `<tr><td colspan="5" class="o2m-muted">${esc(L('ED.NONE'))}</td></tr>`;
    const wl = await api('write_log');
    $('ed-log').innerHTML = wl.slice(0, 100).map(w => `<tr><td class="num">${esc(fmtTime(w.ts))}</td><td>${esc(w.source)}</td>
      <td>${esc(w.name || w.slug)}</td><td class="num">${esc(w.value)}</td>
      <td class="${w.ok ? 'o2m-ok' : 'o2m-bad'}">${esc(w.message)}</td></tr>`).join('') || `<tr><td colspan="5" class="o2m-muted">${esc(L('ED.LOG_EMPTY'))}</td></tr>`;
  }
  async function writePoint(slug) {
    const p = state.points.find(x => x.slug === slug);
    const el = root.querySelector(`[data-slug="${CSS.escape(slug)}"]`);
    const val = el.value;
    const shown = el.tagName === 'SELECT' ? el.options[el.selectedIndex].text : val + (p.unit ? ' ' + p.unit : '');
    if (!confirm(L('ED.CONFIRM', {name: p.name, from: fmtVal(p), to: shown}))) return;
    await cmd('write', {slug, value: val}, $('ed-msg'));
    await loadState();
    renderEdit();
  }

  // ------------------------------------------------------------ Konfiguration
  const cfgFields = ['host', 'port', 'username', 'poll_interval', 'mqtt_topic', 'publish_mode', 'full_refresh_min',
                     'write_min_interval_sec', 'write_max_per_day', 'schema_buffer'];
  const cfgToggles = ['mqtt_enabled', 'include_technical', 'publish_raw_points', 'writes_enabled', 'notify_alarms', 'notify_connection'];
  const VALIDATED = ['#host', '#port', '#pin', '#mqtt_topic'];
  async function loadConfig() {
    const [c, s] = await Promise.all([api('config'), api('state').catch(() => null)]);
    cfgFields.forEach(k => { if ($(k)) $(k).value = c[k] ?? ''; });
    cfgToggles.forEach(k => { $(k).checked = !!c[k]; });
    $('pw-hint').textContent = c.has_password ? L('CFG.PW_STORED') : L('CFG.PW_NONE');
    $('pin-hint').textContent = c.has_pin ? L('CFG.PIN_STORED') : L('CFG.PIN_NONE');
    const st = s?.status || {};
    $('cfg-conn').innerHTML = !c.host ? `<span class="badge b-grey">${esc(L('CFG.NOT_SET_UP'))}</span>`
      : st.connected ? `<span class="badge b-green">● ${esc(L('COMMON.CONNECTED'))}</span> <span class="o2m-muted o2m-msg">${esc(s.identity?.model || '')}</span>`
      : `<span class="badge b-red">● ${esc(L('COMMON.NO_CONNECTION'))}</span>${st.error ? ' <span class="o2m-muted o2m-msg">' + esc(st.error) + '</span>' : ''}`;
    const caps = s?.capabilities;
    const src = caps?.buffer_source;
    $('buf-detect').innerHTML = caps ? L('CFG.BUF_NOW', {state: `<b>${esc(caps.buffer ? L('CFG.BUF_SHOWN') : L('CFG.BUF_NONE'))}</b>`})
      + (src && LT['CFG.BUF_SRC_' + src.toUpperCase()] ? ' (' + esc(L('CFG.BUF_SRC_' + src.toUpperCase())) + ')' : '') + '.' : '';
  }
  function enableValidation() {
    // LoxBerry-Formularvalidierung (validate.js, im LoxBerry-Kopf geladen)
    if (typeof window.validate_enable !== 'function') return;
    VALIDATED.forEach(id => window.validate_enable(id));
    window.validate_chk_object(VALIDATED);
  }
  async function saveConfig() {
    if (typeof window.validate_all === 'function' && !window.validate_all()) {
      setMsg($('cfg-msg'), 'bad', L('CFG.INVALID'));
      return;
    }
    const body = {};
    cfgFields.forEach(k => { body[k] = $(k).value; });
    cfgToggles.forEach(k => { body[k] = $(k).checked; });
    body.password = $('password').value;
    body.pin = $('pin').value;
    const wasOn = !!(await api('config')).writes_enabled;
    if (body.writes_enabled && !wasOn && !confirm(L('CFG.CONFIRM_WRITES'))) return;
    const r = await post('save_config', body);
    setMsg($('cfg-msg'), r.ok ? 'ok' : 'bad', r.ok ? L('CFG.SAVED') : (r.error || L('COMMON.ERROR')));
    $('password').value = ''; $('pin').value = '';
    setTimeout(loadConfig, 2500);
  }

  // ------------------------------------------------------------ Loxone
  let lx = null, lxInfo = null, gw = null, lxSel = null;
  const BASIS = [/^plant\/hp\/(status_text|outdoor|flow|return|heat_output|el_power|cop|buffer_top|program_text)$/,
                 /^plant\/dhw\/(temp|target_active|mode)$/,
                 /^plant\/hc\d\/(room_target|room_temp|mode|preset|flow_actual|flow_target|heating|cooling)$/,
                 /^(connected|alarm\/count|alarm\/active|cmd_result)$/];
  const isV2 = () => !!(gw && gw.version === 2);
  async function loadLoxone() {
    [lx, lxInfo, gw] = await Promise.all([api('api&ep=topics').catch(() => null), api('loxinfo').catch(() => ({})), api('gateway').catch(() => null)]);
    if (lx && !lx.error) {
      lx.topics = lx.topics.concat([
        {topic: 'connected', area: 'Plugin', name: L('LX.P_CONNECTED'), value: 1},
        {topic: 'alarm/count', area: 'Plugin', name: L('LX.P_ALARM_COUNT'), value: ''},
        {topic: 'alarm/active', area: 'Plugin', name: L('LX.P_ALARM_ACTIVE'), value: ''},
        {topic: 'cmd_result', area: 'Plugin', name: L('LX.P_CMD_RESULT'), value: ''}]);
    }
    if (isV2()) {
      const subs = new Set(gw.subscribed || []);
      const base = (lx && lx.base) || 'ochsner';
      lxSel = new Set((lx?.topics || []).map(t => t.topic).filter(t => (subs.size ? subs.has(base + '/' + t) : BASIS.some(re => re.test(t)))));
      const ms = gw.miniservers || [];
      $('lx-ms-wrap').hidden = ms.length < 2;
      $('lx-ms').innerHTML = `<option value="">${esc(L('LX.MS_DEFAULT'))}</option>` +
        ms.map(m => `<option value="${esc(m.no)}">${esc(m.no + ' – ' + m.name)}</option>`).join('');
      $('lx-ms').value = (gw.toms && gw.toms.length === 1) ? String(gw.toms[0]) : '';
    }
    renderGateway();
    renderLoxone();
  }
  function renderGateway() {
    const base = (lx && lx.base) || 'ochsner';
    const tiles = [[L('LX.T_TOPICS'), lx && !lx.error ? lx.topics.length : '–'],
                   [L('LX.T_CIRCUITS'), (lx?.circuits || []).map(c => `${esc(L('LX.HC_SHORT'))}${c.index} ${esc(c.name)}`).join(', ') || '–'],
                   [L('LX.T_GATEWAY'), gw ? L('LX.GW_VERSION', {v: gw.version}) + (gw.version === 2 ? ' <small>(V2)</small>' : ` <small>(${esc(L('LX.GW_CLASSIC'))})</small>`) : '–'],
                   [L('LX.T_UDP'), lxInfo?.udp_port || 11884]];
    $('lx-tiles').innerHTML = tiles.map(tile).join('');
    let h = '';
    if (!gw) h = callout('lb-callout-warning', L('LX.GW_MISSING'), L('LX.GW_MISSING_TEXT'));
    else if (isV2()) {
      const n = (gw.subscribed || []).length;
      h = callout(n ? 'o2m-state-ok' : '', n ? L('LX.GW2_ACTIVE', {n}) : L('LX.GW2_EMPTY'), L('LX.GW2_TEXT'));
    } else {
      h = callout('o2m-state-ok', L('LX.GW1_ACTIVE', {sub: `<code>${esc(base)}/#</code>`}), L('LX.GW1_TEXT'));
    }
    $('lx-gw').innerHTML = h;
    $('lx-selbar').hidden = !isV2();
    $('lx-selhead').hidden = !isV2();
  }
  function renderLoxone() {
    if (!lx || lx.error) { $('lx-body').innerHTML = `<tr><td colspan="5" class="o2m-bad">${esc(L('COMMON.DAEMON_DOWN'))}</td></tr>`; return; }
    const base = lx.base || 'ochsner';
    const vi = (t) => (base + '/' + t).replace(/[/\s%]/g, '_');
    const v2 = isV2();
    $('lx-addr').textContent = `/dev/udp/${lxInfo.loxberry || '<loxberry>'}/${lxInfo.udp_port || 11884}`;
    $('lx-res').textContent = base + '/cmd_result';
    const ex = {'hp/program': ['auto', 'off'], 'hc<n>/preset': ['comfort', 'eco', 'off'], 'dhw/mode': ['comfort', 'eco', 'off', 'boost'],
                'hc<n>/mode': ['heat', 'off'], 'dhw/boost': ['1'], 'poll': ['1']};
    const n1 = (lx.circuits[0] || {index: 1}).index;
    $('lx-cmds').innerHTML = lx.commands.map(c => {
      const t = c.topic.replace('<n>', n1);
      const vals = ex[c.topic] ? ex[c.topic].map(v => `publish ${base}/cmd/${t} ${v}`) : [`publish ${base}/cmd/${t} <v>`];
      return `<tr><td>${esc(c.text)}<br><code class="o2m-muted sm">${esc(base + '/cmd/' + c.topic)}</code></td><td class="sm">${esc(c.values)}</td>
        <td>${vals.map(v => `<div style="margin:2px 0"><code>${esc(v)}</code>${copyBtn(v)}</div>`).join('')}</td></tr>`;
    }).join('');
    const f = ($('lx-filter').value || '').toLowerCase();
    const rows = lx.topics.filter(t => !f || (t.area + ' ' + t.name + ' ' + t.topic).toLowerCase().includes(f));
    let html = '', grp = null;
    const cols = v2 ? 5 : 4;
    for (const t of rows) {
      if (t.area !== grp) { grp = t.area; html += `<tr class="grp"><td colspan="${cols}">${esc(grp)}</td></tr>`; }
      const sel = v2 ? `<td><input type="checkbox" data-lx="${esc(t.topic)}" ${lxSel.has(t.topic) ? 'checked' : ''} aria-label="${esc(L('LX.COL_MS_TITLE'))}"></td>` : '';
      const isText = /_text$|^alarm\/active$|^cmd_result$|\/mode$|\/preset$|\/name$/.test(t.topic);
      html += `<tr>${sel}<td class="o2m-muted sm">${esc(t.topic.split('/').slice(-1)[0])}</td><td>${esc(t.name)}${isText ? ` <span class="badge b-grey">${esc(L('LX.B_TEXT'))}</span>` : ''}</td>
        <td class="num">${esc(num(t.value))}${t.unit ? ' ' + esc(t.unit) : ''}</td><td><code>${esc(vi(t.topic))}</code>${copyBtn(vi(t.topic))}</td></tr>`;
    }
    $('lx-body').innerHTML = html || `<tr><td colspan="${cols}" class="o2m-muted">${esc(L('COMMON.NO_DATA'))}</td></tr>`;
    lxMeta(rows.length);
  }
  function lxMeta(nRows) {
    $('lx-meta').className = 'o2m-msg o2m-muted';
    $('lx-meta').textContent = L('LX.META', {n: nRows ?? lx.topics.length, total: lx.topics.length}) +
      (isV2() ? ' · ' + L('LX.META_SEL', {n: lxSel.size}) : '');
  }
  root.addEventListener('change', (e) => {
    const cb = e.target.closest('input[data-lx]');
    if (!cb || !lxSel) return;
    if (cb.checked) lxSel.add(cb.dataset.lx); else lxSel.delete(cb.dataset.lx);
    lxMeta();
  });
  function lxSelect(mode) {
    if (!lxSel) return;
    const all = lx.topics.map(t => t.topic);
    lxSel = new Set(mode === 'all' ? all : mode === 'none' ? [] : all.filter(t => BASIS.some(re => re.test(t))));
    renderLoxone();
  }
  async function lxApply() {
    const base = lx.base || 'ochsner';
    const topics = [...lxSel].map(t => base + '/' + t);
    if (!confirm(L('LX.CONFIRM_APPLY', {n: topics.length, base}))) return;
    const ms = $('lx-ms').value;
    const r = await post('gateway_subscribe', {topics, toms: ms ? [Number(ms)] : []});
    setMsg($('lx-meta'), r.ok ? 'ok' : 'bad', r.ok ? L('LX.APPLIED', {n: r.count, added: r.added, removed: r.removed}) : (r.error || L('COMMON.ERROR')));
    if (r.ok) { gw = await api('gateway').catch(() => gw); renderGateway(); }
  }

  // ------------------------------------------------------------ Log
  let logTimer = null;
  async function loadLog() {
    const r = await api('log');
    const el = $('log-body');
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
    el.innerHTML = esc(r.log || L('LOG.EMPTY')).split('\n').map(l => {
      const cls = /&lt;(ERROR|CRITICAL|ALERT|EMERGE|FAIL)&gt;/.test(l) ? 'e' : /&lt;WARNING&gt;/.test(l) ? 'w'
        : /SCHREIBEN|WRITE /.test(l) ? 's' : /&lt;OK&gt;/.test(l) ? 'o' : /^\d\d:\d\d:\d\d\.\d+ (?!&lt;)/.test(l) ? 'd' : '';
      return cls ? `<span class="${cls}">${l}</span>` : l;
    }).join('\n');
    if (atEnd || !logTimer) el.scrollTop = el.scrollHeight;
    $('log-file').textContent = r.file ? L('LOG.FILE', {file: r.file}) : '';
    const v = $('log-viewer');
    if (r.viewer) { v.href = r.viewer; v.hidden = false; } else v.hidden = true;
  }
  function initLogLevel() {
    // Gleiche Funktion wie LBWeb::loglevel_select_html (dort jQuery-Mobile-Markup, unter PHP 8 nicht aufrufbar):
    // die Stufe steht in der Plugin-Datenbank, LBLog im Dienst übernimmt sie ohne Neustart.
    const sel = $('o2m-loglevel');
    if (!sel) return;
    if (!sel.dataset.md5) { sel.disabled = true; setMsg($('log-level-msg'), 'muted', L('LOG.LEVEL_NA')); return; }
    sel.value = sel.dataset.level || '3';
    sel.addEventListener('change', async () => {
      const body = new URLSearchParams({action: 'plugin-loglevel', pluginmd5: sel.dataset.md5, value: sel.value});
      try {
        const r = await fetch('/admin/system/ajax/ajax-config-handler.cgi', {method: 'POST', credentials: 'same-origin', body});
        setMsg($('log-level-msg'), r.ok ? 'ok' : 'bad', r.ok ? L('LOG.LEVEL_SAVED') : L('COMMON.ERROR') + ' ' + r.status);
      } catch (e) { setMsg($('log-level-msg'), 'bad', L('COMMON.ERROR')); }
    });
  }

  async function refresh() {
    if (form === 'overview') await renderOverview();
    else if (form === 'values') { await loadState(); renderValues(); }
    else if (form === 'edit') { await loadState(); renderEdit(); }
  }

  // ------------------------------------------------------------ Start
  if (form === 'settings') {
    loadConfig();
    enableValidation();
    $('cfg-form').addEventListener('submit', (e) => { e.preventDefault(); saveConfig(); });
  } else if (form === 'loxone') {
    loadLoxone();
    $('lx-filter').addEventListener('input', renderLoxone);
  } else if (form === 'log') {
    initLogLevel();
    loadLog();
    $('log-auto').addEventListener('change', () => {
      if (logTimer) { clearInterval(logTimer); logTimer = null; }
      if ($('log-auto').checked) logTimer = setInterval(loadLog, 5000);
    });
  } else {
    refresh();
    if (form === 'overview') loadNotifications();
    if (form === 'values') { $('val-filter').addEventListener('input', renderValues); $('val-alarms').addEventListener('change', renderValues); }
    if (form === 'edit') $('ed-filter').addEventListener('input', renderEdit);
    if (form !== 'edit') setInterval(refresh, 15000);
  }
  return {L, refresh};
})();
