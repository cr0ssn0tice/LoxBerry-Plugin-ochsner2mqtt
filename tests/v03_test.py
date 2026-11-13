#!/usr/bin/env python3
"""Tests für v0.3: Diagnose-Export, Puffer im Schema, MQTT Gateway V2, Abo-Datei V1, Plugin-Seiten.

Voraussetzung: tests/dev_env.sh start mit MOCK_ARGS="--profile 208buf".
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

T = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/o2m-dev")
CFG = json.loads((T / "cfg/ochsner2mqtt.json").read_text())
API = f"http://127.0.0.1:{CFG['api_port']}"
WEB = "http://127.0.0.1:18090"
TOKEN = (T / "data/api_token").read_text().strip()
ok = True


def check(cond, label):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok &= bool(cond)


def get(path):
    req = urllib.request.Request(API + path, headers={"X-O2M-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def web(action, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{WEB}/ajax.php?action={action}", data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json", "X-O2M": "1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read()
        return (r.headers, b) if raw else json.loads(b)


def set_cfg(**kw):
    cfg = json.loads((T / "cfg/ochsner2mqtt.json").read_text())
    cfg.update(kw)
    (T / "cfg/ochsner2mqtt.json").write_text(json.dumps(cfg))
    time.sleep(2.5)


# --- Puffer: im Regler nicht konfiguriert, aber Fühler liefert Werte → automatisch sichtbar
caps = get("/api/plants")["plants"][0]["capabilities"]
check(caps.get("buffer") and caps.get("buffer_temp"), "Puffer über plausiblen Fühler erkannt (auto)")
set_cfg(schema_buffer="hide")
check(not get("/api/plants")["plants"][0]["capabilities"].get("buffer"), "Puffer ausblendbar")
set_cfg(schema_buffer="show")
check(get("/api/plants")["plants"][0]["capabilities"].get("buffer"), "Puffer einblendbar")
set_cfg(schema_buffer="auto")
time.sleep(10)  # nächster Poll schreibt state.json
st = web("state")
check(st.get("capabilities", {}).get("buffer_source") == "sensor", "Quelle der Puffer-Erkennung im Status")

# --- Diagnose-Export ohne Geheimnisse
hdr, body = web("diag", raw=True)
txt = body.decode()
d = json.loads(txt)
check("attachment" in hdr.get("Content-Disposition", ""), "Diagnose als Datei-Download")
secrets = [CFG["password"], CFG["pin"], CFG["username"]]
check(all(json.dumps(s) not in txt for s in secrets) and "TEST-0000" not in txt and "pin" not in d["config"]
      and "password" not in d["config"] and "username" not in d["config"], "Diagnose ohne Passwort, PIN, Benutzer, Seriennummer")
check(d["config"]["host"].endswith(".x.x") and d["config"]["password_set"], "IP gekürzt, Zugangsdaten nur als vorhanden markiert")
check(d.get("capabilities", {}).get("buffer_source") == "sensor" and "role_values" in d and d.get("buffer_sensor") == 33.4,
      "Diagnose enthält Fähigkeiten, Rollenwerte und Pufferfühler")

# --- Abo-Datei für Gateway V1 folgt dem Basis-Topic
sub = (T / "cfg/mqtt_subscriptions.cfg").read_text().strip()
check(sub == "ochsner/#", "mqtt_subscriptions.cfg = <basis>/#")

# --- MQTT Gateway V2: Abos eintragen, fremde bleiben, Sicherung angelegt
gw = web("gateway")
check(gw["version"] == 2 and gw["subscribed"] == [], "Gateway V2 erkannt, noch keine Topics")
r = web("gateway_subscribe", {"topics": ["ochsner/plant/hp/outdoor", "ochsner/plant/hc1/room_target", "ochsner/connected"]})
check(r.get("ok") and r["added"] == 3 and r["removed"] == 0, "3 Topics eingetragen")
subs = json.loads((T / "lbhome/config/system/subscriptions.json").read_text())["Subscriptions"]
ids = [s["Id"] for s in subs]
check("shelly/bulb/state" in ids and len(ids) == 4, "Fremdes Abo unverändert erhalten")
check(all(set(s) >= {"Id", "Toms", "Noncached", "resetaftersend", "Jsonexpand", "Json"} for s in subs), "Einträge im Format des Gateways")
r = web("gateway_subscribe", {"topics": ["ochsner/plant/hp/outdoor"]})
ids = [s["Id"] for s in json.loads((T / "lbhome/config/system/subscriptions.json").read_text())["Subscriptions"]]
check(r.get("ok") and r["removed"] == 2 and sorted(ids) == ["ochsner/plant/hp/outdoor", "shelly/bulb/state"], "Abgewählte Topics entfernt")
check((T / "data/subscriptions.json.backup").exists(), "Sicherung der Abo-Liste angelegt")
r = web("gateway_subscribe", {"topics": ["fremd/topic"]})
check(not r.get("ok"), "Fremde Topics abgelehnt")
try:
    req = urllib.request.Request(f"{WEB}/ajax.php?action=gateway_subscribe", data=b'{"topics":[]}', method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)
    check(False, "Ohne CSRF-Header abgelehnt")
except urllib.error.HTTPError as e:
    check(e.code == 403, "Ohne CSRF-Header abgelehnt")

print("\nERGEBNIS:", "ALLES OK" if ok else "FEHLER")
sys.exit(0 if ok else 1)
