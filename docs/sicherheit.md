# Sicherheit und Schutz des Reglers

[← Übersicht](../README.md) · [Installation](installation.md) · [Bedienung](bedienung.md) · [Loxone](loxone.md) · [MQTT-Referenz](mqtt-referenz.md) · **Sicherheit** · [Fehlersuche](fehlersuche.md) · [Entwicklung](entwicklung.md)

---

Eine Wärmepumpe ist keine Spielerei: Das Plugin ist so gebaut, dass es den Regler im Zweifel **nicht** verändert.

## Schutz des Reglers

| Schutz | Wirkung |
|---|---|
| **Schreibsperre** | Ab Werk liest das Plugin nur. Schreiben muss in der Konfiguration ausdrücklich erlaubt werden – das gilt für App, MQTT/Loxone und Experten-Editor gleichermaßen. |
| **Frisch lesen, dann schreiben** | Vor jedem Schreiben liest das Plugin den aktuellen Wert. Ist er unverändert, wird nichts geschrieben. |
| **Grenzen** | Minimum, Maximum und Schrittweite aus dem Katalog werden geprüft; der Regler verwirft unzulässige Werte zusätzlich selbst. |
| **Tageslimit** | Höchstens 100 Schreibzugriffe pro Tag (einstellbar, 0–1000). |
| **Mindestabstand** | Für Befehle aus MQTT/Loxone (Automationen) je Datenpunkt mindestens 120 s (einstellbar). Bedienung in der App ist ausgenommen. |
| **Keine Altbefehle** | Gespeicherte (retained) MQTT-Befehle werden nie ausgeführt. |
| **Feste Rollen** | Die App darf nur freigegebene Rollen beschreiben (Sollwerte, Kurven, Betriebsarten, Zeitprogramme). Alles andere bleibt lesend; einzelne Parameter nur bewusst über den Experten-Editor mit Bestätigung. |
| **Schreibsequenzen der Ochsner-App** | Die Abfolge der Schreibzugriffe entspricht der Ochsner-App (aus der HA-Integration übernommen). Komfort/Eco schreibt z. B. nur den einen Punkt, der sich ändert. |
| **Flash-Zähler und Protokoll** | Jeder Schreibzugriff wird gezählt (gesamt, pro Tag, pro Punkt) und mit Quelle protokolliert. Laut Siemens hält der Flash-Speicher etwa 100.000 Zyklen. |

## Zugangsdaten und Daten

- Benutzer, Passwort und PIN des Reglers liegen nur in `config/plugins/ochsner2mqtt/ochsner2mqtt.json`
  (Rechte 0640, Benutzer *loxberry*). Die Weboberfläche zeigt nur, *ob* etwas gespeichert ist, und gibt die Werte
  nie an den Browser zurück. Im Protokoll tauchen sie nicht auf.
- Das Plugin bringt **keine Standard-Zugangsdaten** mit und probiert keine aus. Die Zugangsdaten gibt es beim
  Ochsner-Kundendienst bzw. beim Service-Partner.
- Der **Diagnose-Export** enthält weder Passwort, PIN, Benutzer noch Seriennummer; die IP-Adresse ist gekürzt.
- Beim Umstieg von 0.3 liegt die Sicherung der Konfiguration nur kurz und nur für *loxberry* lesbar (0700) auf
  dem LoxBerry und wird nach der Übernahme gelöscht.
- **Keine Cloud:** Alle Daten bleiben im Heimnetz. Das Plugin spricht nur mit dem Regler und dem MQTT-Broker des
  LoxBerry; die Weboberfläche lädt nichts von fremden Servern. (Die Update-Prüfung macht der LoxBerry selbst.)

## Weboberfläche und lokale API

- Die Seiten liegen im geschützten Bereich des LoxBerry (`/admin/plugins/…`, LoxBerry-Anmeldung).
- Schreibende Anfragen sind nur per POST mit eigenem Header und gleichem Origin möglich (Schutz gegen CSRF).
  Alle Eingaben prüft der Server noch einmal, unabhängig von der Prüfung im Browser.
- Der Dienst stellt seine API nur auf `127.0.0.1` bereit und verlangt ein zufälliges Token, das nur der LoxBerry
  kennt.
- Aufräumen bei der Deinstallation: retained MQTT-Werte und die eigenen Gateway-Abos werden entfernt.

## Empfehlungen für das Netz

- Dem Regler eine feste IP geben und ihn – wenn möglich – in ein eigenes Netz/VLAN für Haustechnik legen,
  in dem nur der LoxBerry ihn erreichen darf.
- Den Regler nicht per Portweiterleitung ins Internet stellen. Für den Zugriff von unterwegs den LoxBerry bzw.
  Loxone über ein VPN nutzen.
- Den MQTT-Broker des LoxBerry mit Benutzer und Passwort betreiben (Standard beim MQTT Gateway).

## Sicherheitslücke gefunden?

Bitte vertraulich melden – siehe [SECURITY.md](../SECURITY.md).

## Haftung

Das Projekt ist inoffiziell und hat keine Verbindung zu Ochsner oder Siemens. Schreibzugriffe auf den Regler
erfolgen auf eigene Verantwortung. Im Zweifel Einstellungen mit dem Fachbetrieb abstimmen.
