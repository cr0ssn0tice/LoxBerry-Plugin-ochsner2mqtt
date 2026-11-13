#!/bin/bash
# Nach der Installation (als loxberry): Rechte setzen, Sicherung einer Vorversion
# übernehmen (siehe preinstall.sh) und den Dienst starten.
# Ausgaben mit <OK>/<INFO>/<WARNING> formatiert das LoxBerry-Installationslog.
PDIR=$3; LBH=$5
CFG="$LBH/config/plugins/$PDIR"
DATA="$LBH/data/plugins/$PDIR"

for MIG in "$LBH/data/system/ochsner2mqtt-migration" "/tmp/ochsner2mqtt-migration"; do
    [ -d "$MIG" ] || continue
    if [ -f "$MIG/config/ochsner2mqtt.json" ]; then
        cp -a "$MIG/config/ochsner2mqtt.json" "$CFG/ochsner2mqtt.json"
        cp -a "$MIG/data/." "$DATA/" 2>/dev/null
        echo "<OK> Einstellungen und Verlauf der Vorversion übernommen"
    fi
    rm -rf "$MIG"
done

chmod 0640 "$CFG/ochsner2mqtt.json" 2>/dev/null
mkdir -p "$DATA/cmd"
OUT="$("$LBH/bin/plugins/$PDIR/ctl.sh" restart 2>&1 | tail -n 1)"
if "$LBH/bin/plugins/$PDIR/ctl.sh" status > /dev/null 2>&1; then
    echo "<OK> Dienst ochsner2mqtt läuft ($OUT)"
else
    echo "<WARNING> Dienst konnte nicht gestartet werden: $OUT – Protokoll im Plugin prüfen"
fi
exit 0
