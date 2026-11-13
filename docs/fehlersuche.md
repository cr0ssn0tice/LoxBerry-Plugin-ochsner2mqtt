# Fehlersuche und FAQ

[← Übersicht](../README.md) · [Installation](installation.md) · [Bedienung](bedienung.md) · [Loxone](loxone.md) · [MQTT-Referenz](mqtt-referenz.md) · [Sicherheit](sicherheit.md) · **Fehlersuche** · [Entwicklung](entwicklung.md)

---

## Werkzeuge

| Werkzeug | Wo | Wofür |
|---|---|---|
| **Reiter Störungen** | Plugin | Verbindung, letzte Abfrage, Anzahl Datenpunkte, MQTT, aktive Störungen |
| **Log** | Plugin → Log, oder LoxBerry → Log Manager → *Ochsner OTS* | Was der Dienst tut. Für die Fehlersuche Protokollstufe **Info** oder **Debug** |
| **Healthcheck** | LoxBerry → Mein LoxBerry → Healthcheck | Dienst läuft? Regler erreichbar? Daten aktuell? Störungen? MQTT? – mit Detail-Logdatei |
| **Diagnose-Export** | Plugin → Konfiguration → Diagnose | JSON mit Fähigkeiten, Rollenwerten, Scan und Log-Auszug – ohne Zugangsdaten |
| **Benachrichtigungen** | Glocke oben rechts im LoxBerry | Störungen der Wärmepumpe und längere Verbindungsabbrüche |

Der Healthcheck meldet:

| Status | Bedeutung |
|---|---|
| OK | verbunden, Daten aktuell, keine Störung |
| Info | noch nicht eingerichtet (IP fehlt) |
| Warnung | aktive Störung an der Wärmepumpe · letzte erfolgreiche Abfrage älter als 15 min · MQTT getrennt |
| Fehler | Dienst läuft nicht · keine Verbindung zum Regler (mit Grund) |

## Häufige Fragen

<details>
<summary><b>„Keine Verbindung: HTTP 401 … Benutzer/Passwort/PIN prüfen“</b></summary>

Der Regler lehnt die Zugangsdaten ab. Benutzer, Passwort und PIN unter *Konfiguration → Wärmepumpe* neu eintragen
(Passwort und PIN werden nur überschrieben, wenn das Feld nicht leer ist). Die richtigen Daten hat der
Ochsner-Kundendienst bzw. dein Service-Partner.
</details>

<details>
<summary><b>„Keine Verbindung“ ohne 401 (Zeitüberschreitung, verweigert)</b></summary>

- Stimmt die IP-Adresse? Ist sie fest vergeben (nach einem Router-Neustart nicht geändert)?
- Kann der LoxBerry den Regler erreichen (gleiches Netz/VLAN, Firewall)? Der Port ist normalerweise 80.
- Nach 15 Minuten ohne Verbindung meldet sich das Plugin zusätzlich über die LoxBerry-Benachrichtigungen.
</details>

<details>
<summary><b>Die Installation bricht ab: „Bitte zuerst die alte Version deinstallieren“</b></summary>

Das ist Absicht beim Umstieg von 0.3 auf 0.4: neue Plugin-ID. Alte Version deinstallieren, 0.4 erneut
installieren – die Einstellungen werden übernommen. Siehe
[Installation → Umstieg](installation.md#umstieg-von-version-03).
</details>

<details>
<summary><b>Im Miniserver kommen keine Werte an (MQTT Gateway V2)</b></summary>

Das Gateway V2 leitet nur eingetragene Topics weiter. Im Reiter **Loxone** Topics auswählen und
**Im MQTT Gateway eintragen**. Danach im Miniserver die virtuellen Eingänge mit exakt den angezeigten Namen
anlegen. Kontrolle: LoxBerry → MQTT Gateway → *Incoming Overview*.
</details>

<details>
<summary><b>Im Miniserver kommen keine Werte an (MQTT Gateway V1)</b></summary>

- Läuft MQTT im Plugin? Statusleiste der App: „MQTT ochsner/…“ grün.
- Stimmen die Namen der virtuellen Eingänge (`ochsner_plant_hp_outdoor` …)? Groß-/Kleinschreibung beachten.
- Text-Topics brauchen einen **virtuellen Texteingang**.
</details>

<details>
<summary><b>Befehle aus Loxone wirken nicht</b></summary>

Ergebnis steht in `ochsner/cmd_result` und im Schreibprotokoll (Experten-Editor). Typische Gründe:
- „Schreiben ist in den Einstellungen deaktiviert“ → *Konfiguration → Schreiben erlauben*.
- „Ratenlimit: derselbe Punkt erst in … s wieder“ → Mindestabstand je Punkt (Standard 120 s).
- Tageslimit erreicht → Zähler in der Statusleiste der App.
- Adresse des virtuellen Ausgangs: `/dev/udp/<IP-des-LoxBerry>/11884`, Befehl `publish ochsner/cmd/… <wert>`.
</details>

<details>
<summary><b>Der Pufferspeicher fehlt im Schema – oder wird angezeigt, obwohl keiner da ist</b></summary>

*Konfiguration → Anlagenschema → Pufferspeicher* auf „immer anzeigen“ bzw. „nie anzeigen“. Unter dem Feld steht,
warum das Plugin bei „automatisch“ so entschieden hat (im Regler konfiguriert, externer Puffer gemeldet oder über
den Pufferfühler erkannt).
</details>

<details>
<summary><b>Werte fehlen nach einem Software-Update des Reglers</b></summary>

Reiter **Störungen** → *Datenpunkte neu scannen*. Der Scan liest nur und dauert wenige Sekunden.
</details>

<details>
<summary><b>Die Karte „Letzte 24 h“ ist leer</b></summary>

Den Verlauf zeichnet das Plugin selbst auf. Nach der Installation füllt sich die Karte nach und nach
(„Aufzeichnung seit …“).
</details>

<details>
<summary><b>Das Log ist leer</b></summary>

LoxBerry stellt neue Plugins auf die Protokollstufe „Fehler“. Im Reiter **Log** auf *Info* oder *Debug* stellen –
der Dienst übernimmt das nach spätestens einer Minute.
</details>

<details>
<summary><b>Dienst läuft nicht</b></summary>

Reiter **Störungen** → *Dienst neu starten*, oder auf der Konsole
`$LBHOMEDIR/bin/plugins/ochsner2mqtt/ctl.sh restart`. Startet er nicht, steht der Grund in
`log/plugins/ochsner2mqtt/daemon_stdout.log` bzw. im Log. Ein Watchdog versucht alle 5 Minuten einen Neustart.
</details>

## Fehler melden

Bitte ein [Issue](https://github.com/cr0ssn0tice/LoxBerry-Plugin-ochsner2mqtt/issues/new/choose) mit der Vorlage
**Fehler melden** anlegen und den **Diagnose-Export** anhängen. Keine Zugangsdaten in Issues schreiben.
