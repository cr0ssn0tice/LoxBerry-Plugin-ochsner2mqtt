"""Rohwerte deuten: Zahlen, Enums (über den Regler-Deskriptor) und Alarmzustände."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .catalog import Catalog, Point, normalize_token

# Tokens aus Enum-Deskriptoren, die einen aktiven Fehler/Alarm bedeuten.
ACTIVE_TOKENS = {"almon", "eron", "lockon", "error", "fault", "flt", "alarm", "nok"}
# Tokens, die ausdrücklich "kein Fehler" bedeuten.
INACTIVE_TOKENS = {"almof", "erof", "lockof", "infof", "infon", "ok", "null", "passive", "off", "none"}

_ALARM_NAME = re.compile(r"(st(ö|oe)rung|alarm|störabschaltung|fehler|\bnok\b)", re.IGNORECASE)
_NOT_ALARM_NAME = re.compile(r"(quittieren|meldung.*verz|verz(ö|oe)gerung|zähler|anzahl|historie)", re.IGNORECASE)


def is_alarm_point(p: Point) -> bool:
    if p.platform not in ("sensor", "select"):
        return False
    if p.writable and p.platform == "select" and "quittier" in p.name.lower():
        return False
    text = f"{p.name} {p.name_en}"
    return bool(_ALARM_NAME.search(text)) and not _NOT_ALARM_NAME.search(text)


def to_number(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def interpret(cat: Catalog, p: Point, raw: Any, tokens: Optional[List[str]]) -> Dict[str, Any]:
    """Liefert {'value': num|str|None, 'text': str|None, 'token': str|None}."""
    num = to_number(raw)
    out: Dict[str, Any] = {"value": None, "text": None, "token": None}

    if p.platform == "text":
        out["value"] = "" if raw is None else str(raw)
        out["text"] = out["value"]
        return out

    if num is not None and float(num).is_integer() and (p.enum_shaped or tokens):
        idx = int(num)
        out["value"] = idx
        if tokens and 0 <= idx < len(tokens):
            out["token"] = tokens[idx]
            out["text"] = cat.label_for_token(p, tokens[idx])
        elif str(idx) in p.value_map:
            out["text"] = p.value_map[str(idx)]
        else:
            inv = {v: k for k, v in p.options.items()}
            if idx in inv:
                out["text"] = inv[idx]
        return out

    if num is not None:
        out["value"] = round(num, 3)
        if p.platform == "switch" and p.on_value is not None:
            out["text"] = "Ein" if int(num) == int(p.on_value) else "Aus"
        return out

    # Nicht numerisch: als Text durchreichen
    out["value"] = None if raw is None else str(raw)
    out["text"] = out["value"]
    return out


def alarm_state(p: Point, interp: Dict[str, Any]) -> Optional[bool]:
    """True = aktiv, False = inaktiv, None = nicht bestimmbar."""
    tok = interp.get("token")
    if tok:
        key = normalize_token(tok)
        if key in ACTIVE_TOKENS:
            return True
        if key in INACTIVE_TOKENS:
            return False
    text = (interp.get("text") or "").strip().lower()
    if text:
        if text.endswith(" ein") or text in ("ein", "aktiv", "störung", "alarm"):
            return True
        if text.endswith(" aus") or text in ("aus", "inaktiv", "ok", "keine störung"):
            return False
    v = interp.get("value")
    if isinstance(v, (int, float)):
        return v != 0
    return None


def parse_descriptor(raw: Any) -> Optional[List[str]]:
    if isinstance(raw, str) and "*" in raw:
        return raw.split("*")
    return None


def coerce_write_value(cat: Catalog, p: Point, value: Any, tokens: Optional[List[str]]) -> Tuple[Any, str]:
    """Prüft einen Schreibwunsch gegen Katalog-Grenzen. Gibt (wert, beschreibung) zurück
    oder wirft ValueError mit deutscher Begründung."""
    s = str(value).strip()
    if p.platform == "number":
        num = to_number(s)
        if num is None:
            raise ValueError(f"'{s}' ist keine Zahl")
        if p.min is not None and num < p.min:
            raise ValueError(f"{num} liegt unter dem Minimum {p.min}")
        if p.max is not None and num > p.max:
            raise ValueError(f"{num} liegt über dem Maximum {p.max}")
        if p.step:
            snapped = round(round(num / p.step) * p.step, 6)
            if abs(snapped - num) > 1e-6:
                raise ValueError(f"{num} passt nicht zur Schrittweite {p.step}")
            num = snapped
        return (int(num) if float(num).is_integer() else num), f"{num:g}{(' ' + p.unit) if p.unit else ''}"

    if p.platform == "switch":
        on = int(p.on_value if p.on_value is not None else 1)
        off = int(p.off_value if p.off_value is not None else 0)
        low = s.lower()
        if low in ("1", "on", "ein", "true", "an", str(on)):
            return on, "Ein"
        if low in ("0", "off", "aus", "false", str(off)):
            return off, "Aus"
        raise ValueError(f"'{s}' ist kein gültiger Schaltwert (0/1, ein/aus)")

    if p.platform == "select":
        choices: Dict[int, str] = {}
        if tokens:
            choices = {i: cat.label_for_token(p, t) for i, t in enumerate(tokens) if str(t).strip() not in ("", "-")}
        elif p.options:
            choices = {v: k for k, v in p.options.items()}
        elif p.value_map:
            choices = {int(k): v for k, v in p.value_map.items() if k.lstrip("-").isdigit()}
        if not choices:
            raise ValueError("Für diesen Punkt sind keine Auswahlwerte bekannt")
        num = to_number(s)
        if num is not None and float(num).is_integer() and int(num) in choices:
            return int(num), choices[int(num)]
        for k, lab in choices.items():
            if lab.lower() == s.lower():
                return k, lab
        raise ValueError(f"'{s}' ist keine gültige Auswahl ({', '.join(f'{k}={v}' for k, v in sorted(choices.items()))})")

    if p.platform == "text":
        if not 1 <= len(s) <= 20 or not re.fullmatch(r"[\w .,()/+-]+", s):
            raise ValueError("Text muss 1–20 Zeichen lang sein (Buchstaben, Ziffern, Leerzeichen, .,()/+-)")
        return s, s

    raise ValueError("Dieser Punkt ist nicht beschreibbar")
