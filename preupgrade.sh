#!/bin/bash
# Vor dem Update (als loxberry): Konfiguration und Daten sichern, Dienst stoppen
PTEMPDIR=$1; PDIR=$3; LBH=$5
BK="/tmp/${PTEMPDIR}_upgrade"
mkdir -p "$BK/config" "$BK/data"
cp -a "$LBH/config/plugins/$PDIR/." "$BK/config/" 2>/dev/null
cp -a "$LBH/data/plugins/$PDIR/." "$BK/data/" 2>/dev/null
echo "<INFO> Konfiguration und Daten gesichert"
if [ -x "$LBH/bin/plugins/$PDIR/ctl.sh" ]; then
    "$LBH/bin/plugins/$PDIR/ctl.sh" stop > /dev/null 2>&1
    echo "<INFO> Dienst für das Update angehalten"
fi
exit 0
