#!/bin/bash
# Vor der Installation (als loxberry). Argumente laut LoxBerry-Plugin-Interface:
#   $1 Temp-Ordner  $2 Plugin-Name  $3 Plugin-Ordner  $4 Version  $5 LoxBerry-Home  $6 Temp-Pfad
#
# Ab 0.4.0 steht ein neuer Autor in plugin.cfg und damit hat das Plugin eine neue
# Plugin-ID. Ist noch eine Vorversion (bis 0.3.x) installiert, würde LoxBerry das
# Plugin sonst ein zweites Mal daneben installieren (Ordner "ochsner2mqtt_xxx").
# Dann: Einstellungen und Verlauf sichern und die Installation sauber abbrechen.
# Nach dem Deinstallieren der Vorversion übernimmt postinstall.sh die Sicherung.

PNAME=$2; PDIR=$3; LBH=$5
ORIG="ochsner2mqtt"

if [ "$PDIR" = "$ORIG" ] || [ ! -d "$LBH/config/plugins/$ORIG" ]; then
    exit 0
fi

MIG="$LBH/data/system/${ORIG}-migration"
mkdir -p "$MIG" 2>/dev/null || { MIG="/tmp/${ORIG}-migration"; mkdir -p "$MIG"; }
chmod 0700 "$MIG"
mkdir -p "$MIG/config" "$MIG/data"
cp -a "$LBH/config/plugins/$ORIG/." "$MIG/config/" 2>/dev/null
for f in history.json alarm_history.json flash_counter.json write_log.json discovered.json \
         gateway_topics.json subscriptions.json.backup; do
    [ -f "$LBH/data/plugins/$ORIG/$f" ] && cp -a "$LBH/data/plugins/$ORIG/$f" "$MIG/data/"
done
chmod -R go-rwx "$MIG"
date -Is > "$MIG/created"

echo "<INFO> Eine ältere Version von \"Ochsner OTS\" ist installiert (Ordner $ORIG)."
echo "<INFO> Ab Version 0.4.0 hat das Plugin einen neuen Autor-Eintrag und damit eine neue Plugin-ID."
echo "<OK> Einstellungen und Verlauf wurden gesichert ($MIG)."
echo "<FAIL> Bitte zuerst die alte Version deinstallieren und dann diese Version erneut installieren –"
echo "<FAIL> Einstellungen, Zugangsdaten und Verlauf werden dabei automatisch übernommen."
echo "<INFO> An older version of \"Ochsner OTS\" is installed. Please uninstall it first and install this"
echo "<INFO> version again - settings and history have been saved and will be restored automatically."

# Hinweis zusätzlich in den LoxBerry-Benachrichtigungen (Python-SDK ab LoxBerry 4.0.1)
/usr/bin/python3 - "$ORIG" <<'PY' >/dev/null 2>&1
import sys
from loxberry import log
log.notify(sys.argv[1], "update",
           "Ochsner OTS 0.4.0: please uninstall the old version first, then install 0.4.0 again. "
           "Settings and history are kept. / Bitte zuerst die alte Version deinstallieren und 0.4.0 "
           "erneut installieren. Einstellungen und Verlauf bleiben erhalten.", error=True)
PY
exit 2
