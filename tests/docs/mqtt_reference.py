#!/usr/bin/env python3
"""Erzeugt docs/mqtt-referenz.md aus der Topic-Liste des laufenden Dienstes (Testumgebung, Profil 518).

Aufruf: mqtt_reference.py <ausgabedatei> [web-url]
"""
import json
import re
import sys
import urllib.request

out = sys.argv[1]
web = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:18090"
d = json.loads(urllib.request.urlopen(f"{web}/ajax.php?action=api&ep=topics", timeout=20).read())
base = d["base"]
TEXT = re.compile(r"_text$|/mode$|/preset$|/name$")


def row(topic, name, unit):
    vi = (base + "/" + topic).replace("/", "_")
    kind = "Text" if TEXT.search(topic) else "Zahl"
    return f"| `{base}/{topic}` | {name} | {unit or ''} | {kind} | `{vi}` |"


areas = {}
for t in d["topics"]:
    areas.setdefault(t["area"], []).append(t)
hc_names = {c["name"]: c["index"] for c in d["circuits"]}
L = ["# MQTT-Referenz", "",
     "Alle Topics, die das Plugin veröffentlicht, und alle Befehle, die es annimmt. Erzeugt aus der Testanlage",
     "(Air Hawk 518 mit drei Heizkreisen, Warmwasser und Puffer, `tests/docs/mqtt_reference.py`). Welche Topics es",
     "bei dir gibt, hängt von der Anlage ab – die vollständige Liste deiner Anlage zeigt der Reiter **Loxone**.", "",
     f"Basis-Topic: `{base}` (einstellbar). Werte sind `retained`. Das MQTT Gateway macht aus `/` ein `_` – das ist",
     "der Name des virtuellen Eingangs im Miniserver. Text-Topics als **virtuellen Texteingang** anlegen.", "",
     "## Inhalt", "", "- [Plugin und Störungen](#plugin-und-störungen)", "- [Wärmepumpe](#wärmepumpe)",
     "- [Warmwasser](#warmwasser)", "- [Heizkreise](#heizkreise)", "- [Rohwerte aller Katalogpunkte](#rohwerte-aller-katalogpunkte)",
     "- [Befehle](#befehle)", "",
     "## Plugin und Störungen", "", "| Topic | Bedeutung | Einheit | Typ | Virtueller Eingang |", "|---|---|---|---|---|"]
for topic, name, kind in (("status", "Dienst online/offline (Last Will)", "Text"),
                          ("connected", "Regler erreichbar (1/0)", "Zahl"),
                          ("alarm/count", "Anzahl aktiver Störungen", "Zahl"),
                          ("alarm/active", "Aktive Störungen als Text (`keine`, wenn alles in Ordnung ist)", "Text"),
                          ("alarm/<punkt>", "Einzelne Störung (1 = aktiv), z. B. `alarm/niederdruck_stoerung`", "Zahl"),
                          ("info/model", "Anlagentyp laut Regler", "Text"), ("info/sw_version", "Reglersoftware", "Text"),
                          ("info/points", "Anzahl erkannter Datenpunkte", "Zahl"),
                          ("cmd_result", "Ergebnis des letzten Befehls (JSON mit `ok`, `message`)", "Text")):
    L.append(f"| `{base}/{topic}` | {name} |  | {kind} | `{(base + '/' + topic).replace('/', '_')}` |")
for area, title in (("Wärmepumpe", "Wärmepumpe"), ("Warmwasser", "Warmwasser")):
    L += ["", f"## {title}", "", "| Topic | Bedeutung | Einheit | Typ | Virtueller Eingang |", "|---|---|---|---|---|"]
    L += [row(t["topic"], t["name"], t.get("unit")) for t in sorted(areas.get(area, []), key=lambda t: t["topic"])]
first = d["circuits"][0]
L += ["", "## Heizkreise", "",
      f"Je Heizkreis dieselben Topics unter `{base}/plant/hc<n>/…` (n = 1–4). Beispiel Heizkreis {first['index']}",
      f"({first['name']}); die Topics für Raumtemperatur und Feuchte gibt es nur mit Raumfühler.", "",
      "| Topic | Bedeutung | Einheit | Typ | Virtueller Eingang |", "|---|---|---|---|---|"]
L += [row(t["topic"], t["name"], t.get("unit")) for t in sorted(areas.get(first["name"], []), key=lambda t: t["topic"])]
L += ["", "## Rohwerte aller Katalogpunkte", "",
      "Zusätzlich (abschaltbar unter *Konfiguration → Rohpunkte senden*) jeder erkannte Katalogpunkt unter",
      f"`{base}/<punkt>`, z. B. `{base}/gemittelte_aussentemperatur_h_k_grenze`. Die Liste mit Namen, Topic und Objektadresse zeigt der",
      "Reiter **Alle Werte**. Für Loxone sind die `plant/…`-Topics oben gedacht; die Rohwerte eher für Node-RED o. Ä.", "",
      "## Befehle", "",
      f"Befehle gehen an `{base}/cmd/<befehl>` – aus Loxone per **virtuellem Ausgang** an `/dev/udp/<loxberry>/11884`",
      f"mit dem Befehl `publish {base}/cmd/<befehl> <wert>`. Schreiben muss in der Konfiguration erlaubt sein.",
      "Gespeicherte (retained) Befehle führt das Plugin nie aus.", "",
      "| Befehl | Werte | Wirkung |", "|---|---|---|"]
L += [f"| `{base}/cmd/{c['topic']}` | {c['values'].replace('|', '·')} | {c['text']} |" for c in d["commands"]]
L += ["", f"Zusätzlich gibt es `{base}/set/<punkt> <wert>` für einzelne Katalogpunkte (wie im Experten-Editor).", ""]
open(out, "w", encoding="utf-8").write("\n".join(L))
print(f"{out}: {len(L)} Zeilen")
