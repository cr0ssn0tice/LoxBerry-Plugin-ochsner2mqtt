#!/bin/bash
# Deinstallation (läuft als root, bevor LoxBerry die Plugin-Dateien löscht).
# $1 Temp  $2 Plugin-Name  $3 Plugin-Ordner  $4 Version  $5 LoxBerry-Home
# Räumt auf, was das Plugin außerhalb seiner eigenen Ordner verändert hat:
#   1. Daemon stoppen
#   2. gespeicherte (retained) MQTT-Werte des Plugins am Broker löschen
#   3. vom Plugin eingetragene Abos aus der Abo-Liste des MQTT Gateway V2 entfernen
PDIR=$3; LBH=$5
BIN="$LBH/bin/plugins/$PDIR"
CFG="$LBH/config/plugins/$PDIR"
DATA="$LBH/data/plugins/$PDIR"

[ -x "$BIN/ctl.sh" ] && "$BIN/ctl.sh" stop > /dev/null 2>&1
rm -f "/dev/shm/$PDIR.pid" /dev/shm/ochsner2mqtt.pid
echo "<OK> Dienst gestoppt"

if [ -f "$BIN/ochsner2mqtt.py" ]; then
    OUT="$(su loxberry -s /bin/bash -c "LBHOMEDIR='$LBH' timeout 20 /usr/bin/python3 '$BIN/ochsner2mqtt.py' --lbhome '$LBH' --clear-retained" 2>&1 | tail -n 1)"
    echo "<INFO> MQTT: $OUT"
fi

SUBS="$LBH/config/system/subscriptions.json"
if [ -f "$SUBS" ] && [ -f "$DATA/gateway_topics.json" ]; then
    /usr/bin/python3 -I - "$SUBS" "$DATA/gateway_topics.json" <<'PY'
import fcntl, json, sys
subs_file, ours_file = sys.argv[1], sys.argv[2]
try:
    ours = set(json.load(open(ours_file, encoding="utf-8")).get("topics", []))
except (OSError, ValueError):
    ours = set()
if not ours:
    sys.exit(0)
with open(subs_file, "r+", encoding="utf-8") as fh:          # r+: Besitzer und Rechte bleiben erhalten
    fcntl.flock(fh, fcntl.LOCK_EX)
    try:
        data = json.load(fh)
    except ValueError:
        print("<WARNING> Abo-Liste des MQTT Gateway unlesbar - nichts geändert")
        sys.exit(0)
    entries = data.get("Subscriptions") or []
    keep = [e for e in entries if e.get("Id") not in ours]
    if len(keep) != len(entries):
        data["Subscriptions"] = keep
        fh.seek(0)
        fh.truncate()
        json.dump(data, fh, indent=1, ensure_ascii=False)
    print("<OK> MQTT Gateway V2: %d Abos des Plugins entfernt" % (len(entries) - len(keep)))
PY
fi
exit 0
