# Änderungen

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [SemVer](https://semver.org/lang/de/).

## [0.4.0] – 2026-11-13

Erste öffentliche Version. Umsetzung der Vorgaben aus dem LoxBerry-Entwickler-Wiki.

> **Umstieg von 0.3.x:** Das Plugin hat einen neuen Autor-Eintrag und damit eine neue Plugin-ID. Die Installation
> bricht beim ersten Versuch bewusst ab und sichert vorher alle Einstellungen. Dann die alte Version deinstallieren
> und 0.4.0 erneut installieren – siehe [Installation → Umstieg](docs/installation.md#umstieg-von-version-03).

### Neu
- **Benachrichtigungen** im LoxBerry bei Störungen der Wärmepumpe (kommt/geht) und wenn der Regler länger als
  15 Minuten nicht erreichbar ist – mit Zähler im Plugin-Menü, beides abschaltbar.
- **Zweisprachige Oberfläche** (Deutsch/Englisch) nach der LoxBerry-Sprache, mit zweisprachigem Hilfe-Panel.
- **Protokoll über LoxBerry:** Log-Sitzung „Daemon“ im Log Manager, Protokollstufe in der Plugin-Verwaltung oder
  im Reiter *Log* (greift ohne Neustart), Links zum LoxBerry-Logviewer.
- **Healthcheck** mit englischen Texten und Detail-Logdatei (Dienst, Verbindung, Aktualität, Störungen, MQTT).
- **MQTT Gateway V2:** bei mehreren Miniservern auswählbar, welcher die Werte bekommt.
- **Deinstallation räumt auf:** gespeicherte MQTT-Werte am Broker und die vom Plugin eingetragenen Gateway-Abos
  werden entfernt; fremde Abos bleiben.
- **Automatische Updates** über `release.cfg`/`prerelease.cfg`.
- Icon als SVG (dazu PNG 64/128/256/512).

### Geändert
- Mindestversion LoxBerry 4.0.1 (Python-SDK `loxberry.log`/`loxberry.io`).
- MQTT-Zugang über `loxberry.io.mqtt_connectiondetails` (auch TLS), Rückfall auf `general.json`.
- Weboberfläche vollständig im LoxBerry Design System (Formularzeilen, Tabellen, Callouts, PrimeIcons),
  eigenes CSS/JS über `$htmlhead`, Eingabeprüfung mit der LoxBerry-Formularvalidierung.
- Die eigene Protokollstufe in der Konfiguration entfällt (jetzt LoxBerry-Protokollstufe).
- PID-Datei je Plugin-Ordner.

### Behoben
- Nach einem Neustart des Dienstes galten bereits aktive Störungen als neu (doppelte Einträge im Störungsverlauf).

## [0.3.0] – 2026-11-12

### Neu
- Pufferspeicher im Anlagenschema automatisch erkannt (Regler-Konfiguration, externer Puffer oder plausibler
  Pufferfühler), unter *Konfiguration → Anlagenschema* fest ein- oder ausblendbar.
- Diagnose-Export ohne Zugangsdaten (Passwort, PIN, Benutzer und Seriennummer entfernt, IP gekürzt).
- MQTT Gateway V2: Topics im Reiter *Loxone* auswählen und mit einem Klick eintragen (mit Sicherung der Abo-Liste).
- Energie-Karte zeigt, seit wann aufgezeichnet wird.

### Geändert
- Anlagenschema neu gezeichnet: geschlossene Kreise mit Vorlauf und Rücklauf, synchrone Fließanimation,
  Warmwasserladung durch die Heizwendel, Heizkreise laufen mit Puffer während der Warmwasserladung weiter.
- Konfigurationsseite neu ausgerichtet, Layout für Handy und dunkle Darstellung überarbeitet.

### Behoben
- Fehlermeldungen im Installationslog (Paketquellen-Aktualisierung entfällt, Python-MQTT-Bibliothek nur bei Bedarf).
- Unterbrechungen in der Animation von Vor- und Rücklauf.

## [0.1.0 – 0.2.x]
Interne Vorversionen (nicht veröffentlicht).

[0.4.0]: https://github.com/cr0ssn0tice/LoxBerry-Plugin-ochsner2mqtt/releases/tag/v0.4.0
[0.3.0]: https://github.com/cr0ssn0tice/LoxBerry-Plugin-ochsner2mqtt/commits/main
