"""PlantEngine: die Anlagensicht der Ochsner-App auf dem LoxBerry.

Baut aus den Rohwerten des Reglers dieselben Daten, die das Dashboard der
HA-Integration erwartet (``plants``-Payload, Live-Event, Entity-States), und
führt dessen Aktionen (Service-Aufrufe) mit den Schreibsequenzen der
Ochsner-App aus. Die Anlagenlogik stammt aus ``ots.vendor.plant`` (MIT).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .vendor import catalog as VC
from .vendor import plant as P
from .vendor import schedule as S

log = logging.getLogger("ochsner2mqtt.engine")

PLANT_ID = "o2m"
SETTLE_SECONDS = 8.0           # Regler rechnet Zielwerte nach einer Änderung neu
SCHEDULE_CACHE_SECONDS = 60.0

# Welche Rollen die App schreiben darf (alles andere bleibt lesend, auch wenn
# der Katalog einen Schreibpunkt kennt).
_WRITABLE_NUMBER = re.compile(
    r"^(hc\d\.(setpoint_\w+|heat_curve_\w+|cool_curve_\w+|heat_limit|cool_limit|room_offset|party_temp|party_hours)"
    r"|dhw\.(setpoint_\w+|offset)|pool\.setpoint)$"
)
_WRITABLE_SELECT = re.compile(r"^(hp\.(program|silent_program|aux_program)|hc\d\.(comfort_eco|op_program|season)|dhw\.comfort_eco|pool\.mode)$")
_WRITABLE_TEXT = re.compile(r"^hc\d\.name$")

# Ergänzungspunkte (nicht schreibbar im Katalog, aber von der App benutzt)
_SUPPLEMENT_NUMBERS = {"room_offset": (-P.OFFSET_LIMIT, P.OFFSET_LIMIT, P.OFFSET_STEP, "K"),
                       "dhw.offset": (-P.DHW_OFFSET_LIMIT, P.DHW_OFFSET_LIMIT, P.DHW_OFFSET_STEP, "K")}
_SUPPLEMENT_SELECTS = {"comfort_eco": "comfort_eco", "dhw.comfort_eco": "dhw.comfort_eco"}

_DHW_DEFAULT_BOUNDS = {
    "dhw.setpoint_comfort": (5.0, 75.0), "dhw.setpoint_eco": (5.0, 75.0),
    "dhw.setpoint_reduced": (5.0, 75.0), "dhw.setpoint_boost": (40.0, 75.0),
}

# Deutsche Namen für Rollen, deren Katalogname technisch oder mehrdeutig ist
ROLE_NAMES_DE = {
    "comfort_eco": "Komfort/Eco (0 Komfort, 1 Eco)", "op_program_present": "Betriebswahl wirksam",
    "badge": "Status-Symbol", "room_offset": "Raumsoll-Korrektur", "target_selector": "Aktiver Zielwert",
    "party_on": "Party aktiv", "party_hours": "Party-Dauer", "party_temp": "Party-Raumsoll",
    "heat_curve_norm_outdoor": "Heizkurve Norm-Außentemperatur", "cool_curve_norm_outdoor": "Kühlkurve Norm-Außentemperatur",
    "heat_curve_base_outdoor": "Heizkurve Fußpunkt Außentemperatur", "heat_curve_base_flow": "Heizkurve Fußpunkt Vorlauf",
    "heat_curve_norm_flow": "Heizkurve Norm-Vorlauf", "heat_curve_max_flow": "Heizkurve max. Vorlauf",
    "dhw.comfort_eco": "Warmwasser Komfort/Eco (1 Eco, 2 Komfort)", "dhw.offset": "Warmwasser-Korrektur",
}

# Rollen, deren Verlauf aufgezeichnet wird (Energie-Ansicht, Detaildialog)
HISTORY_ROLES = ("hp.heat_output", "hp.el_power", "hp.status", "hp.outdoor", "hp.flow", "hp.return",
                 "hp.buffer_top", "dhw.temp", "hp.flow_rate")


class WriteRejected(Exception):
    """Ein Schreibwunsch wurde abgelehnt (Begründung im Text, deutsch)."""


def _short_key(role: str) -> str:
    return role.split(".", 1)[1] if role.startswith("hc") and "." in role else role


def entity_id(domain: str, role: str) -> str:
    return f"{domain}.o2m_{role.replace('.', '_')}"


def pretty_model(model: Optional[str]) -> str:
    m = str(model or "").strip()
    mm = re.match(r"^AIR\s*([A-Z]+?)\s*(\d+)", m.upper())
    if mm:
        return f"Air{mm.group(1).capitalize()} {mm.group(2)}"
    return m or "Ochsner"


def _fmt_state(v: Any) -> str:
    if v is None:
        return "unknown"
    if isinstance(v, float):
        return f"{v:.6g}" if not v.is_integer() else str(int(v))
    return str(v)


# ============================================================================ Verlauf
class Recorder:
    """Kleiner Verlaufsspeicher (wie der HA-Recorder, nur für wenige Entities)."""

    def __init__(self, path: Path, keep_hours: int = 48) -> None:
        self.path = path
        self.keep = keep_hours * 3600
        self.data: Dict[str, List[List[Any]]] = {}
        self._dirty = False
        self._saved_at = time.time()
        self._lock = threading.Lock()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                self.data = {k: v for k, v in raw.items() if isinstance(v, list)}
        except (OSError, ValueError):
            pass

    def record(self, eid: str, value: Any, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        s = None if value is None else _fmt_state(value)
        with self._lock:
            rows = self.data.setdefault(eid, [])
            if rows and rows[-1][1] == s:
                return
            rows.append([round(ts, 1), s])
            cutoff = ts - self.keep
            while len(rows) > 2 and rows[1][0] < cutoff:
                rows.pop(0)
            self._dirty = True

    def query(self, eids: Iterable[str], start: float, end: float) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        with self._lock:
            for eid in eids:
                rows = self.data.get(eid) or []
                res: List[Dict[str, Any]] = []
                before = None
                for ts, s in rows:
                    if ts < start:
                        before = s
                        continue
                    if ts > end:
                        break
                    res.append({"s": s if s is not None else "unknown", "lu": ts})
                if before is not None:
                    res.insert(0, {"s": before, "lu": start})
                if res:
                    out[eid] = res
        return out

    def maybe_save(self, force: bool = False) -> None:
        if not self._dirty or (not force and time.time() - self._saved_at < 600):
            return
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, separators=(",", ":"))
                os.replace(tmp, self.path)
                self._dirty = False
                self._saved_at = time.time()
            except OSError as exc:
                log.warning("Verlauf konnte nicht gespeichert werden: %s", exc)


# ============================================================================ Engine
class PlantEngine:
    def __init__(self, daemon: Any) -> None:
        self.d = daemon
        self.vcat = VC.load_catalog()
        self.lang = "de"
        self.caps: Dict[str, Any] = P.compute_capabilities({})
        self.recorder = Recorder(daemon.paths.data_dir / "history.json")
        self.schedule_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self.section_written: Dict[str, float] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._meta_sig: Any = None

    # ------------------------------------------------------------------ Werte
    def _values(self) -> Dict[str, Any]:
        return self.d.raw

    def _get(self, oid: Optional[str]) -> Any:
        return P.first_value(self._values(), oid) if oid else None

    def poll_ids(self) -> List[str]:
        ids = set(P.capability_ids())
        ids.update(P.role_ids(self.caps).values())
        ids.update(P.energy_supplement_ids())
        return sorted(ids)

    def update_caps(self) -> bool:
        """Fähigkeiten aus den aktuellen Werten; True, wenn sich die Struktur änderte."""
        new = self._apply_overrides(P.compute_capabilities(self._values()))
        changed = P.section_signature(new) != P.section_signature(self.caps)
        self.caps = new
        if changed:
            self._meta_sig = None
        return changed

    def buffer_sensor(self) -> Optional[float]:
        """Pufferfühler (oben), wenn er einen plausiblen Wert liefert."""
        v = self._get(P.HP_ROLES["hp.buffer_top"])
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if -20.0 < f < 95.0 else None

    def _apply_overrides(self, caps: Dict[str, Any]) -> Dict[str, Any]:
        """o2m: Puffer im Schema. Die Ochsner-App zeigt ihn nur, wenn er im Regler als
        Pufferspeicher konfiguriert ist. Viele Anlagen haben aber einen (Trenn-)Puffer
        mit Fühler, der anders eingebunden ist. "auto": Konfiguration, externer
        Puffer oder plausibler Pufferfühler; "show"/"hide": fest."""
        mode = str(self.d.cfg.get("schema_buffer", "auto")).lower()
        sensor = self.buffer_sensor()
        caps["buffer_source"] = "config" if caps.get("buffer") else None
        if mode == "hide":
            caps["buffer"] = False
            caps["buffer_source"] = "hidden"
        elif mode == "show":
            if not caps.get("buffer"):
                caps["buffer_source"] = "manual"
            caps["buffer"] = True
            caps["buffer_temp"] = bool(caps.get("buffer_temp")) or sensor is not None
        elif not caps.get("buffer") and not caps.get("pool"):
            ext = P.first_value(self._values(), P.AVAIL_ROLES["avail.ext_buffer"])
            try:
                ext_on = float(ext) > 0
            except (TypeError, ValueError):
                ext_on = False
            if ext_on or sensor is not None:
                caps["buffer"] = True
                caps["buffer_temp"] = sensor is not None
                caps["buffer_source"] = "external" if ext_on else "sensor"
        return caps

    def role_ids(self) -> Dict[str, str]:
        return P.role_ids(self.caps)

    def circuit_ids(self, n: int) -> Dict[str, str]:
        prefix = f"hc{n}."
        return {role[len(prefix):]: oid for role, oid in P.circuit_role_ids(n).items()}

    def circuit(self, n: int) -> Optional[Dict[str, Any]]:
        return next((c for c in self.caps.get("circuits", []) if int(c["index"]) == int(n)), None)

    # ------------------------------------------------------------------ Rollen-Metadaten
    def _catalog_rec(self, oid: str) -> Optional[Dict[str, Any]]:
        return self.vcat.points_by_id.get(P.canonical_id(oid))

    def _labels(self, role: str, oid: str, rec: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
        labels = P.builtin_labels(role, self.lang)
        if labels:
            return labels
        tokens = self.d.tokens.get(P.canonical_id(oid))
        if not (tokens or (rec and (rec.get("value_map") or rec.get("options") or rec.get("platform") == "select"))):
            return None
        return P.catalog_labels(rec, self.lang, self.vcat.enum_token_labels, tokens)

    def meta(self) -> Dict[str, Dict[str, Any]]:
        sig = (P.section_signature(self.caps), len(self.d.tokens))
        if self._meta_sig == sig:
            return self._meta
        out: Dict[str, Dict[str, Any]] = {}
        for role, oid in self.role_ids().items():
            rec = self._catalog_rec(oid)
            short = _short_key(role)
            name = ROLE_NAMES_DE.get(short) or ROLE_NAMES_DE.get(role) or (rec or {}).get("name_de") or role
            m: Dict[str, Any] = {"role": role, "read_id": oid, "write_id": None, "domain": "sensor", "name": name}
            unit = (rec or {}).get("unit") or P.role_unit(role)
            if unit:
                m["unit"] = unit
            cat_writable = bool(rec and rec.get("write_id") and rec.get("platform") in ("number", "select", "switch", "text"))
            if _WRITABLE_NUMBER.match(role) and (cat_writable or short in _SUPPLEMENT_NUMBERS or role in _SUPPLEMENT_NUMBERS):
                m["domain"] = "number"
                m["write_id"] = (rec or {}).get("write_id") or oid
                sup = _SUPPLEMENT_NUMBERS.get(short) or _SUPPLEMENT_NUMBERS.get(role)
                if cat_writable and rec:
                    lo = rec.get("min", rec.get("bundle_min"))
                    hi = rec.get("max", rec.get("bundle_max"))
                    m.update(min=lo, max=hi, step=rec.get("step"))
                elif sup:
                    m.update(min=sup[0], max=sup[1], step=sup[2], unit=sup[3])
                if role in _DHW_DEFAULT_BOUNDS:
                    dlo, dhi = _DHW_DEFAULT_BOUNDS[role]
                    m["min"] = m.get("min") if m.get("min") is not None else dlo
                    m["max"] = m.get("max") if m.get("max") is not None else dhi
            elif _WRITABLE_SELECT.match(role) and (cat_writable or short in _SUPPLEMENT_SELECTS or role in _SUPPLEMENT_SELECTS):
                m["domain"] = "select"
                m["write_id"] = (rec or {}).get("write_id") or oid
            elif _WRITABLE_TEXT.match(role) and cat_writable:
                m["domain"] = "text"
                m["write_id"] = rec.get("write_id") if rec else oid
            labels = self._labels(role, oid, rec)
            if labels:
                m["labels"] = labels
            if m["domain"] == "select":
                opts = labels or {}
                if not opts and rec and rec.get("options"):
                    opts = {str(v): k for k, v in rec["options"].items()}
                m["options"] = {str(k): str(v) for k, v in opts.items()}
            m["entity_id"] = entity_id(m["domain"], role)
            out[role] = m
        self._meta = out
        self._meta_sig = sig
        return out

    def meta_by_entity(self) -> Dict[str, Dict[str, Any]]:
        return {m["entity_id"]: m for m in self.meta().values()}

    # ------------------------------------------------------------------ Payloads (wie HA-Websocket)
    def circuit_name(self, n: int) -> str:
        return P.clean_text(self._get(P.circuit_role_ids(n).get(P.hc_key(n, "name")))) or P.default_circuit_name(n, self.lang)

    def plants_payload(self) -> Dict[str, Any]:
        identity = self.d.discovered.get("identity", {}) if isinstance(self.d.discovered, dict) else {}
        model = identity.get("model") or "Climatix"
        roles = {}
        for role, m in self.meta().items():
            r: Dict[str, Any] = {"entity_id": m["entity_id"]}
            for k in ("unit", "labels", "options"):
                if m.get(k):
                    r[k] = m[k]
            if m["domain"] != "sensor":
                r["writable"] = True
                for k in ("min", "max", "step"):
                    if m.get(k) is not None:
                        r[k] = m[k]
            roles[role] = r
        circuits = []
        for c in self.caps.get("circuits", []):
            n = int(c["index"])
            circuits.append({"index": n, "name": self.circuit_name(n), "device_id": None,
                             "heat": bool(c["heat"]), "cool": bool(c["cool"]),
                             "room_sensor": bool(c["room_sensor"]), "humidity": bool(c["humidity"]),
                             "climate": f"climate.o2m_hc{n}"})
        dhw = {"water_heater": "water_heater.o2m_dhw", "boost_button": "button.o2m_dhw_boost"} if self.caps.get("dhw") else None
        return {
            "version": 1,
            "settings": {"color_scheme": "ochsner"},
            "plants": [{
                "plant_id": PLANT_ID, "entry_id": PLANT_ID, "host": self.d.cfg.get("host"),
                "device_id": PLANT_ID, "title": pretty_model(model), "model": model,
                "available": bool(self.d.status.get("connected")),
                "capabilities": P.public_capabilities(self.caps),
                "circuits": circuits, "dhw": dhw, "badges": list(P.BADGES),
                "roles": roles, "flash_writes": "sensor.o2m_flash_writes",
            }],
        }

    def event(self) -> Dict[str, Any]:
        return {
            "plant_id": PLANT_ID,
            "available": bool(self.d.status.get("connected")),
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "capabilities": P.public_capabilities(self.caps),
            "values": P.role_values(self._values(), self.role_ids()),
        }

    # ------------------------------------------------------------------ States (wie hass.states)
    def states(self) -> Dict[str, Dict[str, Any]]:
        ok = bool(self.d.status.get("connected"))
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        st: Dict[str, Dict[str, Any]] = {}

        def put(eid: str, state: str, attrs: Dict[str, Any]) -> None:
            st[eid] = {"entity_id": eid, "state": state if ok else "unavailable", "attributes": attrs, "last_updated": now}

        for role, m in self.meta().items():
            raw = self._get(m["read_id"])
            attrs: Dict[str, Any] = {"friendly_name": m["name"]}
            if m.get("unit"):
                attrs["unit_of_measurement"] = m["unit"]
            if m["domain"] == "number":
                attrs.update({k: m[k] for k in ("min", "max", "step") if m.get(k) is not None})
                put(m["entity_id"], _fmt_state(P.as_float(raw) if P.as_float(raw) is not None else raw), attrs)
            elif m["domain"] == "select":
                attrs["options"] = list(m.get("options", {}).values())
                iv = P.as_int(raw)
                put(m["entity_id"], m.get("options", {}).get(str(iv), _fmt_state(raw)), attrs)
            elif m.get("labels") and P.as_int(raw) is not None:
                put(m["entity_id"], m["labels"].get(str(P.as_int(raw)), _fmt_state(raw)), attrs)
            else:
                v = P.clean_text(raw) if isinstance(raw, str) else raw
                put(m["entity_id"], _fmt_state(v), attrs)

        for c in self.caps.get("circuits", []):
            n = int(c["index"])
            ids = self.circuit_ids(n)
            g = lambda k: P.first_value(self._values(), ids.get(k))  # noqa: E731
            mode = P.hvac_mode(g("op_program"), g("season"), bool(c["heat"]), bool(c["cool"]))
            target = P.circuit_target(self._values(), ids)
            bounds = P.offset_bounds(target, P.as_float(g("room_offset")))
            attrs = {
                "friendly_name": self.circuit_name(n),
                "hvac_modes": P.hvac_modes(bool(c["heat"]), bool(c["cool"])),
                "preset_modes": list(P.PRESET_VALUES), "preset_mode": P.preset_mode(g("comfort_eco")),
                "hvac_action": P.hvac_action_from_badge(g("badge")),
                "temperature": target, "target_temp_step": P.OFFSET_STEP,
                "min_temp": bounds[0] if bounds else 7, "max_temp": bounds[1] if bounds else 35,
                "current_temperature": P.as_float(g("room_temp")) if c["room_sensor"] else None,
                "current_humidity": P.as_float(g("humidity")) if c["humidity"] else None,
                "room_offset": P.as_float(g("room_offset")),
                "flow_temperature": P.as_float(g("flow_actual")), "flow_target": P.as_float(g("flow_target")),
            }
            put(f"climate.o2m_hc{n}", mode or "unknown", attrs)

        if self.caps.get("dhw"):
            op = P.dhw_operation(self._values())
            sp_role = P.dhw_setpoint_role(op)
            lo, hi = self._dhw_bounds(sp_role)
            put("water_heater.o2m_dhw", op or "unknown", {
                "friendly_name": "Warmwasser", "operation_list": list(P.DHW_OPERATIONS), "operation_mode": op,
                "temperature": P.as_float(self._get(P.DHW_ROLES[sp_role])),
                "current_temperature": P.as_float(self._get(P.DHW_ROLES["dhw.temp"])),
                "min_temp": lo, "max_temp": hi, "target_temp_step": 0.5,
                "offset": P.as_float(self._get(P.DHW_ROLES["dhw.offset"])),
                "effective_target": P.as_float(self._get(P.DHW_ROLES["dhw.target"])),
            })
            put("button.o2m_dhw_boost", "unknown", {"friendly_name": "Warmwasser Boost"})
        put("sensor.o2m_flash_writes", str(int(self.d.flash.get("total", 0))),
            {"friendly_name": "Schreibzugriffe Regler", "today": self.d.flash.get("today", 0)})
        return st

    def _dhw_bounds(self, role: str) -> Tuple[float, float]:
        m = self.meta().get(role, {})
        dlo, dhi = _DHW_DEFAULT_BOUNDS.get(role, (5.0, 75.0))
        lo = m.get("min") if m.get("min") is not None else dlo
        hi = m.get("max") if m.get("max") is not None else dhi
        return float(lo), float(hi)

    # ------------------------------------------------------------------ Verlauf
    def record_history(self) -> None:
        if not self.d.status.get("connected"):
            return
        meta = self.meta()
        ts = time.time()
        for role in HISTORY_ROLES:
            m = meta.get(role)
            if m:
                self.recorder.record(m["entity_id"], self._get(m["read_id"]), ts)
        self.recorder.maybe_save()

    def history(self, entity_ids: List[str], start: float, end: float) -> Dict[str, Any]:
        return self.recorder.query(entity_ids, start, end)

    # ------------------------------------------------------------------ Schreiben
    def write_planned(self, plan: Callable[[Dict[str, Any]], List[Tuple[str, Any]]], reads: Iterable[str],
                      source: str, section: Optional[str] = None, settle: bool = False) -> List[Tuple[str, Any]]:
        """Liest die Entscheidungsgrundlage frisch, plant, schreibt gezählt, liest Abhängige nach."""
        d = self.d
        if d.client is None:
            raise WriteRejected("Kein Regler konfiguriert")
        if settle and section:
            wait = SETTLE_SECONDS - (time.time() - self.section_written.get(section, 0.0))
            if wait > 0:
                time.sleep(wait)
        with d.lock:
            reads = [r for r in reads if r]
            fresh_raw, _ = d.client.read_raw(reads)
            fresh = {P.canonical_id(k): v for k, v in fresh_raw.items()}
            try:
                writes = list(plan(fresh))
            except P.UnknownValueError as exc:
                raise WriteRejected(f"Wert unbekannt ({exc}) – nichts geschrieben") from None
            except ValueError as exc:
                raise WriteRejected(str(exc)) from None
            if not writes:
                return []
            d.guard_writes(len(writes), source)
            for oid, value in writes:
                if isinstance(value, float):
                    value = int(value) if value.is_integer() else round(value, 6)
                d.controller_write(oid, value, source)
            if section:
                self.section_written[section] = time.time()
            time.sleep(0.4)
            reread = set()
            for oid, _ in writes:
                reread.add(oid)
                reread.update(P.write_dependents(oid))
            try:
                vals, _ = d.client.read_raw(sorted(reread))
                for k, v in vals.items():
                    d.raw[P.canonical_id(k)] = v
            except Exception as exc:  # noqa: BLE001
                log.info("Nachlesen nach Schreiben fehlgeschlagen: %s", exc)
        d.after_engine_write()
        return writes

    def call_service(self, domain: str, service: str, data: Dict[str, Any], source: str = "app") -> Dict[str, Any]:
        eid = str(data.get("entity_id") or "")
        if not eid.startswith(domain + "."):
            raise WriteRejected(f"Entity {eid} passt nicht zu {domain}")
        if domain == "climate":
            m = re.fullmatch(r"climate\.o2m_hc(\d)", eid)
            c = self.circuit(int(m.group(1))) if m else None
            if not c:
                raise WriteRejected("Unbekannter Heizkreis")
            return self._climate(int(c["index"]), c, service, data, source)
        if domain == "water_heater":
            if eid != "water_heater.o2m_dhw" or not self.caps.get("dhw"):
                raise WriteRejected("Kein Warmwasser vorhanden")
            return self._water_heater(service, data, source)
        if domain == "button":
            if eid != "button.o2m_dhw_boost" or service != "press" or not self.caps.get("dhw"):
                raise WriteRejected("Unbekannte Taste")
            w = self.write_planned(P.plan_dhw_boost, P.dhw_mode_input_ids(), source, "dhw")
            return {"writes": len(w)}
        m = self.meta_by_entity().get(eid)
        if not m or m["domain"] != domain:
            raise WriteRejected(f"{eid} ist nicht beschreibbar")
        rid, wid = m["read_id"], m["write_id"]
        section = P.write_section(rid)
        if domain == "number" and service == "set_value":
            v = P.as_float(data.get("value"))
            if v is None:
                raise WriteRejected("Kein gültiger Zahlenwert")
            if m.get("min") is not None and v < float(m["min"]) - 1e-6:
                raise WriteRejected(f"{m['name']}: {v:g} liegt unter dem Minimum {m['min']}")
            if m.get("max") is not None and v > float(m["max"]) + 1e-6:
                raise WriteRejected(f"{m['name']}: {v:g} liegt über dem Maximum {m['max']}")
            if m.get("step"):
                step = float(m["step"])
                v = round(round(v / step) * step, 6)
            target = v

            def plan(vals: Dict[str, Any]) -> List[Tuple[str, Any]]:
                cur = P.as_float(P.first_value(vals, rid))
                return [] if cur is not None and abs(cur - target) < 1e-6 else [(wid, target)]
            w = self.write_planned(plan, [rid], source, section)
            return {"writes": len(w)}
        if domain == "select" and service == "select_option":
            opt = str(data.get("option"))
            raw = next((int(k) for k, lab in m.get("options", {}).items() if lab == opt or k == opt), None)
            if raw is None:
                raise WriteRejected(f"Ungültige Auswahl '{opt}'")

            def plan(vals: Dict[str, Any]) -> List[Tuple[str, Any]]:
                return [] if P.as_int(P.first_value(vals, rid)) == raw else [(wid, raw)]
            w = self.write_planned(plan, [rid], source, section)
            return {"writes": len(w)}
        if domain == "text" and service == "set_value":
            txt = str(data.get("value") or "").strip()
            if not 1 <= len(txt) <= 20:
                raise WriteRejected("Name muss 1–20 Zeichen lang sein")
            w = self.write_planned(lambda vals: [] if P.clean_text(P.first_value(vals, rid)) == txt else [(wid, txt)],
                                   [rid], source, section)
            return {"writes": len(w)}
        raise WriteRejected(f"Dienst {domain}.{service} wird nicht unterstützt")

    def _climate(self, n: int, c: Dict[str, Any], service: str, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        ids = self.circuit_ids(n)
        cool = bool(c["cool"])
        section = f"hc{n}"
        if service == "set_preset_mode":
            preset = str(data.get("preset_mode"))
            if preset not in P.PRESET_VALUES:
                raise WriteRejected(f"Unbekannte Betriebsart {preset}")
            w = self.write_planned(lambda v: P.plan_preset(preset, v, ids), P.mode_input_ids(ids), source, section)
        elif service in ("set_hvac_mode", "turn_off", "turn_on"):
            if service == "turn_on":
                w = self.write_planned(lambda v: P.plan_turn_on(v, ids), P.mode_input_ids(ids), source, section)
            else:
                mode = P.HVAC_OFF if service == "turn_off" else str(data.get("hvac_mode"))
                if mode not in P.hvac_modes(bool(c["heat"]), cool):
                    raise WriteRejected(f"Modus {mode} wird von diesem Heizkreis nicht unterstützt")
                w = self.write_planned(lambda v: P.plan_hvac_mode(mode, v, ids, cool), P.mode_input_ids(ids), source, section)
        elif service == "set_temperature":
            t = P.as_float(data.get("temperature"))
            if t is None:
                raise WriteRejected("Keine Temperatur angegeben")
            w = self.write_planned(lambda v: P.plan_temperature(t, v, ids), P.temperature_input_ids(ids),
                                   source, section, settle=True)
        else:
            raise WriteRejected(f"Dienst climate.{service} wird nicht unterstützt")
        return {"writes": len(w)}

    def _water_heater(self, service: str, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        if service == "set_operation_mode":
            op = str(data.get("operation_mode"))
            if op not in P.DHW_OPERATIONS:
                raise WriteRejected(f"Unbekannte Warmwasser-Betriebsart {op}")
            w = self.write_planned(lambda v: P.plan_dhw_operation(op, v), P.dhw_mode_input_ids(), source, "dhw")
        elif service == "turn_on":
            w = self.write_planned(P.plan_dhw_on, P.dhw_mode_input_ids(), source, "dhw")
        elif service == "turn_off":
            w = self.write_planned(lambda v: P.plan_dhw_operation(P.DHW_OFF, v), P.dhw_mode_input_ids(), source, "dhw")
        elif service == "set_temperature":
            req = P.as_float(data.get("temperature"))
            if req is None:
                raise WriteRejected("Keine Temperatur angegeben")

            def plan(values: Dict[str, Any]) -> List[Tuple[str, Any]]:
                op = P.dhw_operation(values)
                if op is None:
                    raise P.UnknownValueError("dhw_operation_unknown", "Warmwasser-Betriebsart unbekannt")
                role = P.dhw_setpoint_role(op)
                lo, hi = self._dhw_bounds(role)
                value = P.clamp(P.round_half(req), lo, hi)
                oid = P.DHW_ROLES[role]
                cur = P.as_float(P.first_value(values, oid))
                return [] if cur is not None and abs(cur - value) < 1e-6 else [(oid, value)]
            w = self.write_planned(plan, P.dhw_setpoint_input_ids(), source, "dhw")
        else:
            raise WriteRejected(f"Dienst water_heater.{service} wird nicht unterstützt")
        return {"writes": len(w)}

    # ------------------------------------------------------------------ Zeitprogramme
    def present_circuits(self) -> List[int]:
        return [] if self.caps.get("bms") else [int(c["index"]) for c in self.caps.get("circuits", [])]

    def read_schedules(self, force: bool = False) -> Dict[str, Any]:
        d = self.d
        out = []
        if d.client is None:
            raise WriteRejected("Kein Regler konfiguriert")
        for n in self.present_circuits():
            hit = self.schedule_cache.get(n)
            if hit and not force and time.time() - hit[0] < SCHEDULE_CACHE_SECONDS:
                prog = hit[1]
            else:
                try:
                    with d.lock:
                        vals, _ = d.client.read_raw(S.circuit_ids(n))
                except Exception as exc:  # noqa: BLE001
                    log.info("Zeitprogramm HK%d nicht lesbar: %s", n, exc)
                    continue
                prog = S.parse_circuit({P.canonical_id(k): v for k, v in vals.items()}, n)
                self.schedule_cache[n] = (time.time(), prog)
            out.append({**prog, "writable": bool(d.cfg.get("writes_enabled"))})
        return {"plant_id": PLANT_ID, "circuits": out}

    def write_schedule(self, n: int, days_in: Dict[Any, Any], source: str = "app") -> Dict[str, Any]:
        if n not in self.present_circuits():
            raise WriteRejected("Unbekannter Heizkreis")
        days: Dict[int, List[Tuple[int, int]]] = {}
        if isinstance(days_in, list):  # {"0": …} kann unterwegs zu einer Liste werden
            days_in = {i: v for i, v in enumerate(days_in) if v is not None}
        try:
            for key, points in (days_in or {}).items():
                day = int(key)
                if not 0 <= day <= 6:
                    raise ValueError("Tag muss 0 (Montag) … 6 (Sonntag) sein")
                days[day] = S.validate_points(points)
        except (TypeError, ValueError) as exc:
            raise WriteRejected(str(exc)) from None
        if not days:
            raise WriteRejected("Kein Tag angegeben")
        ids = S.circuit_ids(n, sorted(days))

        def plan(fresh: Dict[str, Any]) -> List[Tuple[str, Any]]:
            return [w for day in sorted(days) for w in S.plan_day(fresh, n, day, days[day])]
        try:
            writes = self.write_planned(plan, ids, source, f"hc{n}")
        finally:
            self.schedule_cache.pop(n, None)
        prog = self.read_schedules(force=True)
        for p in prog["circuits"]:
            if int(p["index"]) == n:
                return {**p, "writes": len(writes)}
        raise WriteRejected("Zeitprogramm konnte nicht zurückgelesen werden")
