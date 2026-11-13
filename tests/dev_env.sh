#!/bin/bash
# Entwicklungs-/Testumgebung: Mosquitto + Regler-Simulation + Daemon + PHP-Webserver.
# Aufruf: tests/dev_env.sh start|stop  [Testverzeichnis]
#
# Zwei Betriebsarten:
#  * LBSRC=<LoxBerry-Quellcode> gesetzt (github.com/mschlenstedt/Loxberry): "simulierter LoxBerry".
#    Das Plugin wird wie vom Installer in einen LoxBerry-Verzeichnisbaum kopiert ($T/lb) und läuft dort
#    mit den ECHTEN LoxBerry-SDKs (PHP libs/phplib, Python libs/pythonlib), echtem Kopf/Navigation,
#    echtem CSS/JS, als Benutzer loxberry und über ctl.sh – wie auf einem LoxBerry 4.
#  * ohne LBSRC: schlanke Stubs (tests/phpstub), Daemon direkt aus dem Quellordner.
# In beiden Fällen gibt es $T/cfg, $T/data, $T/log, $T/sys und $T/lbhome für die Tests.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T="${2:-/tmp/o2m-dev}"
P=ochsner2mqtt
BPORT=18834; MPORT=18080; APORT=18767; WPORT=18090
LBSRC="${LBSRC:-}"

stop() {
    [ -x "$T/lb/bin/plugins/$P/ctl.sh" ] && su loxberry -s /bin/bash -c "'$T/lb/bin/plugins/$P/ctl.sh' stop" > /dev/null 2>&1
    pkill -f "mock_climatix.py --port $MPORT" 2>/dev/null
    pkill -f "ochsner2mqtt.py --config-dir $T/cfg" 2>/dev/null
    pkill -f "$T/lb/bin/plugins/$P/ochsner2mqtt.py" 2>/dev/null
    pkill -f "mosquitto -p $BPORT" 2>/dev/null
    pkill -f "php .*-S 127.0.0.1:$WPORT" 2>/dev/null
    for _ in $(seq 1 40); do   # Daemon beendet sich geordnet (LOGEND) – abwarten
        pgrep -f "ochsner2mqtt.py --config-dir $T/cfg|$T/lb/bin/plugins/$P/ochsner2mqtt.py" > /dev/null || break
        sleep 0.25
    done
    rm -f "/dev/shm/$P.pid"
    sleep 0.3
}

test_config() {
    [ -f "$1" ] && grep -q '"host"' "$1" && return
    cat > "$1" <<EOF
{"host": "127.0.0.1", "port": $MPORT, "username": "testuser", "password": "testpass", "pin": "1234",
 "poll_interval": 10, "writes_enabled": true, "api_port": $APORT}
EOF
}

general_json() {   # $1 = Zieldatei; Basis: general.json.default des LoxBerry (falls vorhanden)
    python3 - "$1" "${LBSRC:+$LBSRC/config/system/general.json.default}" <<EOF
import json, sys
dst, default = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
g = json.load(open(default)) if default else {}
g.setdefault("Base", {}).update({"Lang": "${O2M_LANG:-de}", "Theme": "${O2M_LBTHEME:-classic-lb}"})
g.setdefault("Network", {})["Friendlyname"] = "LoxBerry"
g["Mqtt"] = {"Brokerhost": "127.0.0.1", "Brokerport": "$BPORT", "Brokeruser": "", "Brokerpass": "",
             "Uselocalbroker": "1", "Gatewayversion": ${GW_VERSION:-2}, "Udpinport": "11884", "Websocketport": "9001"}
ms = {"Port": "80", "Porthttps": "443", "Preferhttps": "0", "Useclouddns": "0", "Admin": "test", "Pass": "test",
      "Credentials": "test:test", "Admin_raw": "test", "Pass_raw": "test", "Credentials_raw": "test:test"}
g["Miniserver"] = {"1": dict(ms, Name="Haus", Ipaddress="192.0.2.10"), "2": dict(ms, Name="Garage", Ipaddress="192.0.2.11")}
json.dump(g, open(dst, "w"), indent=1)
EOF
}

install_lb() {   # Plugin wie der LoxBerry-Installer in $T/lb kopieren
    local LB="$T/lb"
    mkdir -p "$LB"/{config/system,config/plugins/$P,data/system,data/plugins/$P/cmd,log/plugins/$P,log/system_tmpfs} \
             "$LB"/{templates/plugins,webfrontend/htmlauth/plugins,webfrontend/html,bin/plugins}
    ln -sfn "$LBSRC/templates/system" "$LB/templates/system"
    ln -sfn "$LBSRC/webfrontend/html/system" "$LB/webfrontend/html/system"
    for pair in "templates:templates/plugins/$P" "bin:bin/plugins/$P" "webfrontend/htmlauth:webfrontend/htmlauth/plugins/$P"; do
        rm -rf "$LB/${pair#*:}"; cp -a "$ROOT/${pair%%:*}" "$LB/${pair#*:}"
    done
    find "$LB/bin/plugins/$P" -name __pycache__ -prune -exec rm -rf {} +
    rm -rf "$LB/plugin_icons/$P"; mkdir -p "$LB/plugin_icons"; cp -a "$ROOT/icons" "$LB/plugin_icons/$P"
    [ -f "$LB/config/plugins/$P/mqtt_subscriptions.cfg" ] || cp "$ROOT/config/mqtt_subscriptions.cfg" "$LB/config/plugins/$P/"
    test_config "$LB/config/plugins/$P/ochsner2mqtt.json"
    general_json "$LB/config/system/general.json"
    [ -f "$LB/config/system/subscriptions.json" ] || echo '{"Subscriptions": [{"Id": "shelly/bulb/state", "Toms": [], "Noncached": false, "resetaftersend": false, "Jsonexpand": false, "Json": []}]}' > "$LB/config/system/subscriptions.json"
    [ -f "$LB/data/system/plugindatabase.json" ] || cat > "$LB/data/system/plugindatabase.json" <<EOF
{"plugins": {"5f0d0c1e0b2a4c7d9e8f00112233aabb": {"md5": "5f0d0c1e0b2a4c7d9e8f00112233aabb", "author_name": "cr0ssn0tice",
 "author_email": "cr0ssn0tice@proton.me", "name": "$P", "folder": "$P", "title": "Ochsner OTS", "version": "0.4.0",
 "interface": "2.0", "autoupdate": "0", "releasecfg": "", "prereleasecfg": "", "loglevel": "7", "loglevels_enabled": "1"}}}
EOF
    # Router liegt im Plugin-Ordner: das PHP-SDK erkennt das Plugin am ersten eingebundenen Skript
    cp "$ROOT/tests/lbsim/router.php" "$LB/webfrontend/htmlauth/plugins/$P/_lbsim_router.php"
    for d in cfg:config/plugins/$P data:data/plugins/$P log:log/plugins/$P sys:config/system; do
        rm -rf "$T/${d%%:*}"; ln -sfn "$LB/${d#*:}" "$T/${d%%:*}"
    done
    ln -sfn "$LB" "$T/lbhome"
    chown -R loxberry:loxberry "$LB"
}

start() {
    stop
    mkdir -p "$T"
    nohup mosquitto -p $BPORT > "$T/mosq.log" 2>&1 &
    nohup python3 "$ROOT/tests/mock_climatix.py" --port $MPORT --alarm-after ${ALARM_AFTER:-100000} ${MOCK_ARGS:-} > "$T/mock.log" 2>&1 &
    sleep 1.2
    if [ -n "$LBSRC" ]; then
        install_lb
        local LB="$T/lb"
        if [ -n "${O2M_SEED:-}" ]; then   # Doku-Screenshots: 24-h-Verlauf und Störungsverlauf vorbelegen
            python3 "$ROOT/tests/docs/seed_history.py" "$LB/data/plugins/$P" && chown -R loxberry:loxberry "$LB/data/plugins/$P"
        fi
        su loxberry -s /bin/bash -c "PYTHONPATH='$LBSRC/libs/pythonlib' LBHOMEDIR='$LB' '$LB/bin/plugins/$P/ctl.sh' start" > "$T/daemon.out" 2>&1
        su loxberry -s /bin/bash -c "cd '$LB' && LBHOMEDIR='$LB' nohup php -d include_path='.:$LBSRC/libs/phplib' \
            -d display_errors=0 -d log_errors=1 -d error_log=/dev/stderr -d error_reporting=E_ALL -S 127.0.0.1:$WPORT -t '$LB/webfrontend/htmlauth/plugins/$P' '$LB/webfrontend/htmlauth/plugins/$P/_lbsim_router.php' \
            > '$LB/php.log' 2>&1 &"
        ln -sfn "$LB/php.log" "$T/php.log"
    else
        mkdir -p "$T"/{cfg,data,log,sys,lbhome/config/system}
        general_json "$T/sys/general.json"
        cp "$T/sys/general.json" "$T/lbhome/config/system/general.json"
        [ -f "$T/lbhome/config/system/subscriptions.json" ] || echo '{"Subscriptions": [{"Id": "shelly/bulb/state", "Toms": [], "Noncached": false, "resetaftersend": false, "Jsonexpand": false, "Json": []}]}' > "$T/lbhome/config/system/subscriptions.json"
        test_config "$T/cfg/ochsner2mqtt.json"
        nohup python3 "$ROOT/bin/ochsner2mqtt.py" --config-dir "$T/cfg" --data-dir "$T/data" --log-dir "$T/log" \
            --general-json "$T/sys/general.json" > "$T/daemon.out" 2>&1 &
        O2M_LBCSS="${O2M_LBCSS:-}" O2M_LBTHEME="${O2M_LBTHEME:-classic-lb}" O2M_T="$T" O2M_BIN="$ROOT/bin" O2M_TPL="$ROOT/templates" \
            nohup php -d include_path=".:$ROOT/tests/phpstub" -S 127.0.0.1:$WPORT -t "$ROOT/webfrontend/htmlauth" > "$T/php.log" 2>&1 &
    fi
    sleep 5
    local mode="Stub"; [ -n "$LBSRC" ] && mode="simulierter LoxBerry"
    echo "Umgebung läuft ($mode): Web http://127.0.0.1:$WPORT/  Daten $T"
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
esac
