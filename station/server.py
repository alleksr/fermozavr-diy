"""Local screen for the Fermozavr T/RH node.

The default bind is localhost. Set FVZ_HOST when an ESP32 should post over
Wi-Fi. Sensors are not required: POST /api/readings accepts the same row
the bench and the field node will send later.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import decisions

HOST = "127.0.0.1"
DEFAULT_PORT = 8321
DEFAULT_NODE = "station"
STALE_AFTER = timedelta(minutes=3)
AGREE_WINDOW = timedelta(minutes=5)
TREND_SPAN = timedelta(minutes=decisions.TREND_MINUTES)
TREND_SLACK = timedelta(minutes=10)
MAX_BODY = 2_000_000
MAX_BATCH = 2000

QUANTITY_UNITS = {
    "air_temperature": "celsius",
    "relative_humidity": "percent_rh",
    "reference_temperature": "celsius",
}
QUANTITY_RANGE = {
    "air_temperature": (-80.0, 80.0),
    "reference_temperature": (-80.0, 80.0),
    "relative_humidity": (-1.0, 110.0),
}
SPRAY_KEYS = (
    "spray_temp_min",
    "spray_temp_max",
    "spray_rh_min",
    "spray_rh_max",
)

STATIC = Path(__file__).resolve().parent / "static"
FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/style.css": "style.css",
    "/app.js": "app.js",
    "/logo-mark.png": "logo-mark.png",
    "/license.html": "license.html",
    "/license": "license.html",
}
MIME = {
    "index.html": "text/html; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "logo-mark.png": "image/png",
    "license.html": "text/html; charset=utf-8",
}


class Reject(Exception):
    pass


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY,
                observed_at TEXT NOT NULL,
                received_at TEXT NOT NULL,
                node_id TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                quantity TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                experiment TEXT,
                note TEXT,
                UNIQUE (node_id, sensor_id, quantity, observed_at)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboards (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                document TEXT NOT NULL,
                position INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_default_dashboard(conn)


WIDGET_TYPES = {"value", "timeseries", "journal", "frost", "spray", "note"}
DASHBOARD_RANGES = {"1h", "4h", "12h", "1d", "all"}
DASHBOARD_ID = re.compile(r"^d[0-9]{1,6}$")
WIDGET_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def default_dashboard_document() -> dict[str, Any]:
    return {
        "title": "Узел T/RH",
        "range": "12h",
        "nextId": 10,
        "widgets": [
            {"id": "temp", "type": "value", "title": "Температура воздуха", "w": 4, "h": 2, "quantity": "air_temperature", "sensor": "", "accent": "green"},
            {"id": "rh", "type": "value", "title": "Влажность", "w": 4, "h": 2, "quantity": "relative_humidity", "sensor": "", "accent": ""},
            {"id": "ref", "type": "value", "title": "Температура опоры", "w": 4, "h": 2, "quantity": "reference_temperature", "sensor": "", "accent": ""},
            {"id": "frost", "type": "frost", "title": "Заморозок", "w": 6, "h": 5},
            {"id": "spray", "type": "spray", "title": "Окно обработки", "w": 6, "h": 6},
            {"id": "chart", "type": "timeseries", "title": "Температура", "w": 12, "h": 5, "series": [], "dual": False, "seriesSet": False, "pending": None},
            {"id": "journal", "type": "journal", "title": "Журнал", "w": 12, "h": 4},
        ],
    }


def _bounded_int(value: Any, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low or value > high:
        raise Reject(f"{field} вне диапазона")
    return value


def _short_text(value: Any, field: str, limit: int, *, allow_empty: bool) -> str:
    if not isinstance(value, str) or len(value) > limit or any(char in value for char in "\n\r"):
        raise Reject(f"{field} пустое или слишком длинное")
    text = value.strip()
    if not text and not allow_empty:
        raise Reject(f"{field} пустое или слишком длинное")
    return text


def normalize_widget(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise Reject("карточка должна быть объектом")
    kind = item.get("type")
    if kind not in WIDGET_TYPES:
        raise Reject("неизвестный тип карточки")
    ident = item.get("id", "")
    if not isinstance(ident, str) or WIDGET_ID.fullmatch(ident) is None:
        raise Reject("неверное имя карточки")
    title = _short_text(item.get("title", ""), "название карточки", 80, allow_empty=True)
    widget: dict[str, Any] = {
        "id": ident,
        "type": kind,
        "title": title,
        "w": _bounded_int(item.get("w", 4), "ширина", 2, 12),
        "h": _bounded_int(item.get("h", 2), "высота", 2, 8),
    }
    if kind == "value":
        quantity = item.get("quantity", "air_temperature")
        if quantity not in QUANTITY_UNITS:
            raise Reject("неизвестная величина")
        accent = item.get("accent", "")
        if accent not in {"", "green", "amber"}:
            raise Reject("неизвестный цвет плитки")
        widget["quantity"] = quantity
        widget["sensor"] = _short_text(item.get("sensor", ""), "экземпляр", 64, allow_empty=True)
        widget["accent"] = accent
    elif kind == "timeseries":
        series = item.get("series", [])
        if not isinstance(series, list) or len(series) > 12:
            raise Reject("слишком много кривых")
        clean_series = []
        for key in series:
            if not isinstance(key, str) or not key or len(key) > 140 or any(char in key for char in "\n\r"):
                raise Reject("неверное имя кривой")
            clean_series.append(key)
        pending = item.get("pending")
        if pending is not None and (not isinstance(pending, str) or len(pending) > 140):
            raise Reject("неверное имя кривой")
        widget["series"] = clean_series
        widget["dual"] = bool(item.get("dual", False))
        widget["seriesSet"] = bool(item.get("seriesSet", False))
        widget["pending"] = pending
    elif kind == "note":
        text = item.get("text", "")
        if not isinstance(text, str) or len(text) > 2000:
            raise Reject("заметка слишком длинная")
        widget["text"] = text
    return widget


def normalize_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Reject("дашборд должен быть объектом")
    title = _short_text(raw.get("title", ""), "название", 80, allow_empty=False)
    time_range = raw.get("range", "12h")
    if time_range not in DASHBOARD_RANGES:
        raise Reject("неизвестное окно времени")
    widgets = raw.get("widgets")
    if not isinstance(widgets, list) or not widgets or len(widgets) > 40:
        raise Reject("нужен список карточек")
    return {
        "title": title,
        "range": time_range,
        "nextId": _bounded_int(raw.get("nextId", 10), "nextId", 1, 100000),
        "widgets": [normalize_widget(item) for item in widgets],
    }


def ensure_default_dashboard(conn: sqlite3.Connection) -> None:
    found = conn.execute("SELECT id FROM dashboards ORDER BY position, id LIMIT 1").fetchone()
    if found is None:
        document = default_dashboard_document()
        conn.execute(
            """
            INSERT INTO dashboards (id, title, document, position, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("d1", document["title"], json.dumps(document, ensure_ascii=False), 1, stamp(datetime.now(timezone.utc))),
        )
        set_setting(conn, "active_dashboard", "d1")
        conn.commit()
        return
    if get_setting(conn, "active_dashboard") is None:
        set_setting(conn, "active_dashboard", str(found["id"]))
        conn.commit()


def dashboard_summaries(conn: sqlite3.Connection) -> list[dict[str, str]]:
    rows = conn.execute("SELECT id, title FROM dashboards ORDER BY position, id").fetchall()
    return [{"id": str(row["id"]), "title": str(row["title"])} for row in rows]


def active_dashboard_id(conn: sqlite3.Connection) -> str:
    ensure_default_dashboard(conn)
    active = get_setting(conn, "active_dashboard")
    if active and conn.execute("SELECT 1 FROM dashboards WHERE id = ?", (active,)).fetchone():
        return active
    first = conn.execute("SELECT id FROM dashboards ORDER BY position, id LIMIT 1").fetchone()
    ident = str(first["id"])
    set_setting(conn, "active_dashboard", ident)
    conn.commit()
    return ident


def read_dashboard(conn: sqlite3.Connection, ident: str) -> dict[str, Any]:
    row = conn.execute("SELECT document FROM dashboards WHERE id = ?", (ident,)).fetchone()
    if row is None:
        raise Reject("нет такого дашборда")
    document = json.loads(str(row["document"]))
    if not isinstance(document, dict):
        raise Reject("дашборд повреждён")
    document["id"] = ident
    return document


def dashboard_list_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    return {"active": active_dashboard_id(conn), "dashboards": dashboard_summaries(conn)}


def split_dashboard_id(path: str) -> str | None:
    prefix = "/api/dashboards/"
    if not path.startswith(prefix) or path == "/api/dashboards/active":
        return None
    ident = path[len(prefix):]
    if DASHBOARD_ID.fullmatch(ident) is None:
        raise Reject("нет такого дашборда")
    return ident


def create_dashboard(conn: sqlite3.Connection, raw: Any) -> dict[str, Any]:
    title = "Новый дашборд"
    if isinstance(raw, dict) and raw.get("title"):
        title = _short_text(raw.get("title"), "название", 80, allow_empty=False)
    document = default_dashboard_document()
    document["title"] = title
    position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 AS next FROM dashboards").fetchone()
    next_number = conn.execute("SELECT id FROM dashboards").fetchall()
    used = []
    for row in next_number:
        tail = str(row["id"])[1:]
        if tail.isdigit():
            used.append(int(tail))
    ident = "d" + str(max(used, default=0) + 1)
    conn.execute(
        """
        INSERT INTO dashboards (id, title, document, position, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ident, title, json.dumps(document, ensure_ascii=False), int(position["next"]), stamp(datetime.now(timezone.utc))),
    )
    set_setting(conn, "active_dashboard", ident)
    conn.commit()
    stored = read_dashboard(conn, ident)
    return {"dashboard": stored, **dashboard_list_payload(conn)}


def update_dashboard(conn: sqlite3.Connection, ident: str, raw: Any) -> dict[str, Any]:
    if conn.execute("SELECT 1 FROM dashboards WHERE id = ?", (ident,)).fetchone() is None:
        raise Reject("нет такого дашборда")
    document = normalize_document(raw)
    conn.execute(
        """
        UPDATE dashboards SET title = ?, document = ?, updated_at = ? WHERE id = ?
        """,
        (document["title"], json.dumps(document, ensure_ascii=False), stamp(datetime.now(timezone.utc)), ident),
    )
    set_setting(conn, "active_dashboard", ident)
    conn.commit()
    stored = read_dashboard(conn, ident)
    return {"dashboard": stored, **dashboard_list_payload(conn)}


def delete_dashboard(conn: sqlite3.Connection, ident: str) -> dict[str, Any]:
    count = conn.execute("SELECT COUNT(*) AS n FROM dashboards").fetchone()
    if int(count["n"]) <= 1:
        raise Reject("последний дашборд не удаляем")
    if conn.execute("SELECT 1 FROM dashboards WHERE id = ?", (ident,)).fetchone() is None:
        raise Reject("нет такого дашборда")
    conn.execute("DELETE FROM dashboards WHERE id = ?", (ident,))
    nxt = conn.execute("SELECT id FROM dashboards ORDER BY position, id LIMIT 1").fetchone()
    set_setting(conn, "active_dashboard", str(nxt["id"]))
    conn.commit()
    stored = read_dashboard(conn, str(nxt["id"]))
    return {"dashboard": stored, **dashboard_list_payload(conn)}


def activate_dashboard(conn: sqlite3.Connection, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Reject("дашборд должен быть объектом")
    ident = raw.get("id", "")
    if not isinstance(ident, str) or DASHBOARD_ID.fullmatch(ident) is None:
        raise Reject("нет такого дашборда")
    stored = read_dashboard(conn, ident)
    set_setting(conn, "active_dashboard", ident)
    conn.commit()
    return {"dashboard": stored, **dashboard_list_payload(conn)}


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])


def set_setting(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        return
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Reject("время не разбирается, нужен ISO, например 2026-10-10T19:00:00+03:00") from exc
    if parsed.tzinfo is None:
        raise Reject("время без зоны, пример 2026-10-10T19:00:00+03:00")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def as_moment(value: str) -> datetime:
    return datetime.fromisoformat(value)


def require_text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise Reject(f"{field} должно быть строкой")
    text = value.strip()
    if not text or len(text) > limit or any(char in text for char in "\n\r\t"):
        raise Reject(f"{field} пустое или слишком длинное")
    return text


def parse_reading(raw: Any, now: datetime) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Reject("строка показания должна быть объектом")
    sensor_id = require_text(raw.get("sensor_id", ""), "sensor_id", 64)
    node_id = raw.get("node_id", DEFAULT_NODE)
    node_id = require_text(node_id if isinstance(node_id, str) else "", "node_id", 64)
    quantity = raw.get("quantity")
    if quantity not in QUANTITY_UNITS:
        raise Reject("неизвестная величина")
    unit = raw.get("unit")
    if unit != QUANTITY_UNITS[quantity]:
        raise Reject("единица не совпадает с величиной")
    value = raw.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise Reject("value должно быть числом")
    number = float(value)
    low, high = QUANTITY_RANGE[quantity]
    if number < low or number > high:
        raise Reject("значение вне допустимого диапазона")
    if "observed_at" in raw and raw["observed_at"] is not None:
        observed = parse_time(str(raw["observed_at"]))
    else:
        observed = now.replace(microsecond=0)
    if observed > now + timedelta(minutes=2):
        raise Reject("время из будущего")
    experiment = raw.get("experiment")
    note = raw.get("note")
    if experiment is not None:
        experiment = require_text(experiment, "experiment", 64)
    if note is not None:
        if not isinstance(note, str) or len(note) > 500:
            raise Reject("заметка слишком длинная")
        note = note.strip()
    return {
        "observed_at": stamp(observed),
        "node_id": node_id,
        "sensor_id": sensor_id,
        "quantity": quantity,
        "value": number,
        "unit": unit,
        "experiment": experiment,
        "note": note or None,
    }


def parse_body(raw: Any, now: datetime) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and "readings" in raw:
        rows = raw["readings"]
    elif isinstance(raw, dict):
        rows = [raw]
    elif isinstance(raw, list):
        rows = raw
    else:
        raise Reject("нужен объект показания или список readings")
    if not isinstance(rows, list) or not rows:
        raise Reject("список показаний пуст")
    if len(rows) > MAX_BATCH:
        raise Reject("слишком много строк в одном запросе")
    return [parse_reading(row, now) for row in rows]


def store_readings(conn: sqlite3.Connection, rows: list[dict[str, Any]], now: datetime) -> int:
    received = stamp(now)
    for row in rows:
        conn.execute(
            """
            INSERT INTO readings (
                observed_at, received_at, node_id, sensor_id, quantity,
                value, unit, experiment, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id, sensor_id, quantity, observed_at)
            DO UPDATE SET
                received_at = excluded.received_at,
                value = excluded.value,
                unit = excluded.unit,
                experiment = excluded.experiment,
                note = excluded.note
            """,
            (
                row["observed_at"],
                received,
                row["node_id"],
                row["sensor_id"],
                row["quantity"],
                row["value"],
                row["unit"],
                row["experiment"],
                row["note"],
            ),
        )
    maybe_autoselect(conn)
    conn.commit()
    return len(rows)


def maybe_autoselect(conn: sqlite3.Connection) -> None:
    if get_setting(conn, "decision_sensor_id"):
        return
    if get_setting(conn, "decision_hold") == "1":
        return
    found = conn.execute(
        """
        SELECT DISTINCT sensor_id FROM readings
        WHERE quantity = 'air_temperature'
        """
    ).fetchall()
    if len(found) == 1:
        set_setting(conn, "decision_sensor_id", str(found[0]["sensor_id"]))


def current_node(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT node_id FROM readings ORDER BY observed_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return DEFAULT_NODE
    return str(row["node_id"])


def latest_per_sensor(conn: sqlite3.Connection, node_id: str, quantity: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.sensor_id, r.value, r.observed_at
        FROM readings r
        JOIN (
            SELECT sensor_id, MAX(observed_at) AS observed_at
            FROM readings
            WHERE node_id = ? AND quantity = ?
            GROUP BY sensor_id
        ) t
          ON t.sensor_id = r.sensor_id
         AND t.observed_at = r.observed_at
        WHERE r.node_id = ? AND r.quantity = ?
        GROUP BY r.sensor_id
        """,
        (node_id, quantity, node_id, quantity),
    ).fetchall()


def fresh_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    if not rows:
        return []
    newest = max(as_moment(str(row["observed_at"])) for row in rows)
    return [
        row
        for row in rows
        if as_moment(str(row["observed_at"])) >= newest - AGREE_WINDOW
    ]


def spread_of(rows: list[sqlite3.Row]) -> float:
    values = [float(row["value"]) for row in rows]
    return max(values) - min(values)


def trend_delta(
    conn: sqlite3.Connection,
    node_id: str,
    sensor_id: str,
    latest_at: datetime,
    latest_value: float,
) -> tuple[float | None, float | None]:
    target = latest_at - TREND_SPAN
    window_start = stamp(target - TREND_SLACK)
    window_end = stamp(target + TREND_SLACK)
    rows = conn.execute(
        """
        SELECT value, observed_at FROM readings
        WHERE node_id = ? AND sensor_id = ? AND quantity = 'air_temperature'
          AND observed_at >= ? AND observed_at <= ?
        """,
        (node_id, sensor_id, window_start, window_end),
    ).fetchall()
    if not rows:
        return None, None
    previous = min(rows, key=lambda row: abs(as_moment(str(row["observed_at"])) - target))
    previous_value = float(previous["value"])
    return previous_value, latest_value - previous_value


def sensor_cards(conn: sqlite3.Connection, node_id: str, chosen: str | None) -> list[dict[str, Any]]:
    temps = {str(row["sensor_id"]): row for row in latest_per_sensor(conn, node_id, "air_temperature")}
    hums = {str(row["sensor_id"]): row for row in latest_per_sensor(conn, node_id, "relative_humidity")}
    refs = {
        str(row["sensor_id"]): row
        for row in latest_per_sensor(conn, node_id, "reference_temperature")
    }
    cards = []
    for sensor_id in sorted(set(temps) | set(hums) | set(refs)):
        temp = temps.get(sensor_id)
        hum = hums.get(sensor_id)
        ref = refs.get(sensor_id)
        moments = [
            str(row["observed_at"])
            for row in (temp, hum, ref)
            if row is not None
        ]
        cards.append(
            {
                "sensor_id": sensor_id,
                "temperature": None if temp is None else decisions.fmt_temp(float(temp["value"])),
                "humidity": None if hum is None else decisions.fmt_rh(float(hum["value"])),
                "reference": None if ref is None else decisions.fmt_temp(float(ref["value"])),
                "observed_at": max(moments),
                "times": {
                    "air_temperature": None if temp is None else str(temp["observed_at"]),
                    "relative_humidity": None if hum is None else str(hum["observed_at"]),
                    "reference_temperature": None if ref is None else str(ref["observed_at"]),
                },
                "chosen": sensor_id == chosen,
            }
        )
    return cards


def build_frost(
    conn: sqlite3.Connection,
    node_id: str,
    chosen: str | None,
    air_rows: list[sqlite3.Row],
    now: datetime,
) -> dict[str, Any]:
    known = [str(row["sensor_id"]) for row in air_rows]
    if not chosen:
        return decisions.no_sensor(known)
    chosen_row = next((row for row in air_rows if str(row["sensor_id"]) == chosen), None)
    if chosen_row is None:
        return decisions.no_reading()
    fresh = fresh_rows(air_rows)
    fresh_ids = {str(row["sensor_id"]) for row in fresh}
    if chosen not in fresh_ids and fresh:
        others = [str(row["sensor_id"]) for row in fresh]
        return decisions.sensor_quiet(chosen, others)
    latest_at = as_moment(str(chosen_row["observed_at"]))
    latest_value = float(chosen_row["value"])
    stale = now - latest_at > STALE_AFTER
    if len(fresh) >= 2 and spread_of(fresh) > decisions.TEMP_BAR:
        verdict = decisions.disagreement_verdict(spread_of(fresh), stale=stale)
        verdict["sensors"] = [
            {
                "sensor_id": str(row["sensor_id"]),
                "temperature": decisions.fmt_temp(float(row["value"])),
            }
            for row in fresh
        ]
        return verdict
    previous, delta = trend_delta(conn, node_id, chosen, latest_at, latest_value)
    at_time = decisions.frost_verdict(latest_value, delta)
    if stale:
        verdict = decisions.stale_verdict(at_time)
    else:
        verdict = dict(at_time)
    verdict["facts"] = {
        "sensor_id": chosen,
        "now": decisions.fmt_temp(latest_value),
        "then": None if previous is None else decisions.fmt_temp(previous),
        "delta": None if delta is None else decisions.fmt_temp(delta),
        "observed_at": str(chosen_row["observed_at"]),
    }
    verdict["neighbors"] = [
        {
            "sensor_id": str(row["sensor_id"]),
            "temperature": decisions.fmt_temp(float(row["value"])),
            "delta": decisions.fmt_temp(float(row["value"]) - latest_value),
        }
        for row in fresh
        if str(row["sensor_id"]) != chosen
    ]
    return verdict


def optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    return float(value)


def build_spray(
    conn: sqlite3.Connection,
    node_id: str,
    chosen: str | None,
    frost_code: str,
) -> dict[str, Any]:
    if frost_code == "disagreement":
        return decisions.spray_blocked()
    if frost_code == "stale":
        return decisions.spray_stale()
    if frost_code in {"no_sensor", "no_reading", "sensor_quiet"}:
        return decisions.spray_without_air()
    bounds = tuple(optional_float(get_setting(conn, key)) for key in SPRAY_KEYS)
    temp_row = None
    rh_row = None
    if chosen:
        temp_rows = latest_per_sensor(conn, node_id, "air_temperature")
        rh_rows = latest_per_sensor(conn, node_id, "relative_humidity")
        temp_row = next((row for row in temp_rows if str(row["sensor_id"]) == chosen), None)
        fresh_rh = fresh_rows(rh_rows)
        if len(fresh_rh) >= 2 and spread_of(fresh_rh) > decisions.RH_BAR:
            return decisions.humidity_disagreement(spread_of(fresh_rh))
        rh_row = next((row for row in rh_rows if str(row["sensor_id"]) == chosen), None)
        if temp_row is not None and rh_row is not None:
            temp_at = as_moment(str(temp_row["observed_at"]))
            rh_at = as_moment(str(rh_row["observed_at"]))
            if abs(temp_at - rh_at) > AGREE_WINDOW:
                rh_row = None
    temp = None if temp_row is None else float(temp_row["value"])
    rh = None if rh_row is None else float(rh_row["value"])
    return decisions.spray_verdict(temp, rh, bounds[0], bounds[1], bounds[2], bounds[3])


def chart_readings(conn: sqlite3.Connection, node_id: str, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT observed_at, sensor_id, quantity, value, unit, experiment, note
        FROM (
            SELECT observed_at, sensor_id, quantity, value, unit, experiment, note, id
            FROM readings
            WHERE node_id = ?
            ORDER BY observed_at DESC, id DESC
            LIMIT ?
        )
        ORDER BY observed_at ASC, id ASC
        """,
        (node_id, limit),
    ).fetchall()
    return [
        {
            "observed_at": row["observed_at"],
            "sensor_id": row["sensor_id"],
            "quantity": row["quantity"],
            "value": row["value"],
            "unit": row["unit"],
            "experiment": row["experiment"],
            "note": row["note"],
        }
        for row in rows
    ]


def recent_readings(conn: sqlite3.Connection, node_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT observed_at, sensor_id, quantity, value, unit, experiment, note
        FROM readings
        WHERE node_id = ?
        ORDER BY observed_at DESC, id DESC
        LIMIT 20
        """,
        (node_id,),
    ).fetchall()
    return [
        {
            "observed_at": row["observed_at"],
            "sensor_id": row["sensor_id"],
            "quantity": row["quantity"],
            "value": row["value"],
            "unit": row["unit"],
            "experiment": row["experiment"],
            "note": row["note"],
        }
        for row in rows
    ]


def build_state(conn: sqlite3.Connection, now: datetime) -> dict[str, Any]:
    node_id = current_node(conn)
    chosen = get_setting(conn, "decision_sensor_id")
    air_rows = latest_per_sensor(conn, node_id, "air_temperature")
    frost = build_frost(conn, node_id, chosen, air_rows, now)
    spray = build_spray(conn, node_id, chosen, str(frost["code"]))
    return {
        "node_id": node_id,
        "decision_sensor_id": chosen,
        "bars": {
            "temperature_c": decisions.TEMP_BAR,
            "humidity_rh": decisions.RH_BAR,
            "frost_low_c": decisions.FROST_LOW,
            "frost_high_c": decisions.FROST_HIGH,
            "trend_minutes": decisions.TREND_MINUTES,
            "stale_minutes": int(STALE_AFTER.total_seconds() // 60),
            "saturation_rh": decisions.RH_SATURATION,
        },
        "spray_band": {
            "temp_min": optional_float(get_setting(conn, "spray_temp_min")),
            "temp_max": optional_float(get_setting(conn, "spray_temp_max")),
            "rh_min": optional_float(get_setting(conn, "spray_rh_min")),
            "rh_max": optional_float(get_setting(conn, "spray_rh_max")),
        },
        "sensors": sensor_cards(conn, node_id, chosen),
        "frost": frost,
        "spray": spray,
        "readings": recent_readings(conn, node_id),
    }


def apply_settings(conn: sqlite3.Connection, raw: Any) -> None:
    if not isinstance(raw, dict):
        raise Reject("настройки должны быть объектом")
    if "decision_sensor_id" in raw:
        sensor_id = raw["decision_sensor_id"]
        if sensor_id is None or sensor_id == "":
            set_setting(conn, "decision_sensor_id", None)
            set_setting(conn, "decision_hold", "1")
        else:
            sensor_id = require_text(sensor_id, "decision_sensor_id", 64)
            found = conn.execute(
                "SELECT 1 FROM readings WHERE sensor_id = ? LIMIT 1",
                (sensor_id,),
            ).fetchone()
            if found is None:
                raise Reject("такого экземпляра ещё нет")
            set_setting(conn, "decision_sensor_id", sensor_id)
            set_setting(conn, "decision_hold", None)
    for key in SPRAY_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if value is None or value == "":
            set_setting(conn, key, None)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise Reject(f"{key} должно быть числом")
        set_setting(conn, key, str(float(value)))
    temp_min = optional_float(get_setting(conn, "spray_temp_min"))
    temp_max = optional_float(get_setting(conn, "spray_temp_max"))
    rh_min = optional_float(get_setting(conn, "spray_rh_min"))
    rh_max = optional_float(get_setting(conn, "spray_rh_max"))
    if temp_min is not None and temp_max is not None and temp_min >= temp_max:
        raise Reject("нижняя температура полосы должна быть ниже верхней")
    if rh_min is not None and rh_max is not None and rh_min >= rh_max:
        raise Reject("нижняя влажность полосы должна быть ниже верхней")
    if rh_min is not None and (rh_min < 0 or rh_min > 100):
        raise Reject("влажность полосы задаётся от 0 до 100")
    if rh_max is not None and (rh_max < 0 or rh_max > 100):
        raise Reject("влажность полосы задаётся от 0 до 100")
    conn.commit()


class StationServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], db_path: Path) -> None:
        self.db_path = db_path
        super().__init__(server_address, Handler)


class Handler(BaseHTTPRequestHandler):
    server: StationServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/state":
            self._state()
            return
        if path == "/api/readings":
            self._readings(parse_qs(parsed.query))
            return
        if path == "/api/dashboards":
            self._dashboard_list()
            return
        try:
            ident = split_dashboard_id(path)
        except Reject as exc:
            self._send(400, {"error": str(exc)})
            return
        if ident is not None:
            self._dashboard_get(ident)
            return
        self._file(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        now = datetime.now(timezone.utc)
        try:
            payload = self._json()
            with connect(self.server.db_path) as conn:
                if path == "/api/readings":
                    count = store_readings(conn, parse_body(payload, now), now)
                    self._send(201, {"stored": count})
                    return
                if path == "/api/settings":
                    apply_settings(conn, payload)
                    self._send(200, {"ok": True})
                    return
                if path == "/api/dashboards":
                    self._send(201, create_dashboard(conn, payload))
                    return
                if path == "/api/dashboards/active":
                    self._send(200, activate_dashboard(conn, payload))
                    return
                ident = split_dashboard_id(path)
                if ident is not None:
                    self._send(200, update_dashboard(conn, ident, payload))
                    return
        except Reject as exc:
            self._send(400, {"error": str(exc)})
            return
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": "нужно JSON-тело"})
            return
        self._send(404, {"error": "нет такого пути"})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            ident = split_dashboard_id(path)
            if ident is None:
                self._send(404, {"error": "нет такого пути"})
                return
            with connect(self.server.db_path) as conn:
                self._send(200, delete_dashboard(conn, ident))
        except Reject as exc:
            self._send(400, {"error": str(exc)})
            return

    def _dashboard_list(self) -> None:
        with connect(self.server.db_path) as conn:
            self._send(200, dashboard_list_payload(conn))

    def _dashboard_get(self, ident: str) -> None:
        try:
            with connect(self.server.db_path) as conn:
                self._send(200, read_dashboard(conn, ident))
        except Reject as exc:
            self._send(400, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _state(self) -> None:
        now = datetime.now(timezone.utc)
        with connect(self.server.db_path) as conn:
            self._send(200, build_state(conn, now))

    def _readings(self, query: dict[str, list[str]]) -> None:
        raw_limit = query.get("limit", ["800"])[0]
        try:
            limit = int(raw_limit)
        except ValueError:
            self._send(400, {"error": "limit должен быть числом"})
            return
        if limit < 1 or limit > 2000:
            self._send(400, {"error": "limit от 1 до 2000"})
            return
        with connect(self.server.db_path) as conn:
            node_id = current_node(conn)
            rows = chart_readings(conn, node_id, limit)
        self._send(200, {"node_id": node_id, "readings": rows})

    def _json(self) -> Any:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            raise Reject("пустое или слишком большое тело")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _file(self, path: str) -> None:
        name = FILES.get(path)
        if name is None:
            self._send(404, {"error": "нет такого пути"})
            return
        body = (STATIC / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME[name])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def create_server(db_path: Path, host: str = HOST, port: int = DEFAULT_PORT) -> StationServer:
    init_db(db_path)
    return StationServer((host, port), db_path)


def listen_host() -> str:
    raw = os.environ.get("FVZ_HOST", HOST).strip()
    return raw or HOST


def main() -> None:
    port = int(os.environ.get("FVZ_PORT", str(DEFAULT_PORT)))
    host = listen_host()
    root = Path(__file__).resolve().parent
    db_path = Path(os.environ.get("FVZ_DB", str(root / "data" / "station.sqlite")))
    httpd = create_server(db_path, host, port)
    print(f"Фермозавр, узел T/RH  http://127.0.0.1:{port}")
    if host != HOST:
        print(f"Слушаю {host}:{port}. Вход для строки без пароля.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
