#!/bin/bash
# Baut das Installations-ZIP für die LoxBerry-Plugin-Verwaltung: dist/LoxBerry-Plugin-ochsner2mqtt-<version>.zip
# Enthält nur, was auf dem LoxBerry gebraucht wird (ohne docs/, tests/, tools/, .github/).
# Prüft vorher, dass plugin.cfg, Daemon und release.cfg dieselbe Version nennen.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
V="$(sed -n 's/^VERSION=//p' plugin.cfg | head -n 1)"
PYV="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' bin/ochsner2mqtt.py)"
RELV="$(sed -n 's/^VERSION=//p' release.cfg)"
[ "$V" = "$PYV" ] || { echo "plugin.cfg ($V) und bin/ochsner2mqtt.py ($PYV) unterscheiden sich" >&2; exit 1; }
[ "$V" = "$RELV" ] || echo "Hinweis: release.cfg nennt $RELV (plugin.cfg $V) – vor dem Veröffentlichen anpassen" >&2
OUT="dist/LoxBerry-Plugin-ochsner2mqtt-$V.zip"
mkdir -p dist
rm -f "$OUT"
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    FILES="$(git ls-files)"
else
    FILES="$(find . -type f -not -path './.git/*' | sed 's|^\./||')"
fi
echo "$FILES" | grep -v -E '^(docs/|tests/|tools/|\.github/|dist/)|^(release|prerelease)\.cfg$|^\.git|^CHANGELOG\.md$|^CONTRIBUTING\.md$|^SECURITY\.md$|__pycache__|\.pyc$' \
    | zip -q -X "$OUT" -@
echo "$OUT ($(du -k "$OUT" | cut -f1) KB, $(unzip -l "$OUT" | tail -n 1 | awk '{print $2}') Dateien)"
