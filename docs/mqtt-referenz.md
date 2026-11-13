# MQTT-Referenz

Alle Topics, die das Plugin veröffentlicht, und alle Befehle, die es annimmt. Erzeugt aus der Testanlage
(Air Hawk 518 mit drei Heizkreisen, Warmwasser und Puffer, `tests/docs/mqtt_reference.py`). Welche Topics es
bei dir gibt, hängt von der Anlage ab – die vollständige Liste deiner Anlage zeigt der Reiter **Loxone**.

Basis-Topic: `ochsner` (einstellbar). Werte sind `retained`. Das MQTT Gateway macht aus `/` ein `_` – das ist
der Name des virtuellen Eingangs im Miniserver. Text-Topics als **virtuellen Texteingang** anlegen.

## Inhalt

- [Plugin und Störungen](#plugin-und-störungen)
- [Wärmepumpe](#wärmepumpe)
- [Warmwasser](#warmwasser)
- [Heizkreise](#heizkreise)
- [Rohwerte aller Katalogpunkte](#rohwerte-aller-katalogpunkte)
- [Befehle](#befehle)

## Plugin und Störungen

| Topic | Bedeutung | Einheit | Typ | Virtueller Eingang |
|---|---|---|---|---|
| `ochsner/status` | Dienst online/offline (Last Will) |  | Text | `ochsner_status` |
| `ochsner/connected` | Regler erreichbar (1/0) |  | Zahl | `ochsner_connected` |
| `ochsner/alarm/count` | Anzahl aktiver Störungen |  | Zahl | `ochsner_alarm_count` |
| `ochsner/alarm/active` | Aktive Störungen als Text (`keine`, wenn alles in Ordnung ist) |  | Text | `ochsner_alarm_active` |
| `ochsner/alarm/<punkt>` | Einzelne Störung (1 = aktiv), z. B. `alarm/niederdruck_stoerung` |  | Zahl | `ochsner_alarm_<punkt>` |
| `ochsner/info/model` | Anlagentyp laut Regler |  | Text | `ochsner_info_model` |
| `ochsner/info/sw_version` | Reglersoftware |  | Text | `ochsner_info_sw_version` |
| `ochsner/info/points` | Anzahl erkannter Datenpunkte |  | Zahl | `ochsner_info_points` |
| `ochsner/cmd_result` | Ergebnis des letzten Befehls (JSON mit `ok`, `message`) |  | Text | `ochsner_cmd_result` |

## Wärmepumpe

| Topic | Bedeutung | Einheit | Typ | Virtueller Eingang |
|---|---|---|---|---|
| `ochsner/plant/hp/aux_flow` | Zusatzheizung Vorlauftemperatur | °C | Zahl | `ochsner_plant_hp_aux_flow` |
| `ochsner/plant/hp/aux_program` | Betriebswahl Zusatzheizung |  | Zahl | `ochsner_plant_hp_aux_program` |
| `ochsner/plant/hp/aux_program_text` | Betriebswahl Zusatzheizung (Text) |  | Text | `ochsner_plant_hp_aux_program_text` |
| `ochsner/plant/hp/aux_status` | Status Zusatzheizung |  | Zahl | `ochsner_plant_hp_aux_status` |
| `ochsner/plant/hp/aux_status_text` | Status Zusatzheizung (Text) |  | Text | `ochsner_plant_hp_aux_status_text` |
| `ochsner/plant/hp/buffer_top` | Puffertemperatur 1 - Top | °C | Zahl | `ochsner_plant_hp_buffer_top` |
| `ochsner/plant/hp/capability` | heatPumpModeCapability |  | Zahl | `ochsner_plant_hp_capability` |
| `ochsner/plant/hp/cop` | COP aktuell (Wärme/Strom) |  | Zahl | `ochsner_plant_hp_cop` |
| `ochsner/plant/hp/cycles_today` | Schaltzyklen heute |  | Zahl | `ochsner_plant_hp_cycles_today` |
| `ochsner/plant/hp/cycles_total` | Schaltzyklen |  | Zahl | `ochsner_plant_hp_cycles_total` |
| `ochsner/plant/hp/defrosts_today` | erfolgreiche Abtauungen heute |  | Zahl | `ochsner_plant_hp_defrosts_today` |
| `ochsner/plant/hp/defrosts_total` | erfolgreiche Abtauungen |  | Zahl | `ochsner_plant_hp_defrosts_total` |
| `ochsner/plant/hp/dhw_valve` | Umlenkventil Warmwasser |  | Zahl | `ochsner_plant_hp_dhw_valve` |
| `ochsner/plant/hp/el_power` | elektr. Verdichterleistung | kW | Zahl | `ochsner_plant_hp_el_power` |
| `ochsner/plant/hp/emergency_status` | Status Notbetrieb Wärmepumpe |  | Zahl | `ochsner_plant_hp_emergency_status` |
| `ochsner/plant/hp/emergency_status_text` | Status Notbetrieb Wärmepumpe (Text) |  | Text | `ochsner_plant_hp_emergency_status_text` |
| `ochsner/plant/hp/energy_el_prev_year` | Strombedarf gesamt Vorjahr | kWh | Zahl | `ochsner_plant_hp_energy_el_prev_year` |
| `ochsner/plant/hp/energy_el_year` | Strombedarf gesamt aktuelles Jahr | kWh | Zahl | `ochsner_plant_hp_energy_el_year` |
| `ochsner/plant/hp/energy_heat_prev_year` | Wärmeenergie gesamt Vorjahr | kWh | Zahl | `ochsner_plant_hp_energy_heat_prev_year` |
| `ochsner/plant/hp/energy_heat_total` | Heizenergie | kWh | Zahl | `ochsner_plant_hp_energy_heat_total` |
| `ochsner/plant/hp/energy_heat_year` | Wärmeenergie gesamt aktuelles Jahr | kWh | Zahl | `ochsner_plant_hp_energy_heat_year` |
| `ochsner/plant/hp/flow` | Wärmepumpe Vorlauftemperatur | °C | Zahl | `ochsner_plant_hp_flow` |
| `ochsner/plant/hp/flow_rate` | Volumenstrom Wärmenutzung | m³/h | Zahl | `ochsner_plant_hp_flow_rate` |
| `ochsner/plant/hp/heat_output` | Heizleistung | kW | Zahl | `ochsner_plant_hp_heat_output` |
| `ochsner/plant/hp/hours_total` | Betriebsstunden | h | Zahl | `ochsner_plant_hp_hours_total` |
| `ochsner/plant/hp/jaz_prev_year` | JAZ gesamt Vorjahr |  | Zahl | `ochsner_plant_hp_jaz_prev_year` |
| `ochsner/plant/hp/jaz_year` | JAZ gesamt aktuelles Jahr |  | Zahl | `ochsner_plant_hp_jaz_year` |
| `ochsner/plant/hp/outdoor` | Außentemperatur | °C | Zahl | `ochsner_plant_hp_outdoor` |
| `ochsner/plant/hp/outdoor_avg` | Gemittelte Außentemperatur (H/K-Grenze) | °C | Zahl | `ochsner_plant_hp_outdoor_avg` |
| `ochsner/plant/hp/pressure` | Anlagendruck Wärmenutzung | bar | Zahl | `ochsner_plant_hp_pressure` |
| `ochsner/plant/hp/program` | Betriebswahl Wärmepumpe |  | Zahl | `ochsner_plant_hp_program` |
| `ochsner/plant/hp/program_text` | Betriebswahl Wärmepumpe (Text) |  | Text | `ochsner_plant_hp_program_text` |
| `ochsner/plant/hp/return` | Wärmepumpe Rücklauftemperatur | °C | Zahl | `ochsner_plant_hp_return` |
| `ochsner/plant/hp/silent_program` | Betriebswahl Silentmode |  | Zahl | `ochsner_plant_hp_silent_program` |
| `ochsner/plant/hp/silent_program_text` | Betriebswahl Silentmode (Text) |  | Text | `ochsner_plant_hp_silent_program_text` |
| `ochsner/plant/hp/status` | Status Wärmepumpe |  | Zahl | `ochsner_plant_hp_status` |
| `ochsner/plant/hp/status_text` | Status Wärmepumpe (Text) |  | Text | `ochsner_plant_hp_status_text` |
| `ochsner/plant/hp/sum_fault` | Summenstörung Wärmepumpe |  | Zahl | `ochsner_plant_hp_sum_fault` |
| `ochsner/plant/hp/sum_fault_text` | Summenstörung Wärmepumpe (Text) |  | Text | `ochsner_plant_hp_sum_fault_text` |
| `ochsner/plant/hp/system_status` | Status Anlage |  | Zahl | `ochsner_plant_hp_system_status` |
| `ochsner/plant/hp/system_status_text` | Status Anlage (Text) |  | Text | `ochsner_plant_hp_system_status_text` |

## Warmwasser

| Topic | Bedeutung | Einheit | Typ | Virtueller Eingang |
|---|---|---|---|---|
| `ochsner/plant/dhw/boost` | Boost-Ladung |  | Zahl | `ochsner_plant_dhw_boost` |
| `ochsner/plant/dhw/boost_text` | Boost-Ladung (Text) |  | Text | `ochsner_plant_dhw_boost_text` |
| `ochsner/plant/dhw/comfort_eco` | Warmwasser Komfort/Eco (1 Eco, 2 Komfort) |  | Zahl | `ochsner_plant_dhw_comfort_eco` |
| `ochsner/plant/dhw/comfort_eco_text` | Warmwasser Komfort/Eco (1 Eco, 2 Komfort) (Text) |  | Text | `ochsner_plant_dhw_comfort_eco_text` |
| `ochsner/plant/dhw/emergency_status` | Status Notbetrieb Warmwasser |  | Zahl | `ochsner_plant_dhw_emergency_status` |
| `ochsner/plant/dhw/emergency_status_text` | Status Notbetrieb Warmwasser (Text) |  | Text | `ochsner_plant_dhw_emergency_status_text` |
| `ochsner/plant/dhw/mode` | Betriebsart (comfort/eco/off/boost) |  | Text | `ochsner_plant_dhw_mode` |
| `ochsner/plant/dhw/offset` | Warmwasser-Korrektur | K | Zahl | `ochsner_plant_dhw_offset` |
| `ochsner/plant/dhw/program` | Betriebswahl Warmwasser |  | Zahl | `ochsner_plant_dhw_program` |
| `ochsner/plant/dhw/program_text` | Betriebswahl Warmwasser (Text) |  | Text | `ochsner_plant_dhw_program_text` |
| `ochsner/plant/dhw/setpoint_boost` | Sollwert Boost | °C | Zahl | `ochsner_plant_dhw_setpoint_boost` |
| `ochsner/plant/dhw/setpoint_comfort` | Sollwert Komfort | °C | Zahl | `ochsner_plant_dhw_setpoint_comfort` |
| `ochsner/plant/dhw/setpoint_eco` | Sollwert Eco | °C | Zahl | `ochsner_plant_dhw_setpoint_eco` |
| `ochsner/plant/dhw/setpoint_reduced` | Sollwert Reduziert | °C | Zahl | `ochsner_plant_dhw_setpoint_reduced` |
| `ochsner/plant/dhw/status` | Status Warmwasser |  | Zahl | `ochsner_plant_dhw_status` |
| `ochsner/plant/dhw/target` | Sollwert Warmwassertemperatur | °C | Zahl | `ochsner_plant_dhw_target` |
| `ochsner/plant/dhw/target_active` | Warmwasser-Soll der aktiven Betriebsart |  | Zahl | `ochsner_plant_dhw_target_active` |
| `ochsner/plant/dhw/temp` | Warmwassertemperatur | °C | Zahl | `ochsner_plant_dhw_temp` |

## Heizkreise

Je Heizkreis dieselben Topics unter `ochsner/plant/hc<n>/…` (n = 1–4). Beispiel Heizkreis 1
(Fußboden); die Topics für Raumtemperatur und Feuchte gibt es nur mit Raumfühler.

| Topic | Bedeutung | Einheit | Typ | Virtueller Eingang |
|---|---|---|---|---|
| `ochsner/plant/hc1/badge` | Status-Symbol |  | Zahl | `ochsner_plant_hc1_badge` |
| `ochsner/plant/hc1/comfort_eco` | Komfort/Eco (0 Komfort, 1 Eco) |  | Zahl | `ochsner_plant_hc1_comfort_eco` |
| `ochsner/plant/hc1/comfort_eco_text` | Komfort/Eco (0 Komfort, 1 Eco) (Text) |  | Text | `ochsner_plant_hc1_comfort_eco_text` |
| `ochsner/plant/hc1/cool_curve_base_flow` | Vorlauftemperatur bei Fußpunkt | °C | Zahl | `ochsner_plant_hc1_cool_curve_base_flow` |
| `ochsner/plant/hc1/cool_curve_base_outdoor` | Fußpunkt Außentemperatur | °C | Zahl | `ochsner_plant_hc1_cool_curve_base_outdoor` |
| `ochsner/plant/hc1/cool_curve_norm_flow` | Vorlauftemperatur bei Norm-Außentemperatur | °C | Zahl | `ochsner_plant_hc1_cool_curve_norm_flow` |
| `ochsner/plant/hc1/cool_curve_norm_outdoor` | Kühlkurve Norm-Außentemperatur | °C | Zahl | `ochsner_plant_hc1_cool_curve_norm_outdoor` |
| `ochsner/plant/hc1/cool_curve_ref_room` | Kühlkurve Bezugsraumtemperatur | °C | Zahl | `ochsner_plant_hc1_cool_curve_ref_room` |
| `ochsner/plant/hc1/cool_limit` | Kühlgrenze | °C | Zahl | `ochsner_plant_hc1_cool_limit` |
| `ochsner/plant/hc1/cool_limit_status` | Status Kühlgrenze |  | Zahl | `ochsner_plant_hc1_cool_limit_status` |
| `ochsner/plant/hc1/cooling` | Kühlt gerade (0/1) |  | Zahl | `ochsner_plant_hc1_cooling` |
| `ochsner/plant/hc1/dew_point` | Taupunkttemperatur | °C | Zahl | `ochsner_plant_hc1_dew_point` |
| `ochsner/plant/hc1/flow_actual` | Heizkreis Vorlauftemperatur | °C | Zahl | `ochsner_plant_hc1_flow_actual` |
| `ochsner/plant/hc1/flow_target` | Heizkreis Sollvorlauftemperatur | °C | Zahl | `ochsner_plant_hc1_flow_target` |
| `ochsner/plant/hc1/heat_curve_base_flow` | Heizkurve Fußpunkt Vorlauf | °C | Zahl | `ochsner_plant_hc1_heat_curve_base_flow` |
| `ochsner/plant/hc1/heat_curve_base_outdoor` | Heizkurve Fußpunkt Außentemperatur | °C | Zahl | `ochsner_plant_hc1_heat_curve_base_outdoor` |
| `ochsner/plant/hc1/heat_curve_max_flow` | Heizkurve max. Vorlauf | °C | Zahl | `ochsner_plant_hc1_heat_curve_max_flow` |
| `ochsner/plant/hc1/heat_curve_norm_flow` | Heizkurve Norm-Vorlauf | °C | Zahl | `ochsner_plant_hc1_heat_curve_norm_flow` |
| `ochsner/plant/hc1/heat_curve_norm_outdoor` | Heizkurve Norm-Außentemperatur | °C | Zahl | `ochsner_plant_hc1_heat_curve_norm_outdoor` |
| `ochsner/plant/hc1/heat_curve_ref_room` | Heizkurve Bezugsraumtemperatur | °C | Zahl | `ochsner_plant_hc1_heat_curve_ref_room` |
| `ochsner/plant/hc1/heat_limit` | Heizgrenze | °C | Zahl | `ochsner_plant_hc1_heat_limit` |
| `ochsner/plant/hc1/heat_limit_status` | Status Heizgrenze |  | Zahl | `ochsner_plant_hc1_heat_limit_status` |
| `ochsner/plant/hc1/heat_limit_status_text` | Status Heizgrenze (Text) |  | Text | `ochsner_plant_hc1_heat_limit_status_text` |
| `ochsner/plant/hc1/heating` | Heizt gerade (0/1) |  | Zahl | `ochsner_plant_hc1_heating` |
| `ochsner/plant/hc1/humidity` | Relative Luftfeuchtigkeit | % | Zahl | `ochsner_plant_hc1_humidity` |
| `ochsner/plant/hc1/mixer` | Mischer Heizkreis | % | Zahl | `ochsner_plant_hc1_mixer` |
| `ochsner/plant/hc1/mode` | Modus (heat/cool/heat_cool/off) |  | Text | `ochsner_plant_hc1_mode` |
| `ochsner/plant/hc1/name` | Name Heizkreis 1 |  | Text | `ochsner_plant_hc1_name` |
| `ochsner/plant/hc1/op_program` | Betriebswahl Heizkreis |  | Zahl | `ochsner_plant_hc1_op_program` |
| `ochsner/plant/hc1/op_program_present` | Betriebswahl wirksam |  | Zahl | `ochsner_plant_hc1_op_program_present` |
| `ochsner/plant/hc1/op_program_present_text` | Betriebswahl wirksam (Text) |  | Text | `ochsner_plant_hc1_op_program_present_text` |
| `ochsner/plant/hc1/op_program_text` | Betriebswahl Heizkreis (Text) |  | Text | `ochsner_plant_hc1_op_program_text` |
| `ochsner/plant/hc1/party_hours` | Party-Dauer | h | Zahl | `ochsner_plant_hc1_party_hours` |
| `ochsner/plant/hc1/party_on` | Party aktiv |  | Zahl | `ochsner_plant_hc1_party_on` |
| `ochsner/plant/hc1/party_temp` | Party-Raumsoll | °C | Zahl | `ochsner_plant_hc1_party_temp` |
| `ochsner/plant/hc1/preset` | Betriebsart (comfort/eco/off) |  | Text | `ochsner_plant_hc1_preset` |
| `ochsner/plant/hc1/pump` | Heizkreispumpe |  | Zahl | `ochsner_plant_hc1_pump` |
| `ochsner/plant/hc1/pump_text` | Heizkreispumpe (Text) |  | Text | `ochsner_plant_hc1_pump_text` |
| `ochsner/plant/hc1/room_offset` | Raumsoll-Korrektur | K | Zahl | `ochsner_plant_hc1_room_offset` |
| `ochsner/plant/hc1/room_target` | Raumsoll aktuell |  | Zahl | `ochsner_plant_hc1_room_target` |
| `ochsner/plant/hc1/room_target_cool` | Sollwert Raum Kühlen | °C | Zahl | `ochsner_plant_hc1_room_target_cool` |
| `ochsner/plant/hc1/room_target_current` | Aktueller Raumsollwert Heizkreis 1 | ° | Zahl | `ochsner_plant_hc1_room_target_current` |
| `ochsner/plant/hc1/room_target_heat` | Sollwert Raum Heizen | °C | Zahl | `ochsner_plant_hc1_room_target_heat` |
| `ochsner/plant/hc1/room_temp` | Raumtemperatur | °C | Zahl | `ochsner_plant_hc1_room_temp` |
| `ochsner/plant/hc1/season` | Sommer-/Winterumschaltung Heizkreis |  | Zahl | `ochsner_plant_hc1_season` |
| `ochsner/plant/hc1/season_text` | Sommer-/Winterumschaltung Heizkreis (Text) |  | Text | `ochsner_plant_hc1_season_text` |
| `ochsner/plant/hc1/setpoint_frost_room` | Sollwert Frostschutz Raumtemperatur | °C | Zahl | `ochsner_plant_hc1_setpoint_frost_room` |
| `ochsner/plant/hc1/setpoint_manual` | Sollwert Handbetrieb | °C | Zahl | `ochsner_plant_hc1_setpoint_manual` |
| `ochsner/plant/hc1/setpoint_normal_cool` | Raumsollwert Normal Kühlen | °C | Zahl | `ochsner_plant_hc1_setpoint_normal_cool` |
| `ochsner/plant/hc1/setpoint_normal_heat` | Raumsollwert Normal Heizen | °C | Zahl | `ochsner_plant_hc1_setpoint_normal_heat` |
| `ochsner/plant/hc1/setpoint_reduced_cool` | Raumsollwert Reduziert Kühlen | °C | Zahl | `ochsner_plant_hc1_setpoint_reduced_cool` |
| `ochsner/plant/hc1/setpoint_reduced_heat` | Raumsollwert Reduziert Heizen | °C | Zahl | `ochsner_plant_hc1_setpoint_reduced_heat` |
| `ochsner/plant/hc1/status` | Status Heizkreis 1 |  | Zahl | `ochsner_plant_hc1_status` |
| `ochsner/plant/hc1/status_text` | Status Heizkreis 1 (Text) |  | Text | `ochsner_plant_hc1_status_text` |
| `ochsner/plant/hc1/target_selector` | Aktiver Zielwert |  | Zahl | `ochsner_plant_hc1_target_selector` |
| `ochsner/plant/hc1/target_selector_text` | Aktiver Zielwert (Text) |  | Text | `ochsner_plant_hc1_target_selector_text` |

## Rohwerte aller Katalogpunkte

Zusätzlich (abschaltbar unter *Konfiguration → Rohpunkte senden*) jeder erkannte Katalogpunkt unter
`ochsner/<punkt>`, z. B. `ochsner/gemittelte_aussentemperatur_h_k_grenze`. Die Liste mit Namen, Topic und Objektadresse zeigt der
Reiter **Alle Werte**. Für Loxone sind die `plant/…`-Topics oben gedacht; die Rohwerte eher für Node-RED o. Ä.

## Befehle

Befehle gehen an `ochsner/cmd/<befehl>` – aus Loxone per **virtuellem Ausgang** an `/dev/udp/<loxberry>/11884`
mit dem Befehl `publish ochsner/cmd/<befehl> <wert>`. Schreiben muss in der Konfiguration erlaubt sein.
Gespeicherte (retained) Befehle führt das Plugin nie aus.

| Befehl | Werte | Wirkung |
|---|---|---|
| `ochsner/cmd/hp/program` | auto · off | Wärmepumpe Automatik / abschalten |
| `ochsner/cmd/hc<n>/preset` | comfort · eco · off | Heizkreis Komfort / Eco / Aus |
| `ochsner/cmd/hc<n>/mode` | heat · cool · heat_cool · off | Heizen / Kühlen / Automatik (nur mit Kühlung) |
| `ochsner/cmd/hc<n>/room_target` | z. B. 21.5 | Raumsoll über die ±3-K-Korrektur (wie die App) |
| `ochsner/cmd/hc<n>/setpoint_normal_heat` | z. B. 21.5 | Raumsollwert Normal Heizen |
| `ochsner/cmd/hc<n>/setpoint_reduced_heat` | z. B. 19 | Raumsollwert Nacht/Eco Heizen |
| `ochsner/cmd/hc<n>/room_offset` | -3 … 3 (Schritt 0.5) | Temporäre Korrektur |
| `ochsner/cmd/hc<n>/heat_limit` | z. B. 16.5 | Heizgrenze |
| `ochsner/cmd/dhw/mode` | comfort · eco · off · boost | Warmwasser-Betriebsart |
| `ochsner/cmd/dhw/target` | z. B. 50 | Warmwasser-Soll der aktiven Betriebsart |
| `ochsner/cmd/dhw/boost` | 1 | Einmalige Warmwasser-Ladung |
| `ochsner/cmd/poll` | 1 | Sofort abfragen |

Zusätzlich gibt es `ochsner/set/<punkt> <wert>` für einzelne Katalogpunkte (wie im Experten-Editor).
