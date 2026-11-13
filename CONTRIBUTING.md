# Mitmachen

Fehlerberichte, Ideen und Pull Requests sind willkommen – besonders Rückmeldungen zu weiteren Ochsner-Anlagen.

## Fehler melden
Bitte die Vorlage **Fehler melden** nutzen und den **Diagnose-Export** anhängen (Konfiguration → Diagnose).
Er enthält keine Zugangsdaten. Hinweise zur Fehlersuche: [docs/fehlersuche.md](docs/fehlersuche.md).

## Code beitragen
1. Fork, Branch, Änderung.
2. Tests: `tests/run_all.sh` – mit `LBSRC=<Pfad zum LoxBerry-Quellcode>` laufen sie in einem simulierten LoxBerry 4
   mit den echten SDKs (Details: [docs/entwicklung.md](docs/entwicklung.md)).
3. Neue Oberflächentexte immer in `templates/lang/language_de.ini` **und** `language_en.ini` – der Test
   `tests/v04_test.py` prüft, dass beide Sprachdateien vollständig sind.
4. Zeilenende LF, UTF-8 ohne BOM, keine festen `/opt/…`-Pfade (LoxBerry-Vorgaben).
5. Pull Request mit kurzer Beschreibung und Eintrag in `CHANGELOG.md`.

Schreibzugriffe auf den Regler nur über die vorhandenen Schutzmechanismen (Schreibsperre, Grenzen, Tageslimit,
Flash-Zähler). Neue schreibbare Werte bitte im PR begründen.

## Herkunft des Codes
Katalog, Anlagenlogik und Dashboard stammen aus
[permissionBRICK/OTS-HomeAssistant](https://github.com/permissionBRICK/OTS-HomeAssistant) (MIT). Änderungen an
übernommenen Dateien sind mit `o2m:` markiert; Verbesserungen an diesen Teilen gern auch dort vorschlagen.
