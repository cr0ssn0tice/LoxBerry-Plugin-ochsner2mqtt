#!/bin/bash
# Alle Tests. Mit LBSRC=<LoxBerry-Quellcode> (github.com/mschlenstedt/Loxberry) laufen die Suiten 2–6 in einem
# simulierten LoxBerry 4 mit den echten PHP-/Python-SDKs (siehe dev_env.sh); ohne LBSRC mit Stubs.
# Suite 1 läuft immer ohne SDK und prüft damit die Rückfallwege des Dienstes.
# Optional: LBCSS=<Ordner mit LoxBerry-CSS> für realistische Seiten im Stub-Modus.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RC=0
HAVE_PW=0; python3 -c "import playwright" 2>/dev/null && HAVE_PW=1
export LBSRC="${LBSRC:-}"
[ -n "$LBSRC" ] && echo "(simulierter LoxBerry aus $LBSRC)" || echo "(Stub-Modus – LBSRC setzen für die echten LoxBerry-SDKs)"
env_start() { rm -rf /tmp/o2m-dev; O2M_LBCSS="${LBCSS:-}" "$ROOT/tests/dev_env.sh" start > /dev/null; }
"$ROOT/tests/dev_env.sh" stop  # eine laufende Entwicklungsumgebung belegt sonst die Ports
echo "=== 1/6 Daemon, MQTT, Schreibschutz (ohne LoxBerry-SDK)"
OUT1="$("$ROOT/tests/run_tests.sh")"
echo "$OUT1" | grep -E "^(PASS|FAIL)|ERGEBNIS"
echo "$OUT1" | grep -q "ERGEBNIS: ALLES OK" || RC=1
echo "=== 2/6 App-API und Loxone-Befehle"
env_start
python3 "$ROOT/tests/api_test.py" /tmp/o2m-dev || RC=1
echo "=== 3/6 Browser-Oberfläche (Bedienung)"
if [ $HAVE_PW = 1 ]; then
    env_start
    python3 "$ROOT/tests/ui_test.py" /tmp/o2m-dev || RC=1
else echo "(Playwright nicht installiert – übersprungen)"; fi
echo "=== 4/6 Puffer-Erkennung, Diagnose, MQTT Gateway V2"
MOCK_ARGS="--profile 208buf" env_start
python3 "$ROOT/tests/v03_test.py" /tmp/o2m-dev || RC=1
echo "=== 5/6 Browser: Anlagenschema, Konfiguration, Loxone-Seite"
if [ $HAVE_PW = 1 ]; then
    MOCK_ARGS="--profile 208buf" env_start
    python3 "$ROOT/tests/ui_v03_test.py" /tmp/o2m-dev || RC=1
else echo "(Playwright nicht installiert – übersprungen)"; fi
echo "=== 6/6 LoxBerry-Anforderungen (plugin.cfg, Sprache, LBLog, Benachrichtigung, Healthcheck, Migration, Deinstallation)"
ALARM_AFTER=4 env_start
python3 "$ROOT/tests/v04_test.py" /tmp/o2m-dev || RC=1
"$ROOT/tests/dev_env.sh" stop
exit $RC
