#!/usr/bin/env python3
"""Füllt eine frische Testumgebung mit einem plausiblen Verlauf der letzten 24 h (nur für Doku-Screenshots).

Simuliert einen Novembertag: Außentemperatur 1–7 °C, taktende Wärmepumpe (Heizbetrieb mit Pausen),
zwei Warmwasserladungen, eine Abtauung je Stunde mit Frost, dazu ein kleiner Störungsverlauf.
Aufruf: seed_history.py <datenordner>
"""
import json
import math
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

random.seed(208)
data = Path(sys.argv[1])
now = time.time()
start = now - 24 * 3600
H = {k: [] for k in ("hp_heat_output", "hp_el_power", "hp_status", "hp_outdoor", "hp_flow", "hp_return",
                     "hp_buffer_top", "dhw_temp", "hp_flow_rate")}


def add(key, ts, v):
    s = None if v is None else (str(int(v)) if float(v).is_integer() else f"{v:.6g}")
    rows = H[key]
    if not rows or rows[-1][1] != s:
        rows.append([round(ts, 1), s])


t = start
dhw = 47.0
buf = 30.0
while t < now - 60:
    hour = datetime.fromtimestamp(t).hour + datetime.fromtimestamp(t).minute / 60
    outdoor = 4 + 3 * math.sin((hour - 9) / 24 * 2 * math.pi) + random.uniform(-0.3, 0.3)
    dhw_charge = 5.0 <= hour < 5.7 or 17.0 <= hour < 17.6
    if dhw_charge:
        status, heat, el, flow, ret, rate = 3, 6.4, 1.9, 52.0, 46.5, 1.05
        dhw = min(dhw + 0.35, 51)
    else:
        demand = max(0.0, (18 - outdoor) / 14)
        on = (t / 60) % 75 < 40 + 25 * demand              # takten: 40–65 min an je 75 min
        if on and outdoor < 3 and (t / 60) % 75 < 4:
            status, heat, el, flow, ret, rate = 4, 0.0, 0.4, 24.0, 23.0, 0.8      # Abtauen
        elif on:
            heat = 3.2 + 3.0 * demand + random.uniform(-0.2, 0.2)
            el = heat / (3.4 + 0.12 * outdoor + random.uniform(-0.1, 0.1))
            flow = 30 + 6 * demand
            status, ret, rate = 1, flow - 4.5, 0.85
        else:
            status, heat, el, flow, ret, rate = 9, 0.0, 0.02, 26.0, 25.0, 0.0
        dhw = max(dhw - 0.03, 42)
    buf += (0.4 if status == 1 else -0.15)
    buf = min(max(buf, 27.0), 38.0)
    add("hp_outdoor", t, round(outdoor, 1))
    add("hp_status", t, status)
    add("hp_heat_output", t, round(heat, 1))
    add("hp_el_power", t, round(el, 2))
    add("hp_flow", t, round(flow, 1))
    add("hp_return", t, round(ret, 1))
    add("hp_buffer_top", t, round(buf, 1))
    add("dhw_temp", t, round(dhw, 1))
    add("hp_flow_rate", t, rate)
    t += 120

(data / "history.json").write_text(json.dumps({f"sensor.o2m_{k}": v for k, v in H.items()}, separators=(",", ":")))

ev = []
for days, slug, name, text in ((6, "ventilatorstoerung", "Ventilatorstörung", "Alarm ein"),
                                (2, "niederdruck_stoerung", "Niederdruck Störung", "Alarm ein")):
    on = datetime.now().astimezone() - timedelta(days=days, hours=3)
    for i, event in enumerate(("kommt", "geht")):
        ts = on + timedelta(minutes=37 * i)
        ev.append({"ts": ts.isoformat(timespec="seconds"), "slug": slug, "name": name, "event": event,
                   "raw": 1 - i, "text": text if i == 0 else "Alarm aus", "token": "AlmOn" if i == 0 else "AlmOff"})
(data / "alarm_history.json").write_text(json.dumps(ev, ensure_ascii=False))
print(f"Verlauf: {sum(len(v) for v in H.values())} Werte, Störungsverlauf: {len(ev)} Einträge")
