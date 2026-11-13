#!/usr/bin/env python3
"""Test der App-API (lokal, wie die Weboberfläche sie nutzt) und der Loxone-MQTT-Befehle.

Voraussetzung: tests/dev_env.sh start (Simulation + Daemon + Broker laufen).
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt

T = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/o2m-dev")
CFG = json.loads((T / "cfg/ochsner2mqtt.json").read_text())
API = f"http://127.0.0.1:{CFG['api_port']}"
TOKEN = (T / "data/api_token").read_text().strip()
BROKER = int(json.loads((T / "sys/general.json").read_text())["Mqtt"]["Brokerport"])
ok = True


def check(cond, label):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok &= bool(cond)


def call(method, path, body=None, token=TOKEN):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-O2M-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def mock_writes():
    return json.loads(urllib.request.urlopen("http://127.0.0.1:18080/_mock/writes").read())


def service(domain, svc, data):
    return call("POST", "/api/service", {"domain": domain, "service": svc, "data": data})


def live():
    return call("GET", "/api/live")[1]


def set_cfg(**kw):
    cfg = json.loads((T / "cfg/ochsner2mqtt.json").read_text())
    cfg.update(kw)
    (T / "cfg/ochsner2mqtt.json").write_text(json.dumps(cfg))
    time.sleep(1.5)


set_cfg(writes_enabled=True, write_max_per_day=100)
code, _ = call("GET", "/api/plants", token="falsch")
check(code == 403, "API ohne gültiges Token abgewiesen")
code, plants = call("GET", "/api/plants")
p = plants["plants"][0]
check(code == 200 and p["title"] == "AirHawk 518", f"Anlage erkannt ({p['title']})")
check([c["name"] for c in p["circuits"]] == ["Fußboden", "Radiatoren", "Wintergarten"], "Drei Heizkreise mit Namen")
check(p["dhw"] and p["capabilities"]["buffer"], "Warmwasser und Puffer erkannt")
check(p["roles"]["hc1.setpoint_normal_heat"].get("writable") and not p["roles"]["hp.pressure"].get("writable"),
      "Nur App-Rollen beschreibbar (Anlagendruck nicht)")
lv = live()
check(lv["states"]["climate.o2m_hc1"]["state"] == "heat", "Heizkreis-Zustand wie HA-Klima-Entity")
check(lv["event"]["values"]["hp.outdoor"] == 12.2, "Live-Werte nach Rollen")

# --- Bedienung
b = len(mock_writes())
code, r = service("climate", "set_preset_mode", {"entity_id": "climate.o2m_hc2", "preset_mode": "eco"})
w = mock_writes()[b:]
check(code == 200 and len(w) == 1 and w[0]["value"] == "1", f"HK2 Eco = 1 Schreibzugriff ({w})")
check(live()["states"]["climate.o2m_hc2"]["attributes"]["preset_mode"] == "eco", "Zustand sofort aktualisiert")
b = len(mock_writes())
service("climate", "set_preset_mode", {"entity_id": "climate.o2m_hc2", "preset_mode": "eco"})
check(len(mock_writes()) == b, "Gleiche Betriebsart nochmal: kein Schreibzugriff")
code, r = service("number", "set_value", {"entity_id": "number.o2m_hc2_setpoint_reduced_heat", "value": 99})
check(code == 409 and "Maximum" in r["error"]["message"], "Sollwert über Maximum abgelehnt")
b = len(mock_writes())
code, r = service("water_heater", "set_operation_mode", {"entity_id": "water_heater.o2m_dhw", "operation_mode": "high_demand"})
w = mock_writes()[b:]
check(code == 200 and len(w) == 1, f"Warmwasser Boost-Betrieb ({w})")
code, r = service("water_heater", "set_operation_mode", {"entity_id": "water_heater.o2m_dhw", "operation_mode": "performance"})
check(code == 200, "Warmwasser zurück auf Komfort")
code, r = service("select", "select_option", {"entity_id": "select.o2m_hp_program", "option": "Abgeschaltet"})
check(code == 200 and live()["event"]["values"]["hp.status"] == 17, "Wärmepumpe aus → Status „Manuell abgeschaltet“")
service("select", "select_option", {"entity_id": "select.o2m_hp_program", "option": "Automatik"})
code, r = service("number", "set_value", {"entity_id": "number.o2m_hp_pressure", "value": 2})
check(code == 409, "Nicht freigegebene Rolle nicht beschreibbar")

# --- Zeitprogramm
code, sch = call("GET", "/api/schedules?force=1")
hk1 = next(c for c in sch["circuits"] if c["index"] == 1)
check(hk1["complete"] and hk1["days"][0][0] == [360, 1], "Zeitprogramm HK1 gelesen (Mo 06:00 Normal)")
b = len(mock_writes())
code, res = call("POST", "/api/schedule/set", {"circuit": 1, "days": {"5": [[420, 1], [1380, 0]]}})
w = mock_writes()[b:]
check(code == 200 and res["writes"] == len(w) == 1, f"Samstag 07:30→07:00: genau 1 Schreibzugriff ({w})")
check(res["days"][5][0] == [420, 1], "Zeitprogramm zurückgelesen")
code, res = call("POST", "/api/schedule/set", {"circuit": 1, "days": {"0": [[600, 1], [500, 0]]}})
check(code == 409, "Ungültiges Zeitprogramm (absteigende Zeiten) abgelehnt")

# --- Verlauf
code, h = call("GET", "/api/history?entity_ids=sensor.o2m_hp_outdoor,sensor.o2m_hp_heat_output")
check(code == 200 and "sensor.o2m_hp_outdoor" in h, "Verlauf abrufbar")

# --- Schreibschutz
set_cfg(writes_enabled=False)
code, r = service("climate", "set_preset_mode", {"entity_id": "climate.o2m_hc2", "preset_mode": "comfort"})
check(code == 409 and "gesperrt" in r["error"]["message"], "Schreiben gesperrt → App-Aktion abgelehnt")
st = live()["status"]
set_cfg(writes_enabled=True, write_max_per_day=st["flash"]["today"])
code, r = service("climate", "set_preset_mode", {"entity_id": "climate.o2m_hc2", "preset_mode": "comfort"})
check(code == 409 and "Tageslimit" in r["error"]["message"], "Tageslimit greift")
set_cfg(write_max_per_day=100)

# --- Loxone über MQTT
msgs = {}
c = (mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, 'CallbackAPIVersion') else mqtt.Client())
c.on_message = lambda cl, ud, m: msgs.__setitem__(m.topic, m.payload.decode())
c.connect("127.0.0.1", BROKER)
c.subscribe("ochsner/#")
c.loop_start()
time.sleep(1.5)
check(msgs.get("ochsner/plant/hc1/name") == "Fußboden" and "ochsner/plant/hp/status_text" in msgs, "Anlagen-Topics für Loxone")


def cmd(topic, value):
    msgs.pop("ochsner/cmd_result", None)
    c.publish(f"ochsner/cmd/{topic}", value)
    for _ in range(60):
        time.sleep(0.25)
        if "ochsner/cmd_result" in msgs:
            return json.loads(msgs["ochsner/cmd_result"])
    return {}


r = cmd("hc3/preset", "comfort")
check(r.get("ok"), f"MQTT hc3/preset comfort ({r.get('message')})")
time.sleep(1.5)
check(msgs.get("ochsner/plant/hc3/preset") == "comfort", "Ergebnis als Topic zurück")
r = cmd("hc3/preset", "comfort")
check(r.get("ok") and "Unverändert" in r.get("message", ""), "Wiederholung ohne Schreibzugriff")
r = cmd("hc3/setpoint_reduced_heat", "11")
r2 = cmd("hc3/setpoint_reduced_heat", "12")
check(r.get("ok") and not r2.get("ok") and "Ratenlimit" in r2.get("message", ""), "Ratenlimit für Automationen (MQTT)")
r = cmd("dhw/mode", "quatsch")
check(not r.get("ok"), "Ungültiger Befehl abgelehnt")
c.loop_stop()
print("\nERGEBNIS:", "ALLES OK" if ok else "FEHLER")
sys.exit(0 if ok else 1)
