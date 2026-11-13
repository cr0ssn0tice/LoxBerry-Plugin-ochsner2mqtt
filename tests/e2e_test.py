#!/usr/bin/env python3
"""End-to-End-Test: Daemon gegen Mock-Regler + lokalen Mosquitto."""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parent.parent
T = Path(sys.argv[1])
BROKER_PORT = int(sys.argv[2])
MOCK = "http://127.0.0.1:18080"

msgs = {}
c = (mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, 'CallbackAPIVersion') else mqtt.Client())
c.on_message = lambda cl, ud, m: msgs.__setitem__(m.topic, m.payload.decode())
c.connect("127.0.0.1", BROKER_PORT)
c.subscribe("ochsner/#")
c.loop_start()

ok = True


def check(cond, label):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok &= bool(cond)


def wait_for(fn, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = fn()
        if r:
            return r
        time.sleep(0.3)
    return None


import os
d = subprocess.Popen([os.environ.get("O2M_PY", sys.executable), str(ROOT / "bin/ochsner2mqtt.py"), "--config-dir", str(T / "cfg"),
                      "--data-dir", str(T / "data"), "--log-dir", str(T / "log"),
                      "--general-json", str(T / "sys/general.json")])
try:
    check(wait_for(lambda: msgs.get("ochsner/status") == "online"), "Status online (retained)")
    check(wait_for(lambda: msgs.get("ochsner/info/model") == "AIRHAWK518C11A"), "Anlagentyp veröffentlicht")
    check(wait_for(lambda: "ochsner/heizkreis_sollvorlauftemperatur_hk1" in msgs), "Messwert HK1 veröffentlicht")
    check(wait_for(lambda: msgs.get("ochsner/alarm/niederdruck_stoerung") == "1"), "Alarm Niederdruck aktiv")
    check(wait_for(lambda: msgs.get("ochsner/alarm/count") == "1"), "Alarmzähler = 1")
    txt = wait_for(lambda: msgs.get("ochsner/niederdruck_stoerung/text"))
    check(txt == "Alarm ein", f"Alarmtext im Klartext ({txt})")

    st = wait_for(lambda: (lambda s: s if s.get("points") else None)(json.loads((T / "data/state.json").read_text())))
    num = next(p for p in st["points"] if p["writable"] and p["platform"] == "number" and p["min"] is not None
               and p["max"] is not None and p["step"] and p["max"] - p["min"] >= 4 * p["step"])
    slug = num["slug"]
    cur = float(num["value"])
    target = num["min"] + num["step"] * round(((num["max"] - num["min"]) / 2) / num["step"])
    if abs(target - cur) < 1e-6:
        target = num["min"]
    print(f"     Schreibtest auf {slug} ({num['name']}): {cur} -> {target} [{num['min']}..{num['max']}/{num['step']}]")

    # 1) Wert außerhalb Grenzen
    c.publish(f"ochsner/set/{slug}", str(num["max"] + 100))
    r = wait_for(lambda: msgs.get(f"ochsner/set_result/{slug}"))
    check(r and '"ok": false' in r and "Maximum" in r, "Überschreitung Maximum abgelehnt")
    msgs.pop(f"ochsner/set_result/{slug}", None)

    # 2) Gültiger Wert
    c.publish(f"ochsner/set/{slug}", f"{target:g}")
    r = wait_for(lambda: msgs.get(f"ochsner/set_result/{slug}"))
    check(r and '"ok": true' in r and "Geschrieben" in r, f"Gültiger Schreibzugriff ({r and json.loads(r)['message']})")
    writes = json.loads(urllib.request.urlopen(f"{MOCK}/_mock/writes").read())
    check(len(writes) == 1, f"Genau ein Write am Regler ({len(writes)})")
    check(wait_for(lambda: msgs.get("ochsner/flash/writes_total") == "1"), "Flash-Zähler = 1")
    msgs.pop(f"ochsner/set_result/{slug}", None)

    # 3) Gleicher Wert -> kein Write
    c.publish(f"ochsner/set/{slug}", f"{target:g}")
    r = wait_for(lambda: msgs.get(f"ochsner/set_result/{slug}"))
    check(r and "skipped" in r, "Unveränderter Wert übersprungen")
    msgs.pop(f"ochsner/set_result/{slug}", None)

    # 4) Anderer Wert innerhalb Ratenlimit -> abgelehnt
    c.publish(f"ochsner/set/{slug}", f"{num['min']:g}")
    r = wait_for(lambda: msgs.get(f"ochsner/set_result/{slug}"))
    check(r and "Ratenlimit" in r, "Ratenlimit greift")
    msgs.pop(f"ochsner/set_result/{slug}", None)

    # 5) Retained Set-Befehl wird ignoriert
    c.publish(f"ochsner/set/{slug}", "0", retain=True)
    time.sleep(1.0)
    c.publish(f"ochsner/set/{slug}", "", retain=True)  # retained löschen
    time.sleep(1.5)
    writes = json.loads(urllib.request.urlopen(f"{MOCK}/_mock/writes").read())
    check(len(writes) == 1, "Retained Set nach Reconnect nicht ausgeführt (keine Zusatz-Writes)")

    # 6) Web-Spool: Rescan
    (T / "data/cmd/0001.json").write_text(json.dumps({"id": "t1", "action": "rescan"}))
    res = wait_for(lambda: [r for r in json.loads((T / "data/cmd_results.json").read_text() or "[]")
                            if r.get("cmd_id") == "t1"] if (T / "data/cmd_results.json").exists() else None)
    check(res and res[0]["ok"], "Web-Befehl Rescan angenommen")

    # 7) Web-Spool: Schreiben auf unbekannten Punkt
    (T / "data/cmd/0002.json").write_text(json.dumps({"id": "t2", "action": "write", "slug": "gibt_es_nicht", "value": "1"}))
    res = wait_for(lambda: [r for r in json.loads((T / "data/cmd_results.json").read_text())
                            if r.get("cmd_id") == "t2"])
    check(res and not res[0]["ok"], "Unbekannter Punkt abgelehnt")

    # 8) Konfig-Änderung: Schreiben sperren -> wird live übernommen
    cfg = json.loads((T / "cfg/ochsner2mqtt.json").read_text())
    cfg["writes_enabled"] = "0"
    (T / "cfg/ochsner2mqtt.json").write_text(json.dumps(cfg))
    time.sleep(2)
    (T / "data/cmd/0003.json").write_text(json.dumps({"id": "t3", "action": "write", "slug": slug, "value": f"{num['min']:g}"}))
    res = wait_for(lambda: [r for r in json.loads((T / "data/cmd_results.json").read_text())
                            if r.get("cmd_id") == "t3"])
    check(res and "deaktiviert" in res[0]["message"], "Schreibsperre nach Konfig-Reload aktiv")

    # 9) Falsches Passwort -> klare Fehlermeldung im State
    cfg["password"] = "falsch"
    (T / "cfg/ochsner2mqtt.json").write_text(json.dumps(cfg))
    st = wait_for(lambda: (lambda s: s if s["status"].get("error") else None)(json.loads((T / "data/state.json").read_text())))
    check(st and "Zugangsdaten" in st["status"]["error"], f"Auth-Fehler erkannt ({st and st['status']['error']})")
    check(wait_for(lambda: msgs.get("ochsner/connected") == "0"), "connected=0 bei Fehler")

    logs = sorted((T / "log").glob("*_Daemon.log"))
    check(len(logs) == 1, "Eine Log-Sitzung *_Daemon.log (LoxBerry-Schema)")
    log_text = logs[-1].read_text() if logs else ""
    check("<LOGSTART>" in log_text and "<OK> MQTT verbunden" in log_text and "<ERROR> Abfrage fehlgeschlagen" in log_text,
          "LoxBerry-Logformat mit <OK>/<ERROR>-Tags")
    check("testpass" not in log_text and "1234" not in log_text and "falsch" not in log_text, "Keine Zugangsdaten im Log")
finally:
    d.terminate()
    d.wait(10)
    time.sleep(0.5)
    check(msgs.get("ochsner/status") == "offline", "Status offline nach Stopp")
    logs = sorted((T / "log").glob("*_Daemon.log"))
    check(bool(logs) and "<LOGEND>" in logs[-1].read_text(), "Log-Sitzung mit <LOGEND> abgeschlossen")
    c.loop_stop()

print("\nERGEBNIS:", "ALLES OK" if ok else "FEHLER")
sys.exit(0 if ok else 1)
