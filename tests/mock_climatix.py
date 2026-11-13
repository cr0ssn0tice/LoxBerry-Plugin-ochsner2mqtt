#!/usr/bin/env python3
"""Simulation eines Climatix-Reglers einer Ochsner Air Hawk (nur für Tests, keine echten Gerätedaten).

- Basic-Auth + PIN, FN=Read (mehrere OA, states=5 für fehlende Punkte), FN=Write
- Katalogpunkte ausgewählter Module, Anlagenrollen wie die Ochsner-App sie liest
  (3 Heizkreise, Puffer, Warmwasser), Zeitprogramme (Tagesobjekte 8717)
- einfache Regler-Reaktionen: Komfort/Eco → Raumsoll/Badge, WW-Modus → WW-Soll,
  Wärmepumpe Aus → Status „Manuell abgeschaltet“
- nach --alarm-after Leseanfragen wird „Niederdruck Störung“ aktiv
"""

import argparse
import base64
import json
import random
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
from ots.catalog import (DESCRIPTOR_MEMBER_ID, PLANT_MODEL_OA, PLANT_SERIAL_OA,  # noqa: E402
                         PLANT_SW_VERSION_OA, decode_oa, load_catalog)
from ots.values import is_alarm_point  # noqa: E402
from ots.vendor import plant as P  # noqa: E402
from ots.vendor import schedule as S  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=18080)
ap.add_argument("--user", default="testuser")
ap.add_argument("--password", default="testpass")
ap.add_argument("--pin", default="1234")
ap.add_argument("--alarm-after", type=int, default=6)
ap.add_argument("--profile", default="518", choices=["518", "208", "208buf"],
                help="518: 3 Heizkreise + Puffer; 208: 1 Heizkreis + WW ohne Puffer-Konfiguration; "
                     "208buf: wie 208, Puffer nur über den Fühler erkennbar")
ap.add_argument("--state", default="heat", choices=["heat", "dhw", "defrost", "standby"])
args = ap.parse_args()
SMALL = args.profile.startswith("208")

cat = load_catalog()
random.seed(42)
present_modules = {"heat_pump_and_heat_generation", "dhw_and_timed_programs", "heating_circuit_1",
                   "heating_circuit_2", "heating_circuit_3",
                   "shared_io_measurements_and_statistics", "plant_identity_and_clock",
                   "aggregate_heat_cool_demand", "system_service_and_site", "energy_management",
                   "communication_and_controller_firmware", "global_root_and_protocol_meta", "reference_only",
                   "buffer_store_and_external_heat_buffer"}
V = {}        # kanonische OA -> Wert
DESC = {}     # (type, tag, point) -> Deskriptor
WRITABLE = set()


def key3(oa):
    o = decode_oa(oa)
    return (o.object_type, o.instance_tag, o.point_index)


for p in cat.points:
    if p.module not in present_modules:
        continue
    if is_alarm_point(p):
        V[p.id] = 0
        DESC[key3(p.id)] = "AlmOf*AlmOn" if p.platform == "sensor" else "Ok*ErOn"
    elif p.platform == "select" or p.options or p.value_map or p.enum_labels:
        V[p.id] = 0
    elif p.platform == "number":
        lo, hi = p.min if p.min is not None else 0, p.max if p.max is not None else 100
        V[p.id] = round(lo + (hi - lo) * 0.4, 1)
    elif p.platform == "switch":
        V[p.id] = 0
    elif p.platform == "text":
        V[p.id] = "Text"
    else:
        V[p.id] = round(random.uniform(5, 55), 1)
    if p.write_id:
        WRITABLE.add(p.write_id)

# ---------------------------------------------------------------- Anlagenrollen
caps_all = {"circuits": [{"index": 1}, {"index": 2}, {"index": 3}], "dhw": True, "buffer": True}
R = P.role_ids(caps_all)


def setr(role, v):
    V[P.canonical_id(R[role])] = v


for role, v in {
    "avail.bms": 0, "avail.dhw": 256, "avail.buffer": 1, "avail.buffer_aux": 1024 | 4, "avail.aux": 16 | 2048,
    "avail.pool": 0, "avail.silent": 1, "avail.emergency": 1, "avail.ext_buffer": 0,
    "hp.outdoor": 12.2, "hp.outdoor_avg": 10.8, "hp.flow": 29.6, "hp.return": 25.1, "hp.flow_rate": 1.3,
    "hp.buffer_top": 26.3, "hp.status": 1, "hp.system_status": 1, "hp.program": 0, "hp.aux_program": 0,
    "hp.aux_status": 0, "hp.aux_flow": 29.4, "hp.silent_program": 0, "hp.heat_output": 6.8, "hp.el_power": 0.7,
    "hp.pressure": 1.75, "hp.cycles_today": 4, "hp.cycles_total": 5321, "hp.defrosts_today": 0,
    "hp.defrosts_total": 812, "hp.hours_total": 9876, "hp.energy_heat_total": 61234,
    "hp.energy_heat_year": 8123, "hp.energy_el_year": 2143, "hp.energy_heat_prev_year": 12034,
    "hp.energy_el_prev_year": 2741, "hp.jaz_year": 3.79, "hp.jaz_prev_year": 4.39, "hp.sum_fault": 1,
    "hp.dhw_valve": 0, "hp.capability": 1, "hp.emergency_status": 0,
    "dhw.temp": 48.5, "dhw.target": 50, "dhw.status": 0, "dhw.program": 0, "dhw.comfort_eco": 2, "dhw.boost": 0,
    "dhw.offset": 0, "dhw.setpoint_comfort": 50, "dhw.setpoint_eco": 45, "dhw.setpoint_reduced": 40,
    "dhw.setpoint_boost": 55, "dhw.emergency_status": 0,
}.items():
    setr(role, v)

if SMALL:  # Werte wie auf dem Screenshot einer echten Anlage (AirHawk 208, ein Fußbodenheizkreis, WW, kein Puffer konfiguriert)
    for role, v in {"avail.buffer": 0, "avail.buffer_aux": 0, "avail.ext_buffer": 0, "avail.silent": 0, "hp.outdoor": 2.8,
                    "hp.outdoor_avg": 4.2, "hp.flow": 30.5, "hp.return": 28.7, "hp.flow_rate": 0.85,
                    "hp.heat_output": 1.8, "hp.el_power": 0.52, "hp.pressure": 2.12, "hp.cycles_today": 7,
                    "dhw.temp": 45.0, "dhw.target": 43, "dhw.setpoint_comfort": 43, "dhw.setpoint_eco": 40,
                    "hp.aux_status": 0}.items():
        setr(role, v)
    if args.profile == "208":
        V.pop(P.canonical_id(R["hp.buffer_top"]), None)
    else:
        setr("hp.buffer_top", 33.4)
STATE = {"heat": (1, 0), "dhw": (3, 1), "defrost": (4, 0), "standby": (9, 0)}[args.state]
setr("hp.status", STATE[0])
setr("hp.dhw_valve", STATE[1])

HC = {
    1: {"name": "Fußboden", "avail": 1 | 2 | 32 | 64, "flow_actual": 25.9, "flow_target": 26.8, "room_temp": 21.3,
        "humidity": 48, "dew_point": 10.1},
    2: {"name": "Radiatoren", "avail": 1 | 2, "flow_actual": 25.8, "flow_target": 26.6},
    3: {"name": "Wintergarten", "avail": 1 | 2, "flow_actual": 19.5, "flow_target": 19.6},
}
if SMALL:
    HC = {1: {"name": "Fussbodenheizung", "avail": 1 | 2, "flow_actual": 27.3, "flow_target": 32.5}}
    for _n in (2, 3):  # Heizkreise 2/3 nicht vorhanden
        V[P.canonical_id(P.circuit_role_ids(_n)[P.hc_key(_n, "availability")])] = 0
for n, h in HC.items():
    ids = P.circuit_role_ids(n)
    g = lambda k: P.canonical_id(ids[P.hc_key(n, k)])  # noqa: E731
    vals = {"availability": h["avail"], "name": h["name"], "op_program": 0, "op_program_present": 0,
            "comfort_eco": 0 if n != 3 else 1, "season": 3, "room_offset": 0.0, "target_selector": 0,
            "badge": 9, "status": 2, "heat_limit_status": 0, "cool_limit_status": 0,
            "setpoint_normal_heat": 21.5 if n != 3 else 25.0, "setpoint_reduced_heat": 19.0 if n != 3 else 10.0,
            "setpoint_normal_cool": 24.0, "setpoint_reduced_cool": 26.0, "setpoint_frost_room": 6.0,
            "heat_curve_base_outdoor": 20.0, "heat_curve_base_flow": 22.0, "heat_curve_norm_outdoor": -16.0,
            "heat_curve_norm_flow": 38.0 if n == 1 else 45.0, "heat_curve_max_flow": 40.0 if n == 1 else 55.0,
            "heat_limit": 16.7, "heat_curve_ref_room": 20.0, "cool_curve_base_outdoor": 20.0,
            "cool_curve_base_flow": 18.0, "cool_curve_norm_outdoor": 35.0, "cool_curve_norm_flow": 16.0,
            "cool_limit": 22.0, "cool_curve_ref_room": 24.0, "party_on": 0, "party_hours": 3, "party_temp": 22.0,
            "flow_actual": h["flow_actual"], "flow_target": h["flow_target"], "pump": 1, "mixer": 55,
            "setpoint_manual": 30.0}
    if "room_temp" in h:
        vals.update(room_temp=h["room_temp"], humidity=h["humidity"], dew_point=h["dew_point"])
    for k, v in vals.items():
        if P.hc_key(n, k) in ids:
            V[g(k)] = v
    # Raumsoll aus Komfort/Eco ableiten
    for k in ("room_target_heat", "room_target_current"):
        V[g(k)] = vals["setpoint_normal_heat"] if vals["comfort_eco"] == 0 else vals["setpoint_reduced_heat"]
    V[g("room_target_cool")] = 24.0
    for k in ("op_program", "comfort_eco", "season", "room_offset", "setpoint_normal_heat", "setpoint_reduced_heat",
              "setpoint_normal_cool", "setpoint_reduced_cool", "heat_curve_base_outdoor", "heat_curve_base_flow",
              "heat_curve_norm_outdoor", "heat_curve_norm_flow", "heat_curve_max_flow", "heat_limit", "name"):
        WRITABLE.add(g(k))
    # Zeitprogramm: Mo–Fr 06:00 Normal, 22:00 Eco; Sa/So 07:30 Normal, 23:00 Eco (nur HK1)
    present_id, default_id = S.master_ids(n)
    V[present_id] = 1
    V[default_id] = 0
    for d in range(7):
        times, vals_ = S.day_ids(n, d)
        pts = ([(360, 1), (1320, 0)] if d < 5 else [(450, 1), (1380, 0)]) if n == 1 else []
        for i in range(S.SLOTS):
            V[times[i]] = S.encode_time(pts[i][0]) if i < len(pts) else S.UNUSED
            V[vals_[i]] = pts[i][1] if i < len(pts) else 0
            WRITABLE.update({times[i], vals_[i]})
for role in ("hp.program", "dhw.program", "dhw.comfort_eco", "dhw.boost", "dhw.setpoint_comfort", "dhw.setpoint_eco",
             "dhw.setpoint_boost", "dhw.offset", "hp.silent_program"):
    WRITABLE.add(P.canonical_id(R[role]))

# Summenstörung: Zustandsliste wie im Regler (Index = Wert), 1 = störungsfrei
DESC[key3(P.canonical_id(R["hp.sum_fault"]))] = "Null*Ok*LockOf*LockOn*ErOf*ErOn*AlmOf*AlmOn*InfoOf*InfoOn"
V[PLANT_MODEL_OA] = "AIRHAWK208C11A" if SMALL else "AIRHAWK518C11A"
V[PLANT_SERIAL_OA] = "TEST-0000"
V[PLANT_SW_VERSION_OA] = "v3.3.20"
ALARM_ID = cat.by_slug["niederdruck_stoerung"].id
lock = threading.Lock()
reads = {"n": 0}
writes = []


def react(oid):
    """Regler rechnet abhängige Werte neu (stark vereinfacht)."""
    for n in HC:
        ids = P.circuit_role_ids(n)
        g = lambda k: P.canonical_id(ids[P.hc_key(n, k)])  # noqa: E731
        if oid in {g(k) for k in ("op_program", "comfort_eco", "room_offset", "setpoint_normal_heat", "setpoint_reduced_heat")}:
            off = V[g("op_program")] == 1
            base = V[g("setpoint_normal_heat")] if V[g("comfort_eco")] == 0 else V[g("setpoint_reduced_heat")]
            V[g("room_target_heat")] = V[g("room_target_current")] = round(base + float(V[g("room_offset")]), 2)
            V[g("badge")] = 0 if off else (9 if V[g("comfort_eco")] == 0 else 11)
            V[g("status")] = 0 if off else (2 if V[g("comfort_eco")] == 0 else 1)
            V[g("op_program_present")] = V[g("op_program")]
    dp, dce, db = (P.canonical_id(R[k]) for k in ("dhw.program", "dhw.comfort_eco", "dhw.boost"))
    dsp = {P.canonical_id(R[k]) for k in ("dhw.setpoint_comfort", "dhw.setpoint_eco", "dhw.setpoint_boost", "dhw.offset")}
    if oid in (dp, dce, db) or oid in dsp:
        sp = "dhw.setpoint_boost" if V[db] == 1 else ("dhw.setpoint_eco" if V[dce] == 1 else "dhw.setpoint_comfort")
        V[P.canonical_id(R["dhw.target"])] = V[P.canonical_id(R[sp])] + V[P.canonical_id(R["dhw.offset"])]
    if oid == P.canonical_id(R["hp.program"]):
        V[P.canonical_id(R["hp.status"])] = 17 if V[oid] == 3 else 1


for _n in HC:  # Badge/Status/Raumsoll passend zu Komfort/Eco initialisieren
    react(P.canonical_id(P.circuit_role_ids(_n)[P.hc_key(_n, "comfort_eco")]))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode("latin-1", "replace")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path == "/_mock/writes":
            return self._send(200, writes)
        if u.path == "/_mock/set":
            q = urllib.parse.parse_qs(u.query)
            with lock:
                for k, v in q.items():
                    oid = P.canonical_id(R[k]) if k in R else P.canonical_id(k)
                    try:
                        V[oid] = float(v[0]) if "." in v[0] else int(v[0])
                    except ValueError:
                        V[oid] = v[0]
            return self._send(200, {"ok": True})
        if u.path == "/_mock/value":
            q = urllib.parse.parse_qs(u.query)
            return self._send(200, {"value": V.get(P.canonical_id(q["oa"][0]))})
        if u.path.lower() != "/jsongen.html":
            return self._send(404, {"Error": 404})
        want = "Basic " + base64.b64encode(f"{args.user}:{args.password}".encode()).decode()
        if self.headers.get("Authorization") != want:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="climatix"')
            self.end_headers()
            return
        q = urllib.parse.parse_qs(u.query, keep_blank_values=True)
        if q.get("PIN", [""])[0] != args.pin:
            return self._send(200, {"Error": 2})
        fn = q.get("FN", [""])[0]
        oas = q.get("OA", [])
        if fn == "Read":
            with lock:
                reads["n"] += 1
                if reads["n"] >= args.alarm_after:
                    V[ALARM_ID] = 1
            vals, states = {}, {}
            for oa in oas:
                o = decode_oa(oa)
                if o.member_id == DESCRIPTOR_MEMBER_ID:
                    d = DESC.get((o.object_type, o.instance_tag, o.point_index))
                    if d:
                        vals[oa] = [d, d]
                    else:
                        states[oa] = 5
                    continue
                k = P.canonical_id(oa)
                if k in V:
                    v = V[k]
                    if isinstance(v, str):
                        v = v.encode("utf-8").decode("latin-1")  # Regler liefert UTF-8 als Latin-1 (Mojibake)
                    vals[oa] = [v, v]
                else:
                    states[oa] = 5
            return self._send(200, {"values": vals, "states": states})
        if fn == "Write":
            if len(oas) != 1 or ";" not in oas[0]:
                return self._send(200, {"Error": 3})
            wid, val = oas[0].split(";", 1)
            wid = P.canonical_id(wid)
            if wid not in WRITABLE:
                return self._send(200, {"Error": 4})
            p = cat.by_id.get(wid)
            try:
                num = float(val)
            except ValueError:
                num = None
            if p and num is not None and ((p.min is not None and num < p.min) or (p.max is not None and num > p.max)):
                return self._send(200, {"Error": 5})
            with lock:
                target = wid
                if p and p.write_id and p.write_id != p.id:
                    target = p.id
                V[target] = (int(num) if num is not None and num.is_integer() else num) if num is not None else val
                writes.append({"oa": wid, "value": val})
                react(target)
            return self._send(200, {"values": {wid: [val, val]}})
        return self._send(200, {"Error": 1})


srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
print(f"mock climatix on :{args.port}, {len(V)} Werte", flush=True)
srv.serve_forever()
