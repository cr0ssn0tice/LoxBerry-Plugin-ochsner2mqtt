"""Datenpunkt-Katalog und Climatix-Objektadressen (OA).

Der Katalog (data/discovery_catalog.json) stammt aus dem MIT-lizenzierten
Projekt permissionBRICK/OTS-HomeAssistant (siehe data/LICENSE-OTS-HomeAssistant.txt).

Eine OA ist eine 8-Byte-Adresse, Base64-codiert, Little-Endian:
    uint16 object_type | uint16 point_index | uint16 instance_tag | uint16 member_id
(object_id = instance_tag << 16 | point_index, als uint32 LE gepackt)
"""

from __future__ import annotations

import base64
import json
import re
import struct
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Member 4353 einer Enum-OA liefert die Zustandsliste "A*B*C", Index = Zahlenwert.
DESCRIPTOR_MEMBER_ID = 4353

# Anlagenidentität (aus dem Referenzprojekt übernommen)
PLANT_MODEL_OA = "BCP0c9VVAAE="       # Anlagentyp, z. B. AIRHAWK518C11A
PLANT_SERIAL_OA = "BCOOVNVVAAE="      # Seriennummer
PLANT_SW_VERSION_OA = "IAABAAAAAAA="  # Softwareversion, z. B. v3.3.20

# Name, den der Betreiber pro Heizkreis vergeben hat
HC_NAME_OBJECT_TYPE = 8964
HC_NAME_POINT_INDEX = 61003
HC_NAME_MEMBER_ID = 256

_MODULE_LABELS_DE = {
    "global_root_and_protocol_meta": "System",
    "system_service_and_site": "Service & Standort",
    "emergency_mode_dhw": "Notbetrieb Warmwasser",
    "communication_and_controller_firmware": "Kommunikation & Firmware",
    "heating_circuit_1": "Heizkreis 1",
    "heating_circuit_2": "Heizkreis 2",
    "heating_circuit_3": "Heizkreis 3",
    "heating_circuit_4": "Heizkreis 4",
    "plant_identity_and_clock": "Anlage & Uhr",
    "heat_pump_and_heat_generation": "Wärmepumpe & Wärmeerzeugung",
    "energy_management": "Energiemanagement",
    "shared_io_measurements_and_statistics": "Messwerte & Statistik",
    "emergency_mode_heating": "Notbetrieb Heizung",
    "buffer_store_and_external_heat_buffer": "Pufferspeicher",
    "aggregate_heat_cool_demand": "Heiz-/Kühlanforderung",
    "dhw_and_timed_programs": "Warmwasser & Zeitprogramme",
    "pool": "Pool",
    "reference_only": "Sonstiges",
}


@dataclass(frozen=True)
class OA:
    object_type: int
    instance_tag: int
    point_index: int
    member_id: int


def encode_oa(object_type: int, instance_tag: int, point_index: int, member_id: int) -> str:
    for name, v in (("object_type", object_type), ("instance_tag", instance_tag),
                    ("point_index", point_index), ("member_id", member_id)):
        if not 0 <= int(v) <= 0xFFFF:
            raise ValueError(f"{name} außerhalb 0..65535")
    object_id = (int(instance_tag) << 16) | int(point_index)
    return base64.b64encode(struct.pack("<HIH", int(object_type), object_id, int(member_id))).decode("ascii")


def decode_oa(encoded: str) -> OA:
    s = str(encoded)
    padded = s + "=" * (-len(s) % 4)
    raw = base64.b64decode(padded, validate=True)
    if len(raw) != 8:
        raise ValueError("OA muss genau 8 Byte lang sein")
    object_type, object_id, member_id = struct.unpack("<HIH", raw)
    return OA(object_type, object_id >> 16, object_id & 0xFFFF, member_id)


def with_member(encoded: str, member_id: int) -> str:
    oa = decode_oa(encoded)
    return encode_oa(oa.object_type, oa.instance_tag, oa.point_index, member_id)


def descriptor_oa(encoded: str) -> str:
    return with_member(encoded, DESCRIPTOR_MEMBER_ID)


def hc_name_oa(instance_tag: int) -> str:
    return encode_oa(HC_NAME_OBJECT_TYPE, instance_tag, HC_NAME_POINT_INDEX, HC_NAME_MEMBER_ID)


_NORM_STRIP = re.compile(r"[\s_\-]+")


def normalize_token(token: Any) -> str:
    s = str(token or "").strip()
    sign = s[:1] if s[:1] in "+-" else ""
    key = _NORM_STRIP.sub("", s[len(sign):]).lower()
    return sign + key if key else ""


def slugify(text: str) -> str:
    t = str(text or "")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_").lower()
    return t or "punkt"


@dataclass
class Point:
    id: str
    name: str
    name_en: str
    platform: str
    unit: Optional[str] = None
    module: str = "reference_only"
    hc: Optional[int] = None          # Heizkreis-Nummer 1..4
    write_id: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: Dict[str, int] = field(default_factory=dict)       # Label -> Wert
    value_map: Dict[str, str] = field(default_factory=dict)     # Wert -> Label
    enum_labels: Dict[str, str] = field(default_factory=dict)   # Token -> Label (DE)
    on_value: Optional[int] = None
    off_value: Optional[int] = None
    technical: bool = False
    diagnostic: bool = False
    enabled_default: bool = True
    slug: str = ""

    @property
    def writable(self) -> bool:
        return bool(self.write_id) and self.platform in ("number", "select", "switch", "text")

    @property
    def enum_shaped(self) -> bool:
        return self.platform == "select" or bool(self.options) or bool(self.value_map) or bool(self.enum_labels)

    @property
    def module_label(self) -> str:
        return _MODULE_LABELS_DE.get(self.module, self.module)


class Catalog:
    def __init__(self, raw: Dict[str, Any]) -> None:
        if int(raw.get("schema_version", 0)) != 1:
            raise ValueError("Katalog: unbekannte schema_version")
        self.version: str = str(raw.get("catalog_version") or "")
        self.source: str = str(raw.get("app_source") or "")
        self.token_labels_de: Dict[str, str] = {
            normalize_token(k): v for k, v in ((raw.get("enum_token_labels") or {}).get("de") or {}).items()
        }
        tag_to_module: Dict[int, str] = {}
        for t in raw.get("tags") or []:
            try:
                tag_to_module[int(t["tag"])] = str(t["module"])
            except (KeyError, TypeError, ValueError):
                continue
        self.hc_tag_to_number: Dict[int, int] = {}
        for tag, module in tag_to_module.items():
            m = re.fullmatch(r"heating_circuit_(\d)", module)
            if m:
                self.hc_tag_to_number[tag] = int(m.group(1))

        self.points: List[Point] = []
        for rec in raw.get("points") or []:
            pid = str(rec.get("id") or "")
            try:
                oa = decode_oa(pid)
            except Exception:  # noqa: BLE001
                continue
            module = tag_to_module.get(oa.instance_tag, "reference_only")
            hc = self.hc_tag_to_number.get(oa.instance_tag)
            if hc is None and rec.get("hc_tag") is not None:
                hc = self.hc_tag_to_number.get(int(rec["hc_tag"]))
            labels = rec.get("enum_labels_de") or {}
            self.points.append(Point(
                id=pid,
                name=str(rec.get("name_de") or rec.get("name") or pid),
                name_en=str(rec.get("name_en") or rec.get("name") or pid),
                platform=str(rec.get("platform") or "sensor"),
                unit=rec.get("unit"),
                module=module,
                hc=hc,
                write_id=rec.get("write_id"),
                min=_f(rec.get("min")),
                max=_f(rec.get("max")),
                step=_f(rec.get("step")),
                options={str(k): int(v) for k, v in (rec.get("options") or {}).items() if _is_int(v)},
                value_map={str(k): str(v) for k, v in (rec.get("value_map") or {}).items()},
                enum_labels={normalize_token(k): str(v) for k, v in labels.items()},
                on_value=rec.get("on_value"),
                off_value=rec.get("off_value"),
                technical=bool(rec.get("technical")),
                diagnostic=bool(rec.get("diagnostic")),
                enabled_default=rec.get("enabled_default", True) is not False,
            ))
        # Zweite Rückfallebene: Token-Beschriftungen aller Punkte zusammengeführt
        self.merged_point_labels: Dict[str, str] = {}
        for p in self.points:
            for k, v in p.enum_labels.items():
                self.merged_point_labels.setdefault(k, v)
        self._assign_slugs()
        self.by_id: Dict[str, Point] = {p.id: p for p in self.points}
        self.by_slug: Dict[str, Point] = {p.slug: p for p in self.points}

    def _assign_slugs(self) -> None:
        base: Dict[str, List[Point]] = {}
        for p in sorted(self.points, key=lambda x: x.id):
            s = slugify(p.name)
            if p.hc and not re.search(r"heizkreis_?%d" % p.hc, s):
                s = f"{s}_hk{p.hc}"
            base.setdefault(s, []).append(p)
        for s, group in base.items():
            if len(group) == 1:
                group[0].slug = s
                continue
            for p in group:
                oa = decode_oa(p.id)
                p.slug = f"{s}_{oa.instance_tag:04x}{oa.point_index:04x}"

    def label_for_token(self, point: Point, token: str) -> str:
        key = normalize_token(token)
        if key in point.enum_labels:
            return point.enum_labels[key]
        if key in self.token_labels_de:
            return self.token_labels_de[key]
        if key in self.merged_point_labels:
            return self.merged_point_labels[key]
        return str(token)


def _f(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _is_int(v: Any) -> bool:
    try:
        int(v)
        return True
    except (TypeError, ValueError):
        return False


def load_catalog(path: Optional[Path] = None) -> Catalog:
    p = path or Path(__file__).resolve().parent.parent / "data" / "discovery_catalog.json"
    with open(p, "r", encoding="utf-8") as fh:
        return Catalog(json.load(fh))
