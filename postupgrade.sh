#!/bin/bash
# Nach dem Update (als loxberry): Konfiguration und Daten zurückspielen, Dienst starten
PTEMPDIR=$1; PDIR=$3; LBH=$5
BK="/tmp/${PTEMPDIR}_upgrade"
if [ -d "$BK" ]; then
    cp -a "$BK/config/." "$LBH/config/plugins/$PDIR/" 2>/dev/null
    cp -a "$BK/data/." "$LBH/data/plugins/$PDIR/" 2>/dev/null
    rm -rf "$BK"
    echo "<OK> Konfiguration und Daten übernommen"
fi
OUT="$("$LBH/bin/plugins/$PDIR/ctl.sh" restart 2>&1 | tail -n 1)"
if "$LBH/bin/plugins/$PDIR/ctl.sh" status > /dev/null 2>&1; then
    echo "<OK> Dienst ochsner2mqtt läuft ($OUT)"
else
    echo "<WARNING> Dienst konnte nicht gestartet werden: $OUT"
fi
exit 0
