#!/bin/bash
# Als root: Python-MQTT-Bibliothek sicherstellen.
# Ab LoxBerry 4.0.1 gehört python3-paho-mqtt zum System. Das Plugin bringt deshalb
# keine dpkg/apt-Datei mehr mit – so muss der Installer die Paketquellen nicht
# neu laden (das scheitert auf Systemen mit veralteten Fremdquellen).
if /usr/bin/python3 -c "import paho.mqtt.client" 2>/dev/null; then
    V="$(/usr/bin/python3 -c 'import paho.mqtt as m; print(getattr(m, "__version__", "?"))' 2>/dev/null)"
    echo "<OK> Python-MQTT-Bibliothek vorhanden (paho-mqtt $V)"
    exit 0
fi
echo "<INFO> python3-paho-mqtt fehlt – wird installiert"
export DEBIAN_FRONTEND=noninteractive
if ! apt-get -y -q --no-install-recommends install python3-paho-mqtt > /dev/null 2>&1; then
    # Paketlisten zu alt: neu laden (Fehler einzelner Fremdquellen sind hier egal)
    apt-get -q update > /dev/null 2>&1
    apt-get -y -q --no-install-recommends install python3-paho-mqtt > /dev/null 2>&1
fi
if /usr/bin/python3 -c "import paho.mqtt.client" 2>/dev/null; then
    echo "<OK> python3-paho-mqtt installiert"
else
    echo "<ERROR> python3-paho-mqtt konnte nicht installiert werden – bitte 'apt-get install python3-paho-mqtt' als root ausführen"
fi
exit 0
