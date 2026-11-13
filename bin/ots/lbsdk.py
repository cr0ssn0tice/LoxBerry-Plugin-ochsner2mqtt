"""Anbindung an das LoxBerry-Python-SDK (ab LoxBerry 4.0.1: loxberry.system/log/io).

- Protokoll über ``loxberry.log.LBLog``: eigene Log-Sitzung "Daemon" im Logmanager,
  Protokollstufe aus der Pluginverwaltung (CUSTOM_LOGLEVELS), Änderungen greifen
  ohne Neustart.
- Benachrichtigungen über ``loxberry.log.notify`` (Glocke im LoxBerry, Zähler im Plugin-Menü).
- MQTT-Zugang über ``loxberry.io.mqtt_connectiondetails`` (inkl. TLS).
- Texte für Benachrichtigungen aus ``templates/lang/language_<sprache>.ini``.

Fehlt das SDK (Tests, Entwicklung außerhalb eines LoxBerry), arbeitet alles mit
gleichwertigen Rückfallwegen weiter.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

OK = 25                     # LoxBerry-Stufe <OK> (zwischen INFO und WARNING)
logging.addLevelName(OK, "OK")

_SDK: Dict[str, Any] = {}


def load(lbhome: Optional[Path]) -> bool:
    """Importiert das SDK; bei Bedarf aus <lbhome>/libs/pythonlib. True, wenn vorhanden."""
    if _SDK:
        return True
    if lbhome and "LBHOMEDIR" not in os.environ:
        os.environ["LBHOMEDIR"] = str(lbhome)
    for attempt in (0, 1):
        try:
            from loxberry import io as lbio  # noqa: PLC0415
            from loxberry import log as lblog  # noqa: PLC0415
            from loxberry import system as lbsys  # noqa: PLC0415
            _SDK.update(system=lbsys, log=lblog, io=lbio)
            return True
        except Exception:  # noqa: BLE001 – ImportError, aber auch Fehler beim Modulstart
            if attempt == 0 and lbhome and (Path(lbhome) / "libs/pythonlib/loxberry").is_dir():
                sys.path.append(str(Path(lbhome) / "libs/pythonlib"))
                continue
            return False
    return False


def available() -> bool:
    return bool(_SDK)


# ============================================================================ Protokoll
class LBLogHandler(logging.Handler):
    """Leitet Python-logging an LBLog weiter (Datei + Sitzung im LoxBerry-Logmanager)."""

    SEV = ((logging.CRITICAL, 2), (logging.ERROR, 3), (logging.WARNING, 4), (OK, 5), (logging.INFO, 6))

    def __init__(self, lblog: Any) -> None:
        super().__init__(logging.DEBUG)
        self.lblog = lblog

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sev = next((s for lvl, s in self.SEV if record.levelno >= lvl), 7)
            self.lblog.write(sev, self.format(record))
            self.lblog.close()
        except Exception:  # noqa: BLE001
            self.handleError(record)


class PlainLogHandler(logging.Handler):
    """Rückfall ohne SDK: gleiches Zeilenformat wie LBLog in <logdir>/<zeit>_Daemon.log."""

    TAGS = ((logging.CRITICAL, "CRITICAL"), (logging.ERROR, "ERROR"), (logging.WARNING, "WARNING"),
            (OK, "OK"), (logging.INFO, "INFO"))

    def __init__(self, filename: Path) -> None:
        super().__init__(logging.DEBUG)
        self.filename = filename

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tag = next((t for lvl, t in self.TAGS if record.levelno >= lvl), None)
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            line = f"{ts} <{tag}> {self.format(record)}" if tag else f"{ts} {self.format(record)}"
            with open(self.filename, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa: BLE001
            self.handleError(record)


class DaemonLog:
    """Richtet das Protokoll des Daemons ein und merkt sich die aktuelle Logdatei."""

    NAME = "Daemon"

    def __init__(self, package: str, log_dir: Path, title: str) -> None:
        self.package = package
        self.log_dir = log_dir
        self.title = title
        self.lblog: Any = None
        self.filename: Optional[Path] = None
        self._ended = False

    def start(self, logger: logging.Logger, message: str) -> None:
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)      # gefiltert wird nach der LoxBerry-Protokollstufe
        logger.propagate = False
        fmt = logging.Formatter("%(message)s")
        handler: logging.Handler
        if available():
            try:
                self.lblog = _SDK["log"].LBLog(name=self.NAME, package=self.package, logdir=str(self.log_dir),
                                               addtime=True)
                self.lblog.LOGSTART(message)
                self.filename = Path(self.lblog.get_filename())
                handler = LBLogHandler(self.lblog)
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"LBLog nicht nutzbar ({exc}) – eigenes Protokoll\n")
                self.lblog = None
        if self.lblog is None:
            self.filename = self.log_dir / (datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] + f"_{self.NAME}.log")
            with open(self.filename, "a", encoding="utf-8") as fh:
                fh.write("=" * 80 + "\n")
                fh.write(f"<LOGSTART> {datetime.now():%d.%m.%Y %H:%M:%S} TASK STARTED\n<LOGSTART> {message}\n")
            handler = PlainLogHandler(self.filename)
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        if sys.stdout.isatty():
            sh = logging.StreamHandler()
            sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
            logger.addHandler(sh)

    def end(self, message: str) -> None:
        if self._ended:
            return
        self._ended = True
        try:
            if self.lblog is not None:
                self.lblog.LOGEND(message)
            elif self.filename:
                with open(self.filename, "a", encoding="utf-8") as fh:
                    fh.write(f"<LOGEND> {message}\n<LOGEND> {datetime.now():%d.%m.%Y %H:%M:%S} TASK FINISHED\n")
        except Exception:  # noqa: BLE001
            pass


# ============================================================================ Benachrichtigungen
_notify_lock = threading.Lock()


def notify(package: str, name: str, message: str, error: bool = False) -> bool:
    """LoxBerry-Benachrichtigung (ohne SDK: nur Protokoll). Gibt True zurück, wenn gesendet."""
    if not available():
        return False
    with _notify_lock:
        try:
            _SDK["log"].notify(package, name, message, error=error)
            return True
        except Exception:  # noqa: BLE001
            return False


# ============================================================================ MQTT
def _enabled(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "on", "yes", "enabled")


def mqtt_credentials(general_json: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Broker-Zugang des LoxBerry. SDK zuerst, sonst dieselbe Auswertung von general.json."""
    if available():
        try:
            c = _SDK["io"].mqtt_connectiondetails()
            if c and c.get("brokerhost"):
                tls = bool(_numify(c.get("tls")))
                port = c.get("tls_brokerport") if tls else c.get("brokerport")
                return {"host": c["brokerhost"], "port": int(port or (8883 if tls else 1883)),
                        "user": c.get("brokeruser") or "", "password": c.get("brokerpass") or "",
                        "tls": tls, "tls_verify": bool(_numify(c.get("tls_verify"))),
                        "cafile": c.get("tls_cafile") or "", "source": "sdk"}
        except Exception:  # noqa: BLE001
            pass
    if general_json is None or not general_json.exists():
        return None
    try:
        gen = json.loads(general_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    m = (gen or {}).get("Mqtt") or {}
    if not m.get("Brokerhost"):
        return None
    cred: Dict[str, Any] = {"host": m.get("Brokerhost"), "port": int(m.get("Brokerport") or 1883),
                            "user": m.get("Brokeruser") or "", "password": m.get("Brokerpass") or "",
                            "tls": False, "source": "general.json"}
    use_local = _enabled(m.get("Uselocalbroker", "true"))
    if use_local and _enabled(m.get("Tlsenabled", "false")):
        cred.update(tls=True, tls_verify=False, cafile="/etc/mosquitto/tls/ca.crt", port=int(m.get("Tlsport") or 8883))
    elif not use_local and _enabled(m.get("TlsExternalEnabled", "false")):
        cred.update(tls=True, tls_verify=_enabled(m.get("TlsExternalValidatecert", "false")),
                    cafile=str(general_json.parent / "mqtt_external_ca.crt"))
    return cred


def _numify(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ============================================================================ Sprache
FALLBACK_TEXTS = {
    "en": {
        "NOTIFY.ALARM_ON": "Heat pump fault: {name}{text}",
        "NOTIFY.ALARM_OFF": "Heat pump fault cleared: {name}",
        "NOTIFY.CONN_LOST": "No connection to the heat pump for {minutes} minutes: {error}",
        "NOTIFY.CONN_BACK": "Connection to the heat pump restored.",
    },
    "de": {
        "NOTIFY.ALARM_ON": "Störung an der Wärmepumpe: {name}{text}",
        "NOTIFY.ALARM_OFF": "Störung an der Wärmepumpe behoben: {name}",
        "NOTIFY.CONN_LOST": "Seit {minutes} Minuten keine Verbindung zur Wärmepumpe: {error}",
        "NOTIFY.CONN_BACK": "Verbindung zur Wärmepumpe wiederhergestellt.",
    },
}


class Texts:
    """Texte aus den Sprachdateien des Plugins (Fallback Englisch), wie LBSystem::readlanguage."""

    def __init__(self, template_dir: Optional[Path], general_json: Optional[Path] = None) -> None:
        self.lang = "en"
        self.t: Dict[str, str] = {}
        if available():
            try:
                self.lang = (_SDK["system"].lblanguage() or "en")[:2]
            except Exception:  # noqa: BLE001
                pass
        elif general_json is not None:
            try:
                self.lang = str(json.loads(general_json.read_text(encoding="utf-8"))["Base"]["Lang"])[:2] or "en"
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if template_dir is not None:
            for lang in ([self.lang, "en"] if self.lang != "en" else ["en"]):
                self._read(template_dir / "lang" / f"language_{lang}.ini")
        for k, v in FALLBACK_TEXTS.get(self.lang, {}).items():
            self.t.setdefault(k, v)
        for k, v in FALLBACK_TEXTS["en"].items():
            self.t.setdefault(k, v)

    def _read(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return
        section = "default"
        for line in content.splitlines():
            line = line.strip()
            if not line or line[0] in "#;/":
                continue
            if line.startswith("["):
                section = line[1:line.find("]")] if "]" in line else section
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
            self.t.setdefault(f"{section}.{key.strip()}", value)   # erste Fundstelle gewinnt

    def __call__(self, key: str, **params: Any) -> str:
        s = self.t.get(key, key)
        return re.sub(r"\{(\w+)\}", lambda m: str(params.get(m.group(1), m.group(0))), s)
