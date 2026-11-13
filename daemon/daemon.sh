#!/bin/bash
# Wird beim Booten des LoxBerry als root ausgeführt und startet den Daemon im Hintergrund.
# REPLACELBPBINDIR ersetzt der LoxBerry-Installer durch den echten Plugin-Pfad.
CTL="REPLACELBPBINDIR/ctl.sh"
if [ -x "$CTL" ]; then
    "$CTL" start > /dev/null 2>&1 &
    /usr/bin/logger "LoxBerry Plugin ochsner2mqtt: Daemon-Start angestoßen"
else
    /usr/bin/logger "LoxBerry Plugin ochsner2mqtt: $CTL nicht gefunden"
fi
exit 0
