#!/bin/bash
# Startet frischen Mosquitto + Mock-Regler und führt den E2E-Test aus.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d /tmp/o2m-test.XXXX)"
BPORT=$((20000 + RANDOM % 20000))
mkdir -p "$T"/{cfg,data,log,sys}
cat > "$T/sys/general.json" <<EOF
{"Mqtt": {"Brokerhost": "127.0.0.1", "Brokerport": "$BPORT", "Brokeruser": "", "Brokerpass": "", "Uselocalbroker": "1"}}
EOF
cat > "$T/cfg/ochsner2mqtt.json" <<'EOF'
{"host": "127.0.0.1", "port": "18080", "username": "testuser", "password": "testpass", "pin": "1234",
 "poll_interval": "10", "writes_enabled": "1", "write_min_interval_sec": "120"}
EOF
mosquitto -p "$BPORT" > "$T/mosq.log" 2>&1 & MP=$!
python3 "$ROOT/tests/mock_climatix.py" --port 18080 --alarm-after 6 > "$T/mock.log" 2>&1 & KP=$!
sleep 1.5
python3 "$ROOT/tests/e2e_test.py" "$T" "$BPORT"; RC=$?
kill $MP $KP 2>/dev/null
echo "Testverzeichnis: $T"
exit $RC
