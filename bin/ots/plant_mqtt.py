"""Sprechende MQTT-Topics und Befehle für Loxone (über das LoxBerry MQTT Gateway).

Werte:   <basis>/plant/<bereich>/<schlüssel>      z. B. ochsner/plant/hc1/flow_actual
Befehle: <basis>/cmd/<bereich>/<aktion>  <wert>   z. B. ochsner/cmd/hc1/preset  eco

Alle Befehle laufen über dieselbe Logik wie die App (Schreibsequenzen der
Ochsner-App, Grenzwerte, Schreibschutz, Flash-Zähler).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .vendor import plant as P

HC_SETPOINTS = ("setpoint_normal_heat", "setpoint_reduced_heat", "setpoint_normal_cool",
                "setpoint_reduced_cool", "setpoint_frost_room", "setpoint_manual", "room_offset",
                "heat_limit", "heat_curve_max_flow", "cool_limit")
DHW_SETPOINTS = ("setpoint_comfort", "setpoint_eco", "setpoint_reduced", "setpoint_boost")

# Beschreibung der Befehle für die Weboberfläche: (topic-suffix, werte, beschreibung)
COMMANDS: List[Tuple[str, str, str]] = [
    ("hp/program", "auto | off", "Wärmepumpe Automatik / abschalten"),
    ("hc<n>/preset", "comfort | eco | off", "Heizkreis Komfort / Eco / Aus"),
    ("hc<n>/mode", "heat | cool | heat_cool | off", "Heizen / Kühlen / Automatik (nur mit Kühlung)"),
    ("hc<n>/room_target", "z. B. 21.5", "Raumsoll über die ±3-K-Korrektur (wie die App)"),
    ("hc<n>/setpoint_normal_heat", "z. B. 21.5", "Raumsollwert Normal Heizen"),
    ("hc<n>/setpoint_reduced_heat", "z. B. 19", "Raumsollwert Nacht/Eco Heizen"),
    ("hc<n>/room_offset", "-3 … 3 (Schritt 0.5)", "Temporäre Korrektur"),
    ("hc<n>/heat_limit", "z. B. 16.5", "Heizgrenze"),
    ("dhw/mode", "comfort | eco | off | boost", "Warmwasser-Betriebsart"),
    ("dhw/target", "z. B. 50", "Warmwasser-Soll der aktiven Betriebsart"),
    ("dhw/boost", "1", "Einmalige Warmwasser-Ladung"),
    ("poll", "1", "Sofort abfragen"),
]


def role_topic(role: str) -> str:
    section, _, key = role.partition(".")
    return f"plant/{section}/{key}" if key else f"plant/{section}"


def plant_topics(engine: Any) -> Dict[str, Any]:
    """Topic -> Wert für alle Rollen plus abgeleitete Klartexte."""
    out: Dict[str, Any] = {}
    meta = engine.meta()
    vals = engine.d.raw
    for role, m in meta.items():
        if role.startswith("avail.") or role.endswith(".availability"):
            continue
        raw = P.first_value(vals, m["read_id"])
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = P.clean_text(raw)
            if raw is None:
                continue
        out[role_topic(role)] = raw
        labels = m.get("labels") or m.get("options")
        if labels and P.as_int(raw) is not None:
            lab = labels.get(str(P.as_int(raw)))
            if lab:
                out[role_topic(role) + "_text"] = lab
    states = engine.states()
    for c in engine.caps.get("circuits", []):
        n = int(c["index"])
        st = states.get(f"climate.o2m_hc{n}") or {}
        a = st.get("attributes") or {}
        out[f"plant/hc{n}/name"] = engine.circuit_name(n)
        out[f"plant/hc{n}/mode"] = st.get("state")
        out[f"plant/hc{n}/preset"] = "off" if st.get("state") == "off" else (a.get("preset_mode") or "")
        if a.get("temperature") is not None:
            out[f"plant/hc{n}/room_target"] = a["temperature"]
        out[f"plant/hc{n}/heating"] = int(a.get("hvac_action") == "heating")
        out[f"plant/hc{n}/cooling"] = int(a.get("hvac_action") == "cooling")
    if engine.caps.get("dhw"):
        st = states.get("water_heater.o2m_dhw") or {}
        a = st.get("attributes") or {}
        op = st.get("state")
        out["plant/dhw/mode"] = {"performance": "comfort", "high_demand": "boost"}.get(op, op)
        if a.get("temperature") is not None:
            out["plant/dhw/target_active"] = a["temperature"]
    heat = P.as_float(P.first_value(vals, P.HP_ROLES["hp.heat_output"]))
    el = P.as_float(P.first_value(vals, P.HP_ROLES["hp.el_power"]))
    if heat is not None and el and el > 0.05:
        out["plant/hp/cop"] = round(heat / el, 2)
    return out


_DERIVED_NAMES = {
    "name": "Name", "mode": "Modus (heat/cool/heat_cool/off)", "preset": "Betriebsart (comfort/eco/off)",
    "room_target": "Raumsoll aktuell", "heating": "Heizt gerade (0/1)", "cooling": "Kühlt gerade (0/1)",
    "target_active": "Warmwasser-Soll der aktiven Betriebsart", "cop": "COP aktuell (Wärme/Strom)",
}
_SECTION_NAMES = {"hp": "Wärmepumpe", "dhw": "Warmwasser", "pool": "Pool"}


def topic_list(engine: Any) -> List[Dict[str, Any]]:
    """Alle Anlagen-Topics mit Klartext-Beschreibung (für die Loxone-Seite)."""
    meta = engine.meta()
    by_topic = {role_topic(r): m for r, m in meta.items()}
    out = []
    for topic, value in sorted(plant_topics(engine).items()):
        _, section, key = topic.split("/", 2)
        base = key[:-5] if key.endswith("_text") else key
        m = by_topic.get(f"plant/{section}/{base}")
        if section.startswith("hc"):
            area = engine.circuit_name(int(section[2:])) if section[2:].isdigit() else section
        else:
            area = _SECTION_NAMES.get(section, section)
        if m:
            name = m.get("name") or base
            if key.endswith("_text"):
                name += " (Text)"
        elif section == "dhw" and key == "mode":
            name = "Betriebsart (comfort/eco/off/boost)"
        else:
            name = _DERIVED_NAMES.get(key, key)
        out.append({"topic": topic, "area": area, "name": name, "value": value,
                    "unit": (m or {}).get("unit") if not key.endswith("_text") else None})
    return out


def _num(v: str) -> Optional[float]:
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        return None


def parse_command(engine: Any, path: str, payload: str) -> Tuple[str, str, Dict[str, Any]]:
    """MQTT-Befehl -> (domain, service, data) für engine.call_service. ValueError bei Unsinn."""
    parts = [p for p in path.split("/") if p]
    p = payload.strip()
    if len(parts) != 2:
        raise ValueError(f"Unbekannter Befehl '{path}'")
    section, action = parts
    if section == "hp" and action == "program":
        m = engine.meta().get("hp.program")
        if not m or m["domain"] != "select":
            raise ValueError("Wärmepumpen-Programm ist nicht schreibbar")
        raw = {"auto": "0", "automatik": "0", "off": "3", "aus": "3"}.get(p.lower(), p)
        if raw not in m.get("options", {}):
            raise ValueError("Erlaubt: auto | off")
        return "select", "select_option", {"entity_id": m["entity_id"], "option": m["options"][raw]}
    if section.startswith("hc") and section[2:].isdigit():
        n = int(section[2:])
        if engine.circuit(n) is None:
            raise ValueError(f"Heizkreis {n} ist nicht vorhanden")
        climate = f"climate.o2m_hc{n}"
        if action == "preset":
            v = p.lower()
            if v in ("off", "aus", "0"):
                return "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "off"}
            v = {"komfort": "comfort"}.get(v, v)
            if v not in P.PRESET_VALUES:
                raise ValueError("Erlaubt: comfort | eco | off")
            return "climate", "set_preset_mode", {"entity_id": climate, "preset_mode": v}
        if action == "mode":
            v = {"heizen": "heat", "kuehlen": "cool", "auto": "heat_cool", "aus": "off"}.get(p.lower(), p.lower())
            return "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": v}
        if action == "room_target":
            t = _num(p)
            if t is None:
                raise ValueError("Zahl erwartet")
            return "climate", "set_temperature", {"entity_id": climate, "temperature": t}
        if action in HC_SETPOINTS or action.startswith(("heat_curve_", "cool_curve_")):
            m = engine.meta().get(P.hc_key(n, action))
            if not m or m["domain"] != "number":
                raise ValueError(f"{action} ist für Heizkreis {n} nicht schreibbar")
            t = _num(p)
            if t is None:
                raise ValueError("Zahl erwartet")
            return "number", "set_value", {"entity_id": m["entity_id"], "value": t}
    if section == "dhw":
        if not engine.caps.get("dhw"):
            raise ValueError("Kein Warmwasser vorhanden")
        if action == "mode":
            v = {"comfort": "performance", "komfort": "performance", "boost": "high_demand", "aus": "off"}.get(p.lower(), p.lower())
            return "water_heater", "set_operation_mode", {"entity_id": "water_heater.o2m_dhw", "operation_mode": v}
        if action == "target":
            t = _num(p)
            if t is None:
                raise ValueError("Zahl erwartet")
            return "water_heater", "set_temperature", {"entity_id": "water_heater.o2m_dhw", "temperature": t}
        if action == "boost":
            return "button", "press", {"entity_id": "button.o2m_dhw_boost"}
        if action in DHW_SETPOINTS:
            m = engine.meta().get(f"dhw.{action}")
            t = _num(p)
            if not m or m["domain"] != "number" or t is None:
                raise ValueError(f"{action}: nicht schreibbar oder keine Zahl")
            return "number", "set_value", {"entity_id": m["entity_id"], "value": t}
    raise ValueError(f"Unbekannter Befehl '{path}'")
