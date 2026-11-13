"""Synchroner Client für die lokale JSON-Schnittstelle des Climatix-Reglers.

Nur Standardbibliothek. Zugangsdaten und PIN werden nie geloggt.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

log = logging.getLogger("ochsner2mqtt.climatix")

PATHS = ("/jsongen.html", "/JSONgen.html")


class ClimatixError(RuntimeError):
    pass


class ClimatixAuthError(ClimatixError):
    pass


class ClimatixClient:
    def __init__(self, host: str, port: int = 80, username: str = "", password: str = "",
                 pin: str = "", timeout: float = 10.0, max_ids: int = 40, gap_sec: float = 0.1) -> None:
        self.host = host.strip()
        self.port = int(port or 80)
        self.username = username or ""
        self.password = password or ""
        self.pin = str(pin or "")
        self.timeout = float(timeout)
        self.max_ids = max(1, min(int(max_ids), 200))
        self.gap_sec = max(0.0, float(gap_sec))
        self._path: Optional[str] = None
        self.requests = 0

    # ------------------------------------------------------------------ HTTP
    def _auth_header(self) -> Optional[str]:
        if not self.username and not self.password:
            return None
        tok = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
        return f"Basic {tok}"

    def _get(self, params: List[Tuple[str, str]]) -> Dict[str, Any]:
        query = list(params)
        if self.pin:
            query.append(("PIN", self.pin))
        query += [("LNG", "-1"), ("US", "1")]
        qs = urllib.parse.urlencode(query, safe=";")
        paths = (self._path,) if self._path else PATHS
        last_exc: Optional[BaseException] = None
        last_err_payload: Optional[Dict[str, Any]] = None
        for path in paths:
            url = f"http://{self.host}:{self.port}{path}?{qs}"
            req = urllib.request.Request(url, method="GET")
            hdr = self._auth_header()
            if hdr:
                req.add_header("Authorization", hdr)
            try:
                self.requests += 1
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise ClimatixAuthError(f"HTTP {exc.code}: Zugangsdaten abgelehnt") from None
                last_exc = ClimatixError(f"HTTP {exc.code} auf {path}")
                continue
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                raise ClimatixError(f"Regler nicht erreichbar: {reason}") from None
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            try:
                payload = json.loads(text)
            except ValueError:
                last_exc = ClimatixError(f"Keine JSON-Antwort auf {path}")
                continue
            if not isinstance(payload, dict):
                last_exc = ClimatixError(f"Unerwartete Antwort auf {path}")
                continue
            if payload.get("Error") not in (0, None, "0") and "values" not in payload and "states" not in payload:
                last_err_payload = payload
                continue
            self._path = path
            return payload
        if last_err_payload is not None:
            raise ClimatixError(f"Regler meldet Fehlercode {last_err_payload.get('Error')} "
                                f"(häufigste Ursache: PIN falsch oder fehlt)")
        raise last_exc or ClimatixError("Keine Antwort")

    # ------------------------------------------------------------------ API
    def read_raw(self, ids: Iterable[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Liest OAs gebündelt. Gibt (values, states) zurück.

        values: OA -> Rohwert (erstes Listenelement)
        states: OA -> Statuscode (5 = nicht vorhanden / kein Zugriff)
        """
        id_list = [i for i in ids if i]
        values: Dict[str, Any] = {}
        states: Dict[str, Any] = {}
        for n in range(0, len(id_list), self.max_ids):
            chunk = id_list[n:n + self.max_ids]
            params = [("FN", "Read")] + [("OA", oa) for oa in chunk]
            payload = self._get(params)
            v = payload.get("values")
            s = payload.get("states")
            if isinstance(v, dict):
                for k, raw in v.items():
                    values[str(k)] = raw[0] if isinstance(raw, list) and raw else raw
            if isinstance(s, dict):
                for k, st in s.items():
                    states[str(k)] = st
            if self.gap_sec and n + self.max_ids < len(id_list):
                time.sleep(self.gap_sec)
        return values, states

    def read(self, ids: Iterable[str]) -> Dict[str, Any]:
        return self.read_raw(ids)[0]

    def write(self, oa: str, value: Any) -> Dict[str, Any]:
        if isinstance(value, float) and value.is_integer():
            value_str = str(int(value))
        else:
            value_str = str(value)
        payload = self._get([("FN", "Write"), ("OA", f"{oa};{value_str}")])
        if payload.get("Error") not in (0, None, "0") and "values" not in payload:
            raise ClimatixError(f"Schreiben abgelehnt: {payload.get('Error')}")
        return payload
