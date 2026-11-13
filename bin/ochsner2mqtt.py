#!/usr/bin/env python3
"""ochsner2mqtt – Ochsner OTS (Siemens Climatix) lokal auslesen, als App darstellen
und per MQTT an den Loxone Miniserver weitergeben.

Läuft als Daemon auf dem LoxBerry (Benutzer loxberry):
  1. Katalog-Scan (nur lesend): welche bekannten Datenpunkte liefert die Anlage?
  2. Zyklisches Lesen von Katalogpunkten und Anlagenrollen (wie die Ochsner-App).
  3. MQTT: Rohpunkte (<basis>/<slug>), Anlagenrollen (<basis>/plant/...), Störungen.
  4. Lokale API für die Weboberfläche (Dashboard wie die HA-Integration).
  5. Schreiben nur freigeschaltet, mit Grenzwerten, Tageslimit und Flash-Zähler.

LoxBerry-Anbindung (ots/lbsdk.py): Protokoll über LBLog (Logmanager, Protokollstufe
aus der Pluginverwaltung), Benachrichtigungen bei Störungen, MQTT-Zugang über
loxberry.io.mqtt_connectiondetails.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import re
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ots.catalog import (  # noqa: E402
    PLANT_MODEL_OA, PLANT_SERIAL_OA, PLANT_SW_VERSION_OA, Catalog, Point,
    descriptor_oa, hc_name_oa, load_catalog, normalize_token,
)
from ots.climatix import ClimatixAuthError, ClimatixClient, ClimatixError  # noqa: E402
from ots import lbsdk  # noqa: E402
from ots.engine import PlantEngine, WriteRejected  # noqa: E402
from ots.lbsdk import OK  # noqa: E402
from ots.plant_mqtt import parse_command, plant_topics  # noqa: E402
from ots.values import (  # noqa: E402
    ACTIVE_TOKENS, alarm_state, coerce_write_value, interpret, is_alarm_point,
    parse_descriptor,
)
from ots.vendor import plant as P  # noqa: E402

VERSION = "0.4.0"
log = logging.getLogger("ochsner2mqtt")

DEFAULT_CONFIG: Dict[str, Any] = {
    "host": "",
    "port": 80,
    "username": "",
    "password": "",
    "pin": "",
    "poll_interval": 30,
    "mqtt_enabled": True,
    "mqtt_topic": "ochsner",
    "publish_mode": "changes",       # changes | all
    "full_refresh_min": 10,
    "include_technical": False,
    "publish_raw_points": True,      # <basis>/<slug> für alle Katalogpunkte
    "writes_enabled": False,
    "write_min_interval_sec": 120,   # je Punkt, nur für MQTT-Befehle (Automationen)
    "write_max_per_day": 100,
    "api_port": 18765,
    "schema_buffer": "auto",         # auto | show | hide (Pufferspeicher im Anlagenschema)
    "notify_alarms": True,           # LoxBerry-Benachrichtigung bei Störung der Wärmepumpe
    "notify_connection": True,       # … und wenn der Regler länger nicht erreichbar ist
}
# Die Protokollstufe stellt LoxBerry ein (CUSTOM_LOGLEVELS) – kein eigener Konfigurationswert mehr.
CONN_LOST_NOTIFY_SEC = 15 * 60


# ============================================================================ Pfade
class Paths:
    def __init__(self, args: argparse.Namespace) -> None:
        here = Path(__file__).resolve().parent
        installed = "/bin/plugins/" in str(here)
        folder = here.name if installed else "ochsner2mqtt"
        self.folder = folder
        lbhome = Path(str(here).split("/bin/plugins/")[0]) if installed else None
        self.lbhome = Path(args.lbhome) if args.lbhome else lbhome

        def pick(arg: Optional[str], sub: str) -> Path:
            if arg:
                return Path(arg)
            if self.lbhome is None:
                return here / "_local" / sub.split("/")[0]
            return self.lbhome / sub / folder
        self.config_dir = pick(args.config_dir, "config/plugins")
        self.data_dir = pick(args.data_dir, "data/plugins")
        self.log_dir = pick(args.log_dir, "log/plugins")
        self.config_file = self.config_dir / "ochsner2mqtt.json"
        self.discovery_file = self.data_dir / "discovered.json"
        self.state_file = self.data_dir / "state.json"
        self.alarm_history_file = self.data_dir / "alarm_history.json"
        self.alarm_state_file = self.data_dir / "alarm_state.json"
        self.flash_file = self.data_dir / "flash_counter.json"
        self.write_log_file = self.data_dir / "write_log.json"
        self.cmd_dir = self.data_dir / "cmd"
        self.cmd_results_file = self.data_dir / "cmd_results.json"
        self.rescan_flag = self.data_dir / "rescan.flag"
        self.api_token_file = self.data_dir / "api_token"
        self.api_info_file = self.data_dir / "api.json"
        self.general_json = (Path(args.general_json) if args.general_json
                             else (self.lbhome / "config/system/general.json" if self.lbhome else None))
        tpl = self.lbhome / "templates/plugins" / folder if self.lbhome else None
        self.template_dir = tpl if tpl is not None and tpl.is_dir() else here.parent / "templates"
        for d in (self.config_dir, self.data_dir, self.log_dir, self.cmd_dir):
            d.mkdir(parents=True, exist_ok=True)


# ============================================================================ Helfer
def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        log.warning("Kann %s nicht lesen: %s", path.name, exc)
        return default


def write_json(path: Path, data: Any, mode: int = 0o644) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _paho_version() -> Optional[str]:
    try:
        import paho.mqtt as pm
        return getattr(pm, "__version__", None)
    except Exception:  # noqa: BLE001
        return None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def local_timezone() -> str:
    try:
        tz = Path("/etc/timezone").read_text().strip()
        if tz:
            return tz
    except OSError:
        pass
    try:
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return ""


def load_config(paths: Paths) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    user = read_json(paths.config_file, {})
    if isinstance(user, dict):
        for k, v in user.items():
            if k in DEFAULT_CONFIG:
                d = DEFAULT_CONFIG[k]
                try:
                    if isinstance(d, bool):
                        v = str(v).lower() in ("1", "true", "on", "yes")
                    elif isinstance(d, int):
                        v = int(float(v))
                    else:
                        v = "" if v is None else str(v)
                except (TypeError, ValueError):
                    v = d
                cfg[k] = v
    cfg["poll_interval"] = max(10, cfg["poll_interval"])
    cfg["write_min_interval_sec"] = max(10, cfg["write_min_interval_sec"])
    cfg["write_max_per_day"] = max(0, min(cfg["write_max_per_day"], 1000))
    cfg["api_port"] = cfg["api_port"] if 1024 <= cfg["api_port"] <= 65535 else 18765
    if cfg["schema_buffer"] not in ("auto", "show", "hide"):
        cfg["schema_buffer"] = "auto"
    topic = re.sub(r"[^A-Za-z0-9_\-/]", "", cfg["mqtt_topic"]).strip("/")
    cfg["mqtt_topic"] = topic or "ochsner"
    return cfg


# ============================================================================ MQTT
class Mqtt:
    def __init__(self, cred: Dict[str, Any], base: str, inbox: "queue.Queue[tuple]") -> None:
        import paho.mqtt.client as mqtt  # python3-paho-mqtt (1.5 bis 2.x)
        cid = f"ochsner2mqtt-{os.getpid()}"
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
        else:
            self.client = mqtt.Client(client_id=cid)
        self.base = base
        self.inbox = inbox
        self.connected = False
        if cred.get("user") or cred.get("password"):
            self.client.username_pw_set(cred.get("user") or "", cred.get("password") or "")
        if cred.get("tls"):
            import ssl
            if cred.get("tls_verify") and cred.get("cafile") and os.path.isfile(cred["cafile"]):
                self.client.tls_set(ca_certs=cred["cafile"])
            else:
                self.client.tls_set(cert_reqs=ssl.CERT_NONE)
                self.client.tls_insecure_set(True)
        self.client.will_set(f"{base}/status", "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=2, max_delay=60)
        self.client.connect_async(cred["host"], int(cred["port"]), keepalive=60)
        self.client.loop_start()

    @staticmethod
    def _failed(rc: Any) -> bool:
        if hasattr(rc, "is_failure"):
            return bool(rc.is_failure)
        return rc != 0

    def _on_connect(self, client, _userdata, _flags, rc, *args) -> None:  # noqa: ANN001
        if not self._failed(rc):
            self.connected = True
            client.subscribe(f"{self.base}/set/+", qos=1)
            client.subscribe(f"{self.base}/cmd/#", qos=1)
            client.publish(f"{self.base}/status", "online", qos=1, retain=True)
            self.inbox.put(("_connected", "", ""))
            log.log(OK, "MQTT verbunden, Basis-Topic '%s'", self.base)
        else:
            log.warning("MQTT-Verbindung abgelehnt (rc=%s)", rc)

    def _on_disconnect(self, _client, _userdata, *args) -> None:  # noqa: ANN001
        # paho 1.x: (rc) – paho 2.x: (flags, reason_code, properties)
        self.connected = False
        rc = args[1] if len(args) >= 2 else (args[0] if args else 0)
        if self._failed(rc):
            log.warning("MQTT getrennt (rc=%s), verbinde neu …", rc)

    def _on_message(self, _client, _userdata, msg) -> None:  # noqa: ANN001
        if msg.retain:
            return  # gespeicherte Altbefehle niemals ausführen
        topic = msg.topic[len(self.base) + 1:]
        payload = msg.payload.decode("utf-8", "replace").strip()
        kind, _, name = topic.partition("/")
        self.inbox.put((kind, name, payload))

    def publish(self, sub: str, value: Any, retain: bool = True) -> None:
        if not self.connected:
            return
        if isinstance(value, bool):
            value = int(value)
        if value is None:
            value = ""
        if isinstance(value, float):
            value = f"{value:.6g}"
        self.client.publish(f"{self.base}/{sub}", str(value), qos=0, retain=retain)

    def stop(self) -> None:
        try:
            if self.connected:
                self.client.publish(f"{self.base}/status", "offline", qos=1, retain=True).wait_for_publish(2)
        except Exception:  # noqa: BLE001
            pass
        self.client.loop_stop()
        self.client.disconnect()


# ============================================================================ Daemon
class Daemon:
    def __init__(self, paths: Paths, dlog: Optional[lbsdk.DaemonLog] = None) -> None:
        self.paths = paths
        self.dlog = dlog or lbsdk.DaemonLog(paths.folder, paths.log_dir, "Ochsner OTS")
        self.catalog: Catalog = load_catalog()
        self.cfg = load_config(paths)
        self.cfg_mtime = self._cfg_mtime()
        self.texts = lbsdk.Texts(paths.template_dir, paths.general_json)
        self.conn_lost_since: Optional[float] = None
        self.conn_lost_notified = False
        self.lock = threading.RLock()          # Regler-Zugriffe + gemeinsamer Zustand
        self.inbox: "queue.Queue[tuple]" = queue.Queue()
        self.mqtt: Optional[Mqtt] = None
        self.client: Optional[ClimatixClient] = None
        self.running = True
        self.discovered: Dict[str, Any] = {}
        self.raw: Dict[str, Any] = {}               # kanonische OA -> Rohwert
        self.tokens: Dict[str, List[str]] = {}      # kanonische OA -> Enum-Tokens (Deskriptor)
        self.values: Dict[str, Dict[str, Any]] = {}  # Katalog-ID -> Deutung
        self.last_published: Dict[str, Any] = {}
        self.last_full_publish = 0.0
        # Zustand über Neustarts merken: sonst gälte jede aktive Störung nach dem Start als neu
        # (doppelte Verlaufseinträge und Benachrichtigungen)
        self.alarm_active: Dict[str, bool] = {k: bool(v) for k, v in read_json(paths.alarm_state_file, {}).items()}
        self.alarm_history: List[Dict[str, Any]] = read_json(paths.alarm_history_file, [])
        self.flash: Dict[str, Any] = read_json(paths.flash_file, {"total": 0, "day": today(), "today": 0, "per_point": {}})
        self.last_write_at: Dict[str, float] = {}
        self.cmd_results: List[Dict[str, Any]] = read_json(paths.cmd_results_file, [])
        self.status: Dict[str, Any] = {"connected": False, "error": None, "last_poll": None,
                                       "last_ok": None, "poll_ms": None, "requests": 0}
        self.next_poll = 0.0
        self.refresh_requested = False
        self.engine = PlantEngine(self)
        self.api = None
        self.timezone = local_timezone()

    # ------------------------------------------------------------------ Setup
    def _cfg_mtime(self) -> float:
        try:
            return self.paths.config_file.stat().st_mtime
        except OSError:
            return 0.0

    def apply_config(self) -> None:
        c = self.cfg
        with self.lock:
            self.client = ClimatixClient(c["host"], c["port"], c["username"], c["password"], c["pin"]) if c["host"] else None
        if self.mqtt:
            self.mqtt.stop()
            self.mqtt = None
        if c["mqtt_enabled"]:
            cred = lbsdk.mqtt_credentials(self.paths.general_json)
            if cred:
                try:
                    self.mqtt = Mqtt(cred, c["mqtt_topic"], self.inbox)
                except Exception as exc:  # noqa: BLE001
                    log.error("MQTT nicht verfügbar: %s", exc)
            else:
                log.error("Keine MQTT-Zugangsdaten gefunden (MQTT Gateway eingerichtet?) – MQTT deaktiviert")
        self.write_subscription_file()
        self.last_published.clear()
        self.next_poll = 0.0
        log.info("Konfiguration aktiv: Regler %s, Intervall %ss, Schreiben %s",
                 c["host"] or "(nicht gesetzt)", c["poll_interval"],
                 "erlaubt" if c["writes_enabled"] else "gesperrt")

    def start_api(self) -> None:
        from ots.api import ApiServer, load_or_create_token
        if self.api is not None:
            return
        try:
            token = load_or_create_token(self.paths.api_token_file)
            self.api = ApiServer(self, self.cfg["api_port"], token)
            self.api.start()
            self.write_api_info()
        except OSError as exc:
            log.error("Lokale API konnte nicht starten (Port %s): %s", self.cfg["api_port"], exc)
            self.api = None

    def write_api_info(self) -> None:
        """Port der lokalen API und aktuelle Logdatei für die Weboberfläche."""
        logfile = str(self.dlog.filename) if getattr(self, "dlog", None) and self.dlog.filename else ""
        write_json(self.paths.api_info_file, {"port": self.cfg["api_port"], "logfile": logfile,
                                              "sdk": lbsdk.available()}, 0o640)

    def check_config_reload(self) -> None:
        m = self._cfg_mtime()
        if m != self.cfg_mtime:
            self.cfg_mtime = m
            old = self.cfg
            self.cfg = load_config(self.paths)
            log.info("Konfiguration geändert – lade neu")
            if old.get("host") != self.cfg.get("host"):
                with self.lock:
                    self.discovered = {}
                    self.raw = {}
                    self.values = {}
            self.apply_config()
            if old.get("schema_buffer") != self.cfg.get("schema_buffer"):
                with self.lock:
                    self.engine.update_caps()
            if old.get("api_port") != self.cfg.get("api_port") and self.api:
                self.api.stop()
                self.api = None
                self.start_api()

    def public_status(self) -> Dict[str, Any]:
        return {**self.status, "version": VERSION, "writes_enabled": bool(self.cfg["writes_enabled"]),
                "write_max_per_day": self.cfg["write_max_per_day"], "flash": self.flash,
                "time_zone": self.timezone, "mqtt_connected": bool(self.mqtt and self.mqtt.connected),
                "mqtt_topic": self.cfg["mqtt_topic"]}

    # ------------------------------------------------------------------ Discovery
    def discovery_needed(self) -> bool:
        if self.paths.rescan_flag.exists():
            return True
        d = self.discovered or read_json(self.paths.discovery_file, {})
        if (not d or d.get("host") != self.cfg["host"] or d.get("catalog_version") != self.catalog.version
                or d.get("engine_version") != 2):
            return True
        if not self.discovered:
            self.discovered = d
            self._load_tokens()
        return False

    def _load_tokens(self) -> None:
        self.tokens = {P.canonical_id(k): v for k, v in (self.discovered.get("tokens") or {}).items()}
        self.tokens.update({P.canonical_id(k): v for k, v in (self.discovered.get("role_tokens") or {}).items()})

    def run_discovery(self) -> None:
        assert self.client is not None
        t0 = time.time()
        ids = [p.id for p in self.catalog.points]
        log.info("Katalog-Scan: prüfe %d bekannte Datenpunkte (nur lesend) …", len(ids))
        values, _states = self.client.read_raw(ids)
        present = [i for i in ids if i in values]
        enum_ids = [i for i in present if self.catalog.by_id[i].enum_shaped or is_alarm_point(self.catalog.by_id[i])]
        tokens: Dict[str, List[str]] = {}
        if enum_ids:
            dmap = {descriptor_oa(i): i for i in enum_ids}
            dvals, _ = self.client.read_raw(list(dmap))
            for did, pid in dmap.items():
                t = parse_descriptor(dvals.get(did))
                if t:
                    tokens[pid] = t
        # Anlagenrollen: Fähigkeiten bestimmen, dann Deskriptoren der Rollen lesen
        cap_vals, _ = self.client.read_raw(P.capability_ids())
        for k, v in cap_vals.items():
            self.raw[P.canonical_id(k)] = v
        self.engine.update_caps()
        role_ids = sorted(set(self.engine.poll_ids()))
        role_tokens: Dict[str, List[str]] = {}
        dmap = {descriptor_oa(i): i for i in role_ids if P.canonical_id(i) not in tokens}
        if dmap:
            dvals, _ = self.client.read_raw(list(dmap))
            for did, rid in dmap.items():
                t = parse_descriptor(dvals.get(did))
                if t:
                    role_tokens[rid] = t
        ident_vals, _ = self.client.read_raw([PLANT_MODEL_OA, PLANT_SERIAL_OA, PLANT_SW_VERSION_OA])
        hc_names: Dict[str, str] = {}
        hc_vals, _ = self.client.read_raw([hc_name_oa(t) for t in self.catalog.hc_tag_to_number])
        for tag, num in self.catalog.hc_tag_to_number.items():
            v = P.clean_text(hc_vals.get(hc_name_oa(tag)))
            if v:
                hc_names[str(num)] = v
        alarm_ids = [i for i in present if is_alarm_point(self.catalog.by_id[i])
                     or any(normalize_token(t) in ACTIVE_TOKENS for t in tokens.get(i, []))]
        self.discovered = {
            "host": self.cfg["host"],
            "catalog_version": self.catalog.version,
            "engine_version": 2,
            "scanned_at": now_iso(),
            "duration_s": round(time.time() - t0, 1),
            "present": present,
            "absent_count": len(ids) - len(present),
            "tokens": tokens,
            "role_tokens": role_tokens,
            "alarm_ids": alarm_ids,
            "identity": {
                "model": _clean(ident_vals.get(PLANT_MODEL_OA)),
                "serial": _clean(ident_vals.get(PLANT_SERIAL_OA)),
                "sw_version": _clean(ident_vals.get(PLANT_SW_VERSION_OA)),
            },
            "hc_names": hc_names,
        }
        self._load_tokens()
        write_json(self.paths.discovery_file, self.discovered)
        try:
            self.paths.rescan_flag.unlink()
        except FileNotFoundError:
            pass
        caps = self.engine.caps
        log.log(OK, "Katalog-Scan fertig: %d/%d Punkte, %d Alarmpunkte, Anlage %s, SW %s, Heizkreise %s, "
                 "Warmwasser %s, Puffer %s (%.1fs)", len(present), len(ids), len(alarm_ids),
                 self.discovered["identity"]["model"], self.discovered["identity"]["sw_version"],
                 [c["index"] for c in caps.get("circuits", [])], "ja" if caps.get("dhw") else "nein",
                 "ja" if caps.get("buffer") else "nein", time.time() - t0)
        if self.mqtt:
            ident = self.discovered["identity"]
            self.mqtt.publish("info/model", ident["model"])
            self.mqtt.publish("info/sw_version", ident["sw_version"])
            self.mqtt.publish("info/points", len(present))

    # ------------------------------------------------------------------ Polling
    def selected_ids(self) -> List[str]:
        out = []
        alarm_ids = set(self.discovered.get("alarm_ids", []))
        for pid in self.discovered.get("present", []):
            p = self.catalog.by_id.get(pid)
            if p is None:
                continue
            if (p.technical or p.diagnostic) and not self.cfg["include_technical"] and pid not in alarm_ids:
                continue
            out.append(pid)
        return out

    def poll(self) -> None:
        c = self.client
        if c is None:
            self.status.update(connected=False, error="Kein Regler konfiguriert (IP fehlt)")
            self.write_state()
            return
        t0 = time.time()
        self.status["last_poll"] = now_iso()
        try:
            with self.lock:
                if self.discovery_needed():
                    self.run_discovery()
                ids = sorted(set(self.selected_ids()) | set(self.engine.poll_ids()))
                raw, _ = c.read_raw(ids)
                for k, v in raw.items():
                    self.raw[P.canonical_id(k)] = v
                if self.engine.update_caps():
                    # Struktur geändert (z. B. Heizkreis aktiviert): neue Rollen sofort lesen
                    extra = [i for i in self.engine.poll_ids() if i not in raw]
                    if extra:
                        more, _ = c.read_raw(extra)
                        for k, v in more.items():
                            self.raw[P.canonical_id(k)] = v
                    self.engine.update_caps()
                self._interpret_catalog()
        except ClimatixAuthError as exc:
            self._poll_failed(f"{exc} – Benutzer/Passwort/PIN prüfen")
            return
        except ClimatixError as exc:
            self._poll_failed(str(exc))
            return
        if not self.status.get("connected"):
            log.log(OK, "Verbunden mit dem Regler %s", self.cfg["host"])
        self.status.update(connected=True, error=None, last_ok=now_iso(),
                           poll_ms=int((time.time() - t0) * 1000), requests=c.requests)
        self._connection_ok()
        self.engine.record_history()
        self.evaluate_alarms()
        self.publish_values()
        self.write_state()

    def _interpret_catalog(self) -> None:
        tokens = self.discovered.get("tokens", {})
        for pid in self.selected_ids():
            key = P.canonical_id(pid)
            if key in self.raw:
                self.values[pid] = interpret(self.catalog, self.catalog.by_id[pid], self.raw[key], tokens.get(pid))

    def _poll_failed(self, msg: str) -> None:
        if self.status.get("error") != msg:
            log.error("Abfrage fehlgeschlagen: %s", msg)
        self.status.update(connected=False, error=msg)
        now = time.time()
        if self.conn_lost_since is None:
            self.conn_lost_since = now
        elif (not self.conn_lost_notified and self.cfg["notify_connection"]
              and now - self.conn_lost_since >= CONN_LOST_NOTIFY_SEC):
            self.conn_lost_notified = True
            self.notify("daemon", self.texts("NOTIFY.CONN_LOST", minutes=int((now - self.conn_lost_since) // 60),
                                             error=msg), error=True)
        if self.mqtt:
            self.mqtt.publish("connected", 0)
        self.write_state()

    def _connection_ok(self) -> None:
        if self.conn_lost_notified and self.cfg["notify_connection"]:
            self.notify("daemon", self.texts("NOTIFY.CONN_BACK"))
        self.conn_lost_since = None
        self.conn_lost_notified = False

    def notify(self, name: str, message: str, error: bool = False) -> None:
        """LoxBerry-Benachrichtigung; Paket = Plugin-Ordner (Zähler im Menü des Plugins)."""
        text = f"Ochsner OTS: {message}"
        if lbsdk.notify(self.paths.folder, name, text, error=error):
            log.info("Benachrichtigung gesendet: %s", text)
        else:
            log.debug("Benachrichtigung (ohne LoxBerry-SDK nicht gesendet): %s", text)

    # ------------------------------------------------------------------ Alarme
    def evaluate_alarms(self) -> None:
        changed = False
        for pid in self.discovered.get("alarm_ids", []):
            interp = self.values.get(pid)
            if interp is None:
                continue
            state = alarm_state(self.catalog.by_id[pid], interp)
            if state is None:
                continue
            prev = self.alarm_active.get(pid)
            self.alarm_active[pid] = state
            if prev is None and not state:
                continue
            if prev != state:
                changed = True
                p = self.catalog.by_id[pid]
                entry = {"ts": now_iso(), "slug": p.slug, "name": p.name,
                         "event": "kommt" if state else "geht",
                         "raw": interp.get("value"), "text": interp.get("text"), "token": interp.get("token")}
                self.alarm_history.append(entry)
                (log.warning if state else log.info)("Alarm %s: %s (%s)", entry["event"], p.name,
                                                     interp.get("text") or interp.get("value"))
                if self.cfg["notify_alarms"]:
                    if state:
                        detail = interp.get("text") or ""
                        self.notify("alarm", self.texts("NOTIFY.ALARM_ON", name=p.name,
                                                        text=f" ({detail})" if detail else ""), error=True)
                    else:
                        self.notify("alarm", self.texts("NOTIFY.ALARM_OFF", name=p.name))
        if changed:
            self.alarm_history = self.alarm_history[-500:]
            write_json(self.paths.alarm_history_file, self.alarm_history)
            write_json(self.paths.alarm_state_file, self.alarm_active)

    def active_alarms(self) -> List[Point]:
        return [self.catalog.by_id[i] for i, a in self.alarm_active.items() if a]

    # ------------------------------------------------------------------ Veröffentlichen
    def _pub(self, topic: str, value: Any, full: bool) -> None:
        if not full and self.last_published.get(topic) == value:
            return
        self.last_published[topic] = value
        assert self.mqtt is not None
        self.mqtt.publish(topic, value)

    def publish_values(self) -> None:
        m = self.mqtt
        if not m or not m.connected:
            return
        full = (self.cfg["publish_mode"] == "all"
                or time.time() - self.last_full_publish > self.cfg["full_refresh_min"] * 60)
        if self.cfg["publish_raw_points"]:
            for pid, interp in list(self.values.items()):
                p = self.catalog.by_id[pid]
                self._pub(p.slug, interp.get("value"), full)
                if interp.get("text") is not None and p.platform != "text":
                    self._pub(f"{p.slug}/text", interp.get("text"), full)
        with self.lock:
            topics = plant_topics(self.engine)
        for t, v in topics.items():
            self._pub(t, v, full)
        active = self.active_alarms()
        self._pub("connected", 1, full)
        self._pub("alarm/count", len(active), full)
        self._pub("alarm/active", ", ".join(p.name for p in active) if active else "keine", full)
        for pid in self.discovered.get("alarm_ids", []):
            if pid in self.alarm_active:
                self._pub(f"alarm/{self.catalog.by_id[pid].slug}", int(self.alarm_active[pid]), full)
        self._pub("flash/writes_total", self.flash.get("total", 0), full)
        self._pub("flash/writes_today", self.flash.get("today", 0), full)
        if full:
            self.last_full_publish = time.time()

    def write_state(self) -> None:
        tokens = self.discovered.get("tokens", {})
        pts = []
        for pid, interp in list(self.values.items()):
            p = self.catalog.by_id[pid]
            entry: Dict[str, Any] = {
                "slug": p.slug, "id": p.id, "name": p.name, "module": p.module_label,
                "hc": p.hc, "unit": p.unit, "platform": p.platform,
                "value": interp.get("value"), "text": interp.get("text"),
                "writable": p.writable, "technical": p.technical or p.diagnostic,
                "alarm": self.alarm_active.get(pid) if pid in self.discovered.get("alarm_ids", []) else None,
            }
            if p.writable:
                entry.update(min=p.min, max=p.max, step=p.step)
                if p.platform == "select":
                    if tokens.get(pid):
                        entry["choices"] = {str(i): self.catalog.label_for_token(p, t)
                                            for i, t in enumerate(tokens[pid]) if str(t).strip() not in ("", "-")}
                    elif p.options:
                        entry["choices"] = {str(v): k for k, v in p.options.items()}
            pts.append(entry)
        pts.sort(key=lambda e: (e["module"], e["hc"] or 0, e["name"]))
        hc_names = dict(self.discovered.get("hc_names", {}))
        for c in self.engine.caps.get("circuits", []):
            hc_names[str(c["index"])] = self.engine.circuit_name(int(c["index"]))
        state = {
            "version": VERSION,
            "updated": now_iso(),
            "status": self.status,
            "config": {k: self.cfg[k] for k in ("host", "poll_interval", "mqtt_topic", "mqtt_enabled", "writes_enabled",
                                                "write_min_interval_sec", "write_max_per_day", "include_technical",
                                                "notify_alarms", "notify_connection")},
            "mqtt_connected": bool(self.mqtt and self.mqtt.connected),
            "identity": self.discovered.get("identity", {}),
            "hc_names": hc_names,
            "scan": {k: self.discovered.get(k) for k in ("scanned_at", "duration_s", "absent_count")},
            "catalog": {"version": self.catalog.version, "points": len(self.catalog.points)},
            "alarms_active": [{"slug": p.slug, "name": p.name, "text": self.values.get(p.id, {}).get("text")}
                              for p in self.active_alarms()],
            "flash": self.flash,
            "capabilities": {k: v for k, v in self.engine.caps.items() if k != "circuits"},
            "points": pts,
        }
        write_json(self.paths.state_file, state)

    # ------------------------------------------------------------------ Diagnose
    def diagnostics(self) -> Dict[str, Any]:
        """Export für die Fehlersuche – ohne Passwort, PIN und Seriennummer, IP gekürzt."""
        cfg = {k: v for k, v in self.cfg.items() if k not in ("password", "pin")}
        host = str(cfg.get("host") or "")
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            cfg["host"] = ".".join(host.split(".")[:2]) + ".x.x"
        elif host:
            cfg["host"] = "(Hostname)"
        cfg["username_set"] = bool(self.cfg.get("username"))
        cfg["password_set"] = bool(self.cfg.get("password"))
        cfg["pin_set"] = bool(self.cfg.get("pin"))
        cfg.pop("username", None)
        ident = dict(self.discovered.get("identity", {}))
        if ident.get("serial"):
            ident["serial"] = "(entfernt)"
        eng = self.engine
        with self.lock:
            roles = P.role_values(self.raw, eng.role_ids())
            avail = {k: P.first_value(self.raw, oid) for k, oid in P.AVAIL_ROLES.items()}
            caps = {k: v for k, v in eng.caps.items()}
        status = {k: v for k, v in self.status.items() if k != "error"}
        status["error"] = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "<ip>", str(self.status.get("error") or "")) or None
        return {
            "generated": now_iso(),
            "plugin_version": VERSION,
            "python": sys.version.split()[0],
            "loxberry_sdk": lbsdk.available(),
            "mqtt_source": (lbsdk.mqtt_credentials(self.paths.general_json) or {}).get("source"),
            "paho_mqtt": _paho_version(),
            "time_zone": self.timezone,
            "config": cfg,
            "status": status,
            "identity": ident,
            "capabilities": caps,
            "availability_raw": avail,
            "buffer_sensor": eng.buffer_sensor(),
            "role_values": roles,
            "scan": {k: self.discovered.get(k) for k in ("scanned_at", "duration_s", "absent_count", "engine_version")},
            "present_points": len(self.discovered.get("present", [])),
            "alarms_active": [p.slug for p in self.active_alarms()],
            "flash": self.flash,
        }

    def write_subscription_file(self) -> None:
        """Abo für das klassische MQTT Gateway (V1) passend zum Basis-Topic."""
        path = self.paths.config_dir / "mqtt_subscriptions.cfg"
        want = f"{self.cfg['mqtt_topic']}/#\n"
        try:
            if not path.exists() or path.read_text(encoding="utf-8") != want:
                path.write_text(want, encoding="utf-8")
        except OSError as exc:
            log.debug("mqtt_subscriptions.cfg nicht schreibbar: %s", exc)

    # ------------------------------------------------------------------ Schreibschutz (alle Wege)
    def _roll_flash_day(self) -> None:
        if self.flash.get("day") != today():
            self.flash["day"] = today()
            self.flash["today"] = 0

    def guard_writes(self, n: int, source: str) -> None:
        if not self.cfg["writes_enabled"]:
            raise WriteRejected("Schreiben ist gesperrt (Konfiguration → Schreiben erlauben)")
        self._roll_flash_day()
        if int(self.flash.get("today", 0)) + n > self.cfg["write_max_per_day"]:
            raise WriteRejected(f"Tageslimit von {self.cfg['write_max_per_day']} Schreibzugriffen erreicht "
                                f"(heute {self.flash.get('today', 0)})")

    def controller_write(self, oid: str, value: Any, source: str) -> None:
        """Ein gezählter Schreibzugriff (Aufrufer hält self.lock und hat guard_writes geprüft)."""
        key = P.canonical_id(oid)
        min_gap = self.cfg["write_min_interval_sec"] if source.startswith("mqtt") else 0
        wait = min_gap - (time.time() - self.last_write_at.get(key, 0.0))
        if wait > 0:
            raise WriteRejected(f"Ratenlimit: derselbe Punkt erst in {int(wait) + 1}s wieder (Quelle {source})")
        assert self.client is not None
        self.client.write(oid, value)
        self.last_write_at[key] = time.time()
        self.flash["total"] = int(self.flash.get("total", 0)) + 1
        self.flash["today"] = int(self.flash.get("today", 0)) + 1
        pp = self.flash.setdefault("per_point", {})
        name = self._point_name(key)
        pp[name] = pp.get(name, 0) + 1
        write_json(self.paths.flash_file, self.flash)
        log.log(OK, "SCHREIBEN %s (%s) = %s – Quelle %s, Flash heute %d", name, oid, value, source, self.flash["today"])

    def _point_name(self, key: str) -> str:
        p = self.catalog.by_id.get(key)
        if p:
            return p.slug
        for role, m in self.engine.meta().items():
            if P.canonical_id(m["read_id"]) == key or P.canonical_id(m.get("write_id") or "") == key:
                return role
        return key

    def after_engine_write(self) -> None:
        """Nach App-Schreibzugriffen (API-Thread): Hauptschleife veröffentlicht zeitnah."""
        self.refresh_requested = True

    def _append_write_log(self, res: Dict[str, Any]) -> None:
        wl = read_json(self.paths.write_log_file, [])
        wl.append(res)
        write_json(self.paths.write_log_file, wl[-300:])

    # ------------------------------------------------------------------ Einzelpunkt schreiben (Editor, set/<slug>)
    def handle_write(self, slug: str, value: str, source: str) -> Dict[str, Any]:
        res: Dict[str, Any] = {"ts": now_iso(), "source": source, "slug": slug, "value": value, "ok": False}
        p = self.catalog.by_slug.get(slug)
        try:
            if not self.cfg["writes_enabled"]:
                raise WriteRejected("Schreiben ist in den Einstellungen deaktiviert")
            if p is None or p.id not in self.discovered.get("present", []):
                raise WriteRejected(f"Unbekannter oder auf dieser Anlage nicht vorhandener Punkt '{slug}'")
            if not p.writable:
                raise WriteRejected(f"'{p.name}' ist nicht beschreibbar")
            if self.client is None:
                raise WriteRejected("Kein Regler konfiguriert")
            tokens = self.discovered.get("tokens", {}).get(p.id)
            try:
                target, desc = coerce_write_value(self.catalog, p, value, tokens)
            except ValueError as exc:
                raise WriteRejected(str(exc)) from None
            res["name"] = p.name
            current = self.values.get(p.id, {}).get("value")
            if current is not None and _same(current, target, p.step):
                res.update(ok=True, skipped=True, message=f"Unverändert ({desc}) – kein Flash-Schreibzugriff")
                self._append_write_log(res)
                return res
            with self.lock:
                self.guard_writes(1, source)
                assert p.write_id
                self.controller_write(p.write_id, target, source)
                time.sleep(1.0)
                raw, _ = self.client.read_raw([p.id] + [i for i in P.write_dependents(p.id)])
                for k, v in raw.items():
                    self.raw[P.canonical_id(k)] = v
                self._interpret_catalog()
            new_val = self.values.get(p.id, {}).get("value")
            res.update(ok=True, message=f"Geschrieben: {desc}", readback=new_val)
            if new_val is not None and not _same(new_val, target, p.step):
                res["message"] += " – Achtung: Rücklesewert weicht ab (Regler hat evtl. verworfen)"
            self.last_published.pop(p.slug, None)
            self.publish_values()
            self.write_state()
        except (WriteRejected, ClimatixError) as exc:
            res["message"] = str(exc)
            log.info("Schreibwunsch abgelehnt (%s, %s=%s): %s", source, slug, value, exc)
        self._append_write_log(res)
        return res

    def handle_plant_command(self, path: str, payload: str, source: str) -> Dict[str, Any]:
        res: Dict[str, Any] = {"ts": now_iso(), "source": source, "slug": f"cmd/{path}", "value": payload, "ok": False}
        try:
            with self.lock:
                domain, service, data = parse_command(self.engine, path, payload)
            out = self.engine.call_service(domain, service, data, source=source)
            n = out.get("writes", 0)
            res.update(ok=True, message="Unverändert – nichts geschrieben" if n == 0 else f"Ausgeführt ({n} Schreibzugriff{'e' if n != 1 else ''})")
        except (ValueError, WriteRejected, ClimatixError) as exc:
            res["message"] = str(exc)
            log.info("Befehl abgelehnt (%s, %s=%s): %s", source, path, payload, exc)
        self._append_write_log(res)
        return res

    # ------------------------------------------------------------------ Befehle
    def process_inbox(self) -> None:
        while True:
            try:
                kind, name, payload = self.inbox.get_nowait()
            except queue.Empty:
                break
            if kind == "_connected":
                self.last_published.clear()
                self.last_full_publish = 0.0
                if self.values or self.raw:
                    self.publish_values()
                if self.discovered.get("identity") and self.mqtt:
                    ident = self.discovered["identity"]
                    self.mqtt.publish("info/model", ident.get("model"))
                    self.mqtt.publish("info/sw_version", ident.get("sw_version"))
                    self.mqtt.publish("info/points", len(self.discovered.get("present", [])))
                continue
            if kind == "set":
                res = self.handle_write(name, payload, "mqtt")
                if self.mqtt:
                    self.mqtt.publish(f"set_result/{name}", json.dumps(res, ensure_ascii=False), retain=False)
            elif kind == "cmd" and name == "rescan":
                self.paths.rescan_flag.touch()
                self.next_poll = 0.0
            elif kind == "cmd" and name == "poll":
                self.next_poll = 0.0
            elif kind == "cmd":
                res = self.handle_plant_command(name, payload, "mqtt-cmd")
                if self.mqtt:
                    self.mqtt.publish("cmd_result", json.dumps(res, ensure_ascii=False), retain=False)

    def process_spool(self) -> None:
        """Befehle der Weboberfläche (JSON-Dateien in data/cmd/)."""
        files = sorted(self.paths.cmd_dir.glob("*.json"))
        for f in files[:20]:
            cmd = read_json(f, {})
            try:
                f.unlink()
            except OSError:
                pass
            action = cmd.get("action")
            if action == "write":
                res = self.handle_write(str(cmd.get("slug", "")), str(cmd.get("value", "")), "web")
            elif action == "rescan":
                self.paths.rescan_flag.touch()
                self.next_poll = 0.0
                res = {"ts": now_iso(), "source": "web", "ok": True, "message": "Neuer Katalog-Scan angestoßen"}
            elif action == "poll":
                self.next_poll = 0.0
                res = {"ts": now_iso(), "source": "web", "ok": True, "message": "Abfrage angestoßen"}
            elif action == "clear_alarm_history":
                self.alarm_history = []
                write_json(self.paths.alarm_history_file, [])
                res = {"ts": now_iso(), "source": "web", "ok": True, "message": "Alarmverlauf geleert"}
            else:
                continue
            res["cmd_id"] = cmd.get("id")
            self.cmd_results.append(res)
            self.cmd_results = self.cmd_results[-50:]
            write_json(self.paths.cmd_results_file, self.cmd_results)

    # ------------------------------------------------------------------ Hauptschleife
    def run(self) -> None:
        log.info("ochsner2mqtt %s startet (Katalog %s, %d Punkte, LoxBerry-SDK %s)", VERSION, self.catalog.version,
                 len(self.catalog.points), "ja" if lbsdk.available() else "nein")
        self.apply_config()
        self.start_api()
        self.write_state()
        while self.running:
            try:
                self.check_config_reload()
                self.process_inbox()
                self.process_spool()
                if time.time() >= self.next_poll:
                    self.next_poll = time.time() + self.cfg["poll_interval"]
                    self.refresh_requested = False
                    self.poll()
                elif self.refresh_requested:
                    self.refresh_requested = False
                    with self.lock:
                        self._interpret_catalog()
                    self.evaluate_alarms()
                    self.publish_values()
                    self.write_state()
            except Exception:  # noqa: BLE001
                log.exception("Unerwarteter Fehler in der Hauptschleife")
                time.sleep(5)
            time.sleep(0.3)
        self.engine.recorder.maybe_save(force=True)
        if self.api:
            self.api.stop()
        if self.mqtt:
            self.mqtt.stop()
        log.info("ochsner2mqtt beendet")
        self.dlog.end("Daemon stopped")

    def stop(self, *_args: Any) -> None:
        self.running = False


def _clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().strip("\x00")
    return s or None


def _same(a: Any, b: Any, step: Optional[float]) -> bool:
    try:
        tol = (float(step) / 2.0) if step else 1e-6
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return str(a) == str(b)


def clear_retained(paths: Paths, wait: float = 3.0) -> int:
    """Löscht alle gespeicherten (retained) Topics unter dem Basis-Topic am Broker (Deinstallation)."""
    cfg = load_config(paths)
    base = cfg["mqtt_topic"]
    cred = lbsdk.mqtt_credentials(paths.general_json)
    if not cred:
        print("kein MQTT-Broker konfiguriert – nichts zu löschen")
        return 0
    import importlib.util
    if importlib.util.find_spec("paho") is None:
        print("paho-mqtt fehlt – retained Topics nicht gelöscht")
        return 0
    found: List[str] = []
    q: "queue.Queue[tuple]" = queue.Queue()
    m = Mqtt(cred, base, q)
    m.client.on_message = lambda _c, _u, msg: found.append(msg.topic) if msg.retain and msg.payload else None
    deadline = time.time() + 8
    while not m.connected and time.time() < deadline:
        time.sleep(0.1)
    if not m.connected:
        m.stop()
        print("Broker nicht erreichbar – retained Topics nicht gelöscht")
        return 0
    m.client.subscribe(f"{base}/#", qos=0)
    time.sleep(wait)
    topics = sorted(set(t for t in found if t != f"{base}/status"))
    for t in topics + [f"{base}/status"]:
        m.client.publish(t, b"", qos=1, retain=True)
    time.sleep(1.0)
    m.connected = False          # kein "offline" mehr nachschieben
    m.client.loop_stop()
    m.client.disconnect()
    print(f"{len(topics) + 1} gespeicherte Topics unter {base}/ gelöscht")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ochsner OTS → MQTT / App (LoxBerry)")
    ap.add_argument("--lbhome")
    ap.add_argument("--config-dir")
    ap.add_argument("--data-dir")
    ap.add_argument("--log-dir")
    ap.add_argument("--general-json")
    ap.add_argument("--once", action="store_true", help="Einmal abfragen und beenden (Test)")
    ap.add_argument("--clear-retained", action="store_true",
                    help="Gespeicherte MQTT-Topics des Plugins am Broker löschen (Deinstallation)")
    args = ap.parse_args()
    paths = Paths(args)
    lbsdk.load(paths.lbhome)
    if args.clear_retained:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        return clear_retained(paths)
    dlog = lbsdk.DaemonLog(paths.folder, paths.log_dir, "Ochsner OTS")
    dlog.start(log, f"ochsner2mqtt {VERSION} ({'once' if args.once else 'daemon'})")
    try:
        d = Daemon(paths, dlog)
    except Exception:  # noqa: BLE001
        log.critical("Start fehlgeschlagen", exc_info=True)
        dlog.end("Daemon start failed")
        return 1
    signal.signal(signal.SIGTERM, d.stop)
    signal.signal(signal.SIGINT, d.stop)
    if args.once:
        d.apply_config()
        d.poll()
        if d.mqtt:
            time.sleep(1.5)
            d.mqtt.stop()
        dlog.end("Single poll finished")
        print(json.dumps({"status": d.status, "points": len(d.values), "caps": P.public_capabilities(d.engine.caps),
                          "circuits": [c["index"] for c in d.engine.caps.get("circuits", [])],
                          "alarms_active": [p.name for p in d.active_alarms()]}, ensure_ascii=False, indent=1))
        return 0 if d.status.get("connected") else 1
    d.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
