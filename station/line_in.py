"""Forward recorder lines from a serial port into the local page.

USB and Bluetooth Classic both appear as a serial device. A bus note is not a
reading and is not posted. Wi-Fi does not use this program: the board posts
the row itself.

The port setup uses POSIX termios. On Windows the page still accepts a row
typed by hand or sent over Wi-Fi.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

try:
    import termios
except ImportError:
    termios = None


def is_reading(payload: dict[str, Any]) -> bool:
    if not isinstance(payload.get("sensor_id"), str):
        return False
    if not isinstance(payload.get("quantity"), str):
        return False
    if not isinstance(payload.get("unit"), str):
        return False
    value = payload.get("value")
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def classify(line: str) -> tuple[str, dict[str, Any]] | None:
    text = line.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ("invalid", {"raw": text})
    if not isinstance(payload, dict):
        return ("invalid", {"raw": text})
    if is_reading(payload):
        return ("reading", payload)
    if isinstance(payload.get("event"), str):
        return ("event", payload)
    return ("invalid", payload)


def page_url() -> str:
    configured = os.environ.get("FVZ_URL", "").strip()
    if configured:
        return configured
    port = os.environ.get("FVZ_PORT", "8321").strip() or "8321"
    return f"http://127.0.0.1:{port}/api/readings"


def post_reading(url: str, row: dict[str, Any]) -> None:
    body = json.dumps(row, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        print(f"страница не приняла строку: {detail}", file=sys.stderr)
    except urllib.error.URLError as exc:
        print(f"страница не открылась: {exc.reason}", file=sys.stderr)


def open_port(path: str, baud: int):
    if termios is None:
        raise SystemExit("Мост USB и Bluetooth работает на Linux.")
    if baud != 115200:
        raise SystemExit("Нужна скорость 115200, как в прошивке.")
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 1
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return os.fdopen(fd, "rb", buffering=0)


def iter_lines(stream: Any):
    pending = b""
    while True:
        chunk = stream.read(256)
        if not chunk:
            return
        pending += chunk
        while b"\n" in pending:
            raw, pending = pending.split(b"\n", 1)
            yield raw.decode("utf-8", "replace")


def handle_line(url: str, line: str) -> None:
    found = classify(line)
    if found is None:
        return
    kind, payload = found
    if kind == "reading":
        post_reading(url, payload)
        return
    if kind == "event":
        note = payload.get("note")
        if isinstance(note, str) and note:
            print(note)
        else:
            print(payload["event"])
        return
    print("строка не показание", file=sys.stderr)


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Нужен путь к порту: python3 station/line_in.py /dev/ttyUSB0",
            file=sys.stderr,
        )
        sys.exit(2)
    url = page_url()
    baud = int(os.environ.get("FVZ_BAUD", "115200"))
    stream = open_port(sys.argv[1], baud)
    print(f"Фермозавр, мост в {url}")
    try:
        for line in iter_lines(stream):
            handle_line(url, line)
    except KeyboardInterrupt:
        print()
    finally:
        stream.close()


if __name__ == "__main__":
    main()
