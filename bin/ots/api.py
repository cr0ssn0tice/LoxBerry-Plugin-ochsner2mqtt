"""Lokale HTTP-API des Daemons (nur 127.0.0.1, Token-geschützt).

Die Weboberfläche ruft sie über ajax.php auf (LoxBerry-Anmeldung davor).
Endpunkte entsprechen den Websocket-Befehlen der HA-Integration:

  GET  /api/plants                    Struktur der Anlage (Rollen, Kreise, …)
  GET  /api/live                      Live-Event + Entity-States + Status
  GET  /api/schedules?force=0|1       Zeitprogramme aller Heizkreise
  POST /api/schedule/set              {"circuit": n, "days": {"0": [[min, 0|1], …]}}
  POST /api/service                   {"domain", "service", "data"}
  GET  /api/history?start=&end=&entity_ids=a,b
  GET  /api/topics                    MQTT-Anlagentopics mit Beschreibung (Loxone-Seite)
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from .climatix import ClimatixError
from .engine import WriteRejected

log = logging.getLogger("ochsner2mqtt.api")


def load_or_create_token(path: Path) -> str:
    try:
        tok = path.read_text(encoding="utf-8").strip()
        if len(tok) >= 32:
            return tok
    except OSError:
        pass
    tok = secrets.token_hex(24)
    path.write_text(tok, encoding="utf-8")
    path.chmod(0o640)
    return tok


def _parse_time(v: Optional[str], default: float) -> float:
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return default


class ApiServer:
    def __init__(self, daemon: Any, port: int, token: str) -> None:
        self.d = daemon
        self.token = token
        handler = self._make_handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", int(port)), handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="o2m-api", daemon=True)

    def start(self) -> None:
        self.thread.start()
        log.info("Lokale API auf 127.0.0.1:%d", self.httpd.server_address[1])

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def _make_handler(self):  # noqa: ANN202
        api = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ochsner2mqtt"

            def log_message(self, fmt: str, *args: Any) -> None:  # leise
                return

            def _send(self, code: int, obj: Any) -> None:
                body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _err(self, code: int, kind: str, msg: str) -> None:
                self._send(code, {"error": {"code": kind, "message": msg}})

            def _auth(self) -> bool:
                if not secrets.compare_digest(self.headers.get("X-O2M-Token", ""), api.token):
                    self._err(403, "forbidden", "Token fehlt oder falsch")
                    return False
                return True

            def _body(self) -> Dict[str, Any]:
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > 256_000:
                    return {}
                try:
                    data = json.loads(self.rfile.read(n).decode("utf-8"))
                    return data if isinstance(data, dict) else {}
                except ValueError:
                    return {}

            def do_GET(self) -> None:  # noqa: N802
                if not self._auth():
                    return
                u = urllib.parse.urlsplit(self.path)
                q = urllib.parse.parse_qs(u.query)
                eng = api.d.engine
                try:
                    if u.path == "/api/plants":
                        with api.d.lock:
                            return self._send(200, eng.plants_payload())
                    if u.path == "/api/live":
                        with api.d.lock:
                            return self._send(200, {"event": eng.event(), "states": eng.states(),
                                                    "status": api.d.public_status()})
                    if u.path == "/api/topics":
                        from .plant_mqtt import COMMANDS, topic_list
                        with api.d.lock:
                            return self._send(200, {"base": api.d.cfg["mqtt_topic"], "topics": topic_list(eng),
                                                    "commands": [{"topic": t, "values": v, "text": x} for t, v, x in COMMANDS],
                                                    "circuits": [{"index": int(c["index"]), "name": eng.circuit_name(int(c["index"]))}
                                                                 for c in eng.caps.get("circuits", [])]})
                    if u.path == "/api/diag":
                        return self._send(200, api.d.diagnostics())
                    if u.path == "/api/schedules":
                        force = q.get("force", ["0"])[0] in ("1", "true")
                        return self._send(200, eng.read_schedules(force=force))
                    if u.path == "/api/history":
                        now = time.time()
                        start = _parse_time(q.get("start", [""])[0], now - 86400)
                        end = _parse_time(q.get("end", [""])[0], now)
                        ids = [i for i in ",".join(q.get("entity_ids", [""])).split(",") if i]
                        return self._send(200, eng.history(ids, start, end))
                    return self._err(404, "not_found", "Unbekannter Endpunkt")
                except WriteRejected as exc:
                    return self._err(409, "rejected", str(exc))
                except ClimatixError as exc:
                    return self._err(503, "controller", str(exc))
                except Exception as exc:  # noqa: BLE001
                    log.exception("API-Fehler bei %s", u.path)
                    return self._err(500, "internal", f"Interner Fehler: {type(exc).__name__}")

            def do_POST(self) -> None:  # noqa: N802
                if not self._auth():
                    return
                u = urllib.parse.urlsplit(self.path)
                body = self._body()
                eng = api.d.engine
                try:
                    if u.path == "/api/service":
                        domain = str(body.get("domain") or "")
                        service = str(body.get("service") or "")
                        data = body.get("data") if isinstance(body.get("data"), dict) else {}
                        log.info("App-Aktion %s.%s %s", domain, service,
                                 {k: v for k, v in data.items() if k != "entity_id"} | {"entity": data.get("entity_id")})
                        res = eng.call_service(domain, service, data, source="app")
                        return self._send(200, {"ok": True, **res})
                    if u.path == "/api/schedule/set":
                        res = eng.write_schedule(int(body.get("circuit") or 0), body.get("days") or {}, source="app")
                        return self._send(200, res)
                    return self._err(404, "not_found", "Unbekannter Endpunkt")
                except WriteRejected as exc:
                    return self._err(409, "rejected", str(exc))
                except ClimatixError as exc:
                    return self._err(503, "controller", str(exc))
                except (TypeError, ValueError) as exc:
                    return self._err(400, "invalid", str(exc))
                except Exception as exc:  # noqa: BLE001
                    log.exception("API-Fehler bei %s", u.path)
                    return self._err(500, "internal", f"Interner Fehler: {type(exc).__name__}")

        return Handler
