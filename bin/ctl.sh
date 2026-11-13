#!/bin/bash
# ctl.sh – Start/Stopp/Status des ochsner2mqtt-Daemons (läuft als Benutzer loxberry)
# Aufruf: ctl.sh start|stop|restart|status|watchdog

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PLUGINFOLDER="$(basename "$SCRIPT_DIR")"
LBHOMEDIR="${SCRIPT_DIR%/bin/plugins/*}"
LOGDIR="$LBHOMEDIR/log/plugins/$PLUGINFOLDER"
PIDFILE="/dev/shm/${PLUGINFOLDER}.pid"
DAEMON="$SCRIPT_DIR/ochsner2mqtt.py"

mkdir -p "$LOGDIR" 2>/dev/null

is_running() {
    [ -f "$PIDFILE" ] || return 1
    local pid; pid="$(cat "$PIDFILE" 2>/dev/null)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && grep -q "ochsner2mqtt.py" "/proc/$pid/cmdline" 2>/dev/null
}

run_as_loxberry() {
    if [ "$(id -un)" = "loxberry" ]; then
        bash -c "$1"
    else
        su loxberry -s /bin/bash -c "$1"
    fi
}

start() {
    if is_running; then echo "läuft bereits (PID $(cat "$PIDFILE"))"; return 0; fi
    # stdout/stderr nur für Abstürze vor dem Start des LoxBerry-Logs (Python-Traceback)
    run_as_loxberry "LBHOMEDIR='$LBHOMEDIR' nohup /usr/bin/python3 '$DAEMON' --lbhome '$LBHOMEDIR' >> '$LOGDIR/daemon_stdout.log' 2>&1 & echo \$! > '$PIDFILE'"
    sleep 1
    if is_running; then echo "gestartet (PID $(cat "$PIDFILE"))"; else echo "Start fehlgeschlagen – siehe $LOGDIR"; return 1; fi
}

stop() {
    if ! is_running; then rm -f "$PIDFILE"; echo "läuft nicht"; return 0; fi
    local pid; pid="$(cat "$PIDFILE")"
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    rm -f "$PIDFILE"
    echo "gestoppt"
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) if is_running; then echo "running $(cat "$PIDFILE")"; else echo "stopped"; exit 1; fi ;;
    watchdog) is_running || { logger "ochsner2mqtt: Daemon lief nicht – Neustart"; start; } ;;
    *) echo "Aufruf: $0 start|stop|restart|status|watchdog"; exit 2 ;;
esac
