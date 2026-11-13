#!/usr/bin/env python3
"""v0.4: Prüfung gegen die Anforderungen des LoxBerry-Entwickler-Wikis.

Teil A (statisch, immer): plugin.cfg, Zeilenenden/Kodierung, keine festen /opt/loxberry-Pfade,
Sprachdateien vollständig und gleich, Skripte, Icons, Healthcheck-Format.
Teil B (nur im simulierten LoxBerry, tests/dev_env.sh mit LBSRC und ALARM_AFTER=4):
LBLog-Sitzung im Logmanager, Benachrichtigungen, Protokollstufe aus der Plugin-Datenbank,
MQTT über das SDK, Mehrsprachigkeit, Gateway-Abos mit Miniserver-Auswahl, Healthcheck,
Deinstallation (Aufräumen) und Migration einer Vorversion (preinstall/postinstall).

Aufruf: python3 tests/v04_test.py [Testverzeichnis]
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/o2m-dev")
LB = T / "lb"
P = "ochsner2mqtt"
WEB = "http://127.0.0.1:18090"
ok = True


def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


def http(path, data=None, headers=None):
    req = urllib.request.Request(WEB + path, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


def as_loxberry(cmd, env=""):
    return subprocess.run(["su", "loxberry", "-s", "/bin/bash", "-c", f"{env} {cmd}"], capture_output=True, text=True, timeout=60)


# ============================================================================ A: statisch
cfg = {}
section = None
for line in (ROOT / "plugin.cfg").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("["):
        section = line.strip("[]")
        continue
    k, _, v = line.partition("=")
    cfg[f"{section}.{k}"] = v
py_version = re.search(r'VERSION = "([^"]+)"', (ROOT / "bin/ochsner2mqtt.py").read_text()).group(1)
check(cfg.get("AUTHOR.NAME") == "cr0ssn0tice" and cfg.get("AUTHOR.EMAIL") == "cr0ssn0tice@proton.me", "plugin.cfg: Autor cr0ssn0tice")
check(re.fullmatch(r"\d+\.\d+\.\d+", cfg.get("PLUGIN.VERSION", "")) and cfg["PLUGIN.VERSION"] == py_version,
      f"Versionsnummer Major.Minor.Patch, gleich im Daemon ({py_version})")
check(cfg.get("PLUGIN.NAME") == cfg.get("PLUGIN.FOLDER") == P, "NAME/FOLDER klein, ohne Leerzeichen")
check(len(cfg.get("PLUGIN.TITLE", "")) <= 25, "TITLE höchstens 25 Zeichen")
check(cfg.get("SYSTEM.INTERFACE") == "2.0" and cfg.get("SYSTEM.CUSTOM_LOGLEVELS") == "true" and cfg.get("SYSTEM.LB_MINIMUM") == "4.0.1",
      "Interface 2.0, eigene Protokollstufen, LB_MINIMUM 4.0.1 (Python-SDK)")

SHIP = [p for p in ROOT.rglob("*") if p.is_file() and "tests" not in p.parts and "__pycache__" not in p.parts
        and p.suffix not in (".png", ".gif", ".jpg", ".zip") and ".git" not in p.parts and "dist" not in p.parts]
bad_eol = [str(p.relative_to(ROOT)) for p in SHIP if b"\r\n" in p.read_bytes()]
bad_bom = [str(p.relative_to(ROOT)) for p in SHIP if p.read_bytes().startswith(b"\xef\xbb\xbf")]
check(not bad_eol and not bad_bom, f"Zeilenende LF, kein BOM ({len(SHIP)} Dateien) {bad_eol + bad_bom}")
hard = [str(p.relative_to(ROOT)) for p in SHIP if p.suffix != ".md" and "/opt/loxberry" in p.read_text(errors="ignore")]
check(not hard, f"Keine festen /opt/loxberry-Pfade im Code {hard}")


def read_ini(path):
    d, sec = {}, "default"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line[0] in "#;/":
            continue
        if line.startswith("["):
            sec = line[1:line.index("]")]
            continue
        k, _, v = line.partition("=")
        d[f"{sec}.{k.strip()}"] = v.strip()
    return d


de, en = read_ini(ROOT / "templates/lang/language_de.ini"), read_ini(ROOT / "templates/lang/language_en.ini")
check(set(de) == set(en), f"language_de/en mit gleichen Schlüsseln ({len(en)}) {sorted(set(de) ^ set(en))[:6]}")
hd, he = read_ini(ROOT / "templates/lang/help_de.ini"), read_ini(ROOT / "templates/lang/help_en.ini")
check(set(hd) == set(he) and all(f"<TMPL_VAR {k}>" in (ROOT / "templates/help/help.html").read_text() for k in he),
      "Hilfe: help_de/en vollständig, alle Texte im Hilfe-Template")
used = set()
tpl = (ROOT / "templates/page.html").read_text() + (ROOT / "templates/app.html").read_text()
used |= set(re.findall(r"<TMPL_VAR ([A-Z]+\.[A-Z0-9_]+)>", tpl))
js = (ROOT / "webfrontend/htmlauth/js/o2m.js").read_text()
used |= set(re.findall(r"""L\('([A-Z]+\.[A-Z0-9_]*[A-Z0-9])'""", js))
used |= {"APP." + k for k in re.findall(r'T\("([A-Z0-9_]+)"', (ROOT / "webfrontend/htmlauth/app/host.js").read_text())}
php = (ROOT / "webfrontend/htmlauth/ajax.php").read_text() + (ROOT / "webfrontend/htmlauth/index.php").read_text()
used |= set(re.findall(r"""(?:T\("|\$L\['|=> ")([A-Z]+\.[A-Z0-9_]+)""", php))
used |= set(re.findall(r'"(NOTIFY\.[A-Z_]+)"', (ROOT / "bin/ochsner2mqtt.py").read_text()))
dynamic = {k for k in en if re.match(r"(CFG\.BUF_SRC_|APP\.ATTR_|APP\.W_)", k)}
missing = sorted(used - set(en))
unused = sorted(set(en) - used - dynamic)
check(not missing, f"Alle verwendeten Sprachschlüssel vorhanden {missing}")
check(not unused, f"Keine unbenutzten Sprachschlüssel {unused}")
attr_keys = set(re.findall(r'="[^"]*<TMPL_VAR ([A-Z]+\.[A-Z0-9_]+)>', tpl))
check(all('"' not in de[k] and '"' not in en[k] for k in attr_keys), f"Texte in HTML-Attributen ohne Anführungszeichen ({len(attr_keys)})")

scripts = ["preinstall.sh", "postinstall.sh", "postupgrade.sh", "preupgrade.sh", "postroot.sh", "uninstall/uninstall.sh",
           "daemon/daemon.sh", "bin/ctl.sh"]
syntax = [s for s in scripts if subprocess.run(["bash", "-n", str(ROOT / s)]).returncode != 0]
check(not syntax and all(os.access(ROOT / s, os.X_OK) for s in scripts + ["bin/healthcheck"]),
      f"Installationsskripte: Syntax ok, ausführbar {syntax}")
check(all((ROOT / s).read_text().startswith("#!") for s in scripts + ["bin/healthcheck"]), "Shebang in allen Skripten")
try:
    from PIL import Image
    sizes = {n: Image.open(ROOT / f"icons/icon_{n}.png").size for n in (64, 128, 256, 512)}
    check(all(s == (n, n) for n, s in sizes.items()) and (ROOT / "icons/icon.svg").read_text().startswith("<svg"),
          "Icons: icon.svg und PNG 64/128/256/512")
except ImportError:
    check((ROOT / "icons/icon.svg").exists(), "Icons: icon.svg vorhanden")
r = subprocess.run([str(ROOT / "bin/healthcheck"), "title"], capture_output=True, text=True, timeout=10)
try:
    title = json.loads(r.stdout)
except ValueError:
    title = {}
check(set(title) == {"desc"} and title["desc"].isascii(), f"Healthcheck title: nur Beschreibung, Englisch ({title})")

if not (LB / "data/system/plugindatabase.json").exists():
    print("\n(kein simulierter LoxBerry – Teil B übersprungen; tests/dev_env.sh mit LBSRC starten)")
    print("\nERGEBNIS:", "ALLES OK" if ok else "FEHLER")
    sys.exit(0 if ok else 1)

# ============================================================================ B: im simulierten LoxBerry
time.sleep(4)
logdb = LB / "log/system_tmpfs/logs_sqlite.dat"
rows = []
if logdb.exists():
    con = sqlite3.connect(logdb)
    rows = con.execute("SELECT LOGKEY, PACKAGE, NAME, FILENAME FROM logs WHERE PACKAGE=? AND NAME='Daemon' ORDER BY LOGKEY DESC", (P,)).fetchall()
    attrs = dict(con.execute("SELECT attrib, value FROM logs_attr WHERE keyref=?", (rows[0][0],)).fetchall()) if rows else {}
    con.close()
check(rows and Path(rows[0][3]).exists(), "LBLog: Sitzung Daemon im Logmanager (logs_sqlite) mit Logdatei")
check(rows and attrs.get("PLUGINTITLE") == "Ochsner OTS", "LBLog: Plugin-Titel in der Sitzung")
logtext = Path(rows[0][3]).read_text() if rows else ""
check("<LOGSTART>" in logtext and "<INFO> LoxBerry Version" in logtext and "Loglevel: 7" in logtext,
      "LBLog: Kopf mit LoxBerry-Version und Protokollstufe aus der Plugin-Datenbank")
st, body = http("/ajax.php?action=log")
lg = json.loads(body)
check(lg.get("file") == Path(rows[0][3]).name and "<LOGSTART>" in lg.get("log", "") and "logfile.cgi" in lg.get("viewer", ""),
      "Log-Seite liest die aktuelle LBLog-Datei, Link zum LoxBerry-Logviewer")

notdb = LB / "data/system/notifications_sqlite.dat"


def notifications():
    if not notdb.exists():
        return []
    con = sqlite3.connect(notdb)
    r = con.execute("SELECT PACKAGE, NAME, MESSAGE, SEVERITY FROM notifications WHERE PACKAGE=?", (P,)).fetchall()
    con.close()
    return r


for _ in range(30):
    if any(n[1] == "alarm" for n in notifications()):
        break
    time.sleep(1)
alarm_n = [n for n in notifications() if n[1] == "alarm"]
check(len(alarm_n) == 1 and alarm_n[0][3] == 3 and "Störung an der Wärmepumpe" in alarm_n[0][2],
      f"Benachrichtigung bei Störung (Fehler, deutsch): {alarm_n[:1]}")
as_loxberry(f"'{LB}/bin/plugins/{P}/ctl.sh' restart", f"PYTHONPATH='{os.environ.get('LBSRC', '/tmp/lbsrc/lb')}/libs/pythonlib' LBHOMEDIR='{LB}'")
time.sleep(14)
check(len([n for n in notifications() if n[1] == "alarm"]) == 1, "Nach Neustart keine doppelte Störungsmeldung (Zustand gemerkt)")
hist = json.loads((T / "data/alarm_history.json").read_text())
check(len([h for h in hist if h["event"] == "kommt"]) == 1, "Nach Neustart kein doppelter Eintrag im Störungsverlauf")

st, body = http("/ajax.php?action=diag")
d = json.loads(body)
check(d.get("loxberry_sdk") is True and d.get("mqtt_source") == "sdk", "Daemon nutzt LoxBerry-SDK und loxberry.io.mqtt_connectiondetails")
check(d.get("loxberry", {}).get("version") == "4.0.1.6" and d.get("loxberry", {}).get("miniservers") == 2,
      "Diagnose mit LoxBerry-Version (LBSystem::lbversion) und Miniservern")

# Protokollstufe wie die Oberfläche: ajax-config-handler.cgi → plugindatabase.json
st, page = http("/index.php?form=log")
md5 = re.search(r'data-md5="([0-9a-f]{32})" data-level="(\d)"', page)
check(md5 and md5.group(2) == "7", "Log-Seite: Protokollstufe und Plugin-MD5 aus LBSystem::plugindata")
if md5:
    http("/admin/system/ajax/ajax-config-handler.cgi",
         urllib.parse.urlencode({"action": "plugin-loglevel", "pluginmd5": md5.group(1), "value": "3"}).encode())
    db = json.loads((LB / "data/system/plugindatabase.json").read_text())
    check(db["plugins"][md5.group(1)]["loglevel"] == 3, "Protokollstufe in der Plugin-Datenbank gesetzt")
    as_loxberry(f"'{LB}/bin/plugins/{P}/ctl.sh' restart", f"PYTHONPATH='{os.environ.get('LBSRC', '/tmp/lbsrc/lb')}/libs/pythonlib' LBHOMEDIR='{LB}'")
    time.sleep(6)
    newest = sorted((T / "log").glob("*_Daemon.log"))[-1].read_text()
    body_lines = [ln for ln in newest.splitlines() if re.match(r"\d\d:\d\d:\d\d\.\d+ ", ln) and "LoxBerry Version" not in ln
                  and "Ochsner OTS Version" not in ln and "Loglevel" not in ln]
    check("Loglevel: 3" in newest and not any("<INFO>" in ln or "<OK>" in ln for ln in body_lines),
          "Daemon übernimmt Protokollstufe 3 (nur Fehler)")
    http("/admin/system/ajax/ajax-config-handler.cgi",
         urllib.parse.urlencode({"action": "plugin-loglevel", "pluginmd5": md5.group(1), "value": "7"}).encode())

# Mehrsprachigkeit
st, de_page = http("/index.php?form=overview&lang=de")
st, en_page = http("/index.php?form=overview&lang=en")
check('lang="de"' in de_page and "Störungsverlauf" in de_page and "Ochsner OTS – Hilfe" in de_page,
      "Deutsch: Seite und Hilfe-Panel aus language_de.ini/help_de.ini")
check('lang="en"' in en_page and "Fault history" in en_page and "Ochsner OTS – Help" in en_page and "Störungsverlauf" not in en_page,
      "Englisch: Seite und Hilfe-Panel aus language_en.ini/help_en.ini")
st, en_app = http("/index.php?form=app&lang=en")
check('data-lang="en"' in en_app and '"APP.HP_CONNECTED":"Heat pump connected"' in en_app, "Dashboard bekommt die LoxBerry-Sprache")
st, fr_page = http("/index.php?form=values&lang=fr")
check("All data points" in fr_page, "Andere Sprache fällt auf Englisch zurück")
check('"Notify_Package":"ochsner2mqtt","Notify_Name":"alarm"' in de_page, "Navigation mit Benachrichtigungszähler (Notify_Package)")
check("css/o2m.css" in de_page and "js/o2m.js" in de_page and "jquery.mobile-1.4.5" not in de_page,
      "Eigenes CSS/JS über $htmlhead, ohne jQuery Mobile (nojqm)")
check("<TMPL_VAR " not in de_page.replace("<TMPL_VAR NAVBAR_PLAIN>", ""), "Keine offenen Platzhalter")

# Gateway V2 mit Miniserver-Auswahl
st, body = http("/ajax.php?action=gateway")
g = json.loads(body)
check([m["name"] for m in g.get("miniservers", [])] == ["Haus", "Garage"], "Miniserver aus LBSystem::get_miniservers")
hdr = {"Content-Type": "application/json", "X-O2M": "1"}
st, body = http("/ajax.php?action=gateway_subscribe", json.dumps({"topics": ["ochsner/connected", "ochsner/alarm/count"], "toms": [2]}).encode(), hdr)
subs = json.loads((LB / "config/system/subscriptions.json").read_text())["Subscriptions"]
ours = [e for e in subs if e["Id"].startswith("ochsner/")]
check(json.loads(body).get("ok") and len(ours) == 2 and all(e["Toms"] == [2] for e in ours), "Abos an Miniserver 2 (Toms)")
st, body = http("/ajax.php?action=gateway_subscribe", json.dumps({"topics": ["ochsner/connected"], "toms": [9]}).encode(), hdr)
check(not json.loads(body).get("ok"), "Unbekannter Miniserver abgelehnt")
check(json.loads((T / "data/gateway_topics.json").read_text())["topics"] == ["ochsner/connected", "ochsner/alarm/count"],
      "Eigene Gateway-Einträge für die Deinstallation gemerkt")

# Healthcheck (als loxberry, im installierten Plugin)
r = as_loxberry(f"'{LB}/bin/plugins/{P}/healthcheck' check")
try:
    hc = json.loads(r.stdout)
except ValueError:
    hc = {}
check(hc.get("status") == 4 and hc.get("result", "").startswith("The heat pump reports 1 active fault"),
      f"Healthcheck: aktive Störung als Warnung, Englisch ({hc.get('status')}: {hc.get('result')})")
check(hc.get("logfile", "").startswith(str(LB / "log/plugins" / P)) and "Daemon PID" in Path(hc.get("logfile", "/nonexist")).read_text()
      if hc.get("logfile") else False, "Healthcheck: Details als Logdatei im Plugin-Logordner")
check("url" not in hc, "Healthcheck: kein leeres url-Feld")

# Migration einer Vorversion (neue Plugin-ID) – in einem eigenen Test-LoxBerry
with tempfile.TemporaryDirectory() as tmp:
    mig = Path(tmp)
    (mig / "config/plugins/ochsner2mqtt").mkdir(parents=True)
    (mig / "data/plugins/ochsner2mqtt").mkdir(parents=True)
    (mig / "data/system").mkdir(parents=True)
    (mig / "config/plugins/ochsner2mqtt/ochsner2mqtt.json").write_text('{"host": "10.1.2.3", "password": "geheim"}')
    (mig / "data/plugins/ochsner2mqtt/history.json").write_text("{}")
    os.system(f"chown -R loxberry:loxberry '{mig}'")
    r1 = as_loxberry(f"'{ROOT}/preinstall.sh' tmp ochsner2mqtt ochsner2mqtt_5f0 0.4.0 '{mig}' /tmp/x")
    saved = mig / "data/system/ochsner2mqtt-migration"
    check(r1.returncode == 2 and "<FAIL>" in r1.stdout and (saved / "config/ochsner2mqtt.json").exists()
          and (saved / "data/history.json").exists(), "preinstall: Vorversion erkannt, gesichert, Installation abgebrochen (exit 2)")
    check(oct(saved.stat().st_mode)[-3:] == "700", "Sicherung nur für loxberry lesbar (enthält Zugangsdaten)")
    r2 = as_loxberry(f"'{ROOT}/preinstall.sh' tmp ochsner2mqtt ochsner2mqtt 0.4.0 '{mig}' /tmp/x")
    check(r2.returncode == 0, "preinstall: normale Installation/Update läuft durch")
    os.system(f"rm -rf '{mig}/config/plugins/ochsner2mqtt' '{mig}/data/plugins/ochsner2mqtt'")   # = alte Version deinstalliert
    (mig / "config/plugins/ochsner2mqtt").mkdir(parents=True)
    (mig / "config/plugins/ochsner2mqtt/ochsner2mqtt.json").write_text('{"host": ""}')
    (mig / "bin/plugins/ochsner2mqtt").mkdir(parents=True)
    (mig / "bin/plugins/ochsner2mqtt/ctl.sh").write_text("#!/bin/bash\necho ok\nexit 0\n")
    os.chmod(mig / "bin/plugins/ochsner2mqtt/ctl.sh", 0o755)
    os.system(f"chown -R loxberry:loxberry '{mig}'")
    r3 = as_loxberry(f"'{ROOT}/postinstall.sh' tmp ochsner2mqtt ochsner2mqtt 0.4.0 '{mig}' /tmp/x")
    newcfg = json.loads((mig / "config/plugins/ochsner2mqtt/ochsner2mqtt.json").read_text())
    check(newcfg.get("host") == "10.1.2.3" and (mig / "data/plugins/ochsner2mqtt/history.json").exists()
          and not saved.exists() and "übernommen" in r3.stdout, "postinstall: Einstellungen und Verlauf übernommen, Sicherung entfernt")

# Deinstallation: Dienst stoppen, retained Topics löschen, eigene Gateway-Abos entfernen
import paho.mqtt.client as mqtt  # noqa: E402
broker = int(json.loads((T / "sys/general.json").read_text())["Mqtt"]["Brokerport"])


def retained():
    seen = {}
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, "CallbackAPIVersion") else mqtt.Client()
    c.on_message = lambda _c, _u, m: seen.__setitem__(m.topic, m.payload) if m.retain else None
    c.connect("127.0.0.1", broker)
    c.subscribe("ochsner/#")
    c.loop_start()
    time.sleep(2)
    c.loop_stop()
    c.disconnect()
    return {k: v for k, v in seen.items() if v}


before = retained()
r = subprocess.run([str(ROOT / "uninstall/uninstall.sh"),
                    "/tmp", P, P, "0.4.0", str(LB), "/tmp/x"], capture_output=True, text=True, timeout=90,
                   env=dict(os.environ, PYTHONPATH=f"{os.environ.get('LBSRC', '/tmp/lbsrc/lb')}/libs/pythonlib"))
after = retained()
subs = json.loads((LB / "config/system/subscriptions.json").read_text())["Subscriptions"]
check(subprocess.run(["pgrep", "-f", f"{LB}/bin/plugins/{P}/ochsner2mqtt.py"], capture_output=True).returncode != 0,
      "Deinstallation: Dienst gestoppt")
check(len(before) > 20 and not after, f"Deinstallation: gespeicherte MQTT-Topics gelöscht ({len(before)} → {len(after)})")
check([e["Id"] for e in subs] == ["shelly/bulb/state"], "Deinstallation: nur eigene Gateway-Abos entfernt, fremde bleiben")
check(os.stat(LB / "config/system/subscriptions.json").st_uid == int(subprocess.check_output(["id", "-u", "loxberry"])),
      "Abo-Liste gehört weiter loxberry")
print(r.stdout.strip())
phplog = (T / "php.log").read_text(errors="ignore") if (T / "php.log").exists() else ""
ours = [ln for ln in phplog.splitlines() if re.search(r"(Warning|Notice|Deprecated|Fatal|Error)", ln)
        and f"plugins/{P}/" in ln and "_lbsim_router" not in ln]
check(not ours, f"PHP 8 (E_ALL): keine Warnungen/Hinweise aus dem Plugin-Code {ours[:3]}")

print("\nERGEBNIS:", "ALLES OK" if ok else "FEHLER")
sys.exit(0 if ok else 1)
