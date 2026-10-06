"""A small local web UI for browsing generated exercises and copying fields into Hevy.

Standard library only. Serves:
  GET  /                              the single-page UI (ui/index.html)
  GET  /api/exercises                 list of exercises
  GET  /api/exercises/<slug>          one exercise, with Hevy labels and copy-ready text
  GET  /files/<slug>/<path>           image.png, demo.gif, frames/*.png
  POST /api/exercises/<slug>/status   {"added_to_hevy": bool}, saved to <slug>/status.json
"""

import json
import mimetypes
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from .hevy import EQUIPMENT_LABELS, EXERCISE_TYPE_LABELS, muscle_label
from .models import ExerciseSpec
from .output import SPEC_FILE, load_spec

UI_FILE = Path(__file__).parent / "ui" / "index.html"
STATUS_FILE = "status.json"
SERVED_SUFFIXES = {".png", ".gif", ".jpg", ".jpeg", ".webp"}


def notes_text(spec: ExerciseSpec) -> str:
    """Plain-text notes to paste into Hevy's exercise notes."""
    lines = [spec.description, "", "Setup:"]
    lines += [f"{n}. {s}" for n, s in enumerate(spec.setup, 1)]
    lines += ["", "Execution:"]
    lines += [f"{n}. {s}" for n, s in enumerate(spec.execution, 1)]
    lines += ["", "Cues:"]
    lines += [f"- {c}" for c in spec.coaching_cues]
    lines += ["", f"Prescription: {spec.suggested_prescription}"]
    return "\n".join(lines)


class Library:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _dir(self, slug: str) -> Path | None:
        d = (self.root / slug).resolve()
        if d.parent != self.root or not (d / SPEC_FILE).is_file():
            return None
        return d

    def _status(self, d: Path) -> dict:
        try:
            return json.loads((d / STATUS_FILE).read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def list(self) -> list[dict]:
        items = []
        if not self.root.is_dir():
            return items
        for d in sorted(p for p in self.root.iterdir() if (p / SPEC_FILE).is_file()):
            try:
                spec = load_spec(d)
            except (ValidationError, OSError, ValueError):
                items.append({"slug": d.name, "name": d.name, "error": "Invalid exercise.json"})
                continue
            items.append(
                {
                    "slug": d.name,
                    "name": spec.name,
                    "category": spec.category,
                    "muscle_group": muscle_label(spec.hevy_muscle_group),
                    "thumb": f"/files/{d.name}/image.png" if (d / "image.png").is_file() else None,
                    "added_to_hevy": bool(self._status(d).get("added_to_hevy")),
                    "mtime": (d / SPEC_FILE).stat().st_mtime,
                }
            )
        return items

    def get(self, slug: str) -> dict | None:
        d = self._dir(slug)
        if d is None:
            return None
        spec = load_spec(d)
        frames = sorted((d / "frames").glob("*.png")) if (d / "frames").is_dir() else []
        other = [muscle_label(m) for m in spec.hevy_other_muscles]
        return {
            "slug": slug,
            "spec": spec.model_dump(),
            "added_to_hevy": bool(self._status(d).get("added_to_hevy")),
            "hevy_fields": [
                {"label": "Name", "value": spec.name},
                {"label": "Equipment", "value": EQUIPMENT_LABELS[spec.hevy_equipment]},
                {"label": "Primary muscle group", "value": muscle_label(spec.hevy_muscle_group)},
                {"label": "Other muscles", "value": ", ".join(other) or "(none)"},
                {"label": "Exercise type", "value": EXERCISE_TYPE_LABELS[spec.hevy_exercise_type]},
            ],
            "notes": notes_text(spec),
            "image": f"/files/{slug}/image.png" if (d / "image.png").is_file() else None,
            "gif": f"/files/{slug}/demo.gif" if (d / "demo.gif").is_file() else None,
            "frames": [f"/files/{slug}/frames/{f.name}" for f in frames],
        }

    def set_status(self, slug: str, added: bool) -> bool:
        d = self._dir(slug)
        if d is None:
            return False
        status = self._status(d)
        status["added_to_hevy"] = added
        (d / STATUS_FILE).write_text(json.dumps(status, indent=2) + "\n")
        return True

    def file(self, slug: str, rel: str) -> Path | None:
        d = self._dir(slug)
        if d is None:
            return None
        p = (d / rel).resolve()
        if not p.is_file() or not p.is_relative_to(d) or p.suffix.lower() not in SERVED_SUFFIXES:
            return None
        return p


def make_handler(library: Library):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: int = 200):
            self._send(status, json.dumps(data).encode(), "application/json; charset=utf-8")

        def _not_found(self):
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_GET(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            if not parts:
                return self._send(200, UI_FILE.read_bytes(), "text/html; charset=utf-8")
            if parts == ["api", "exercises"]:
                return self._json(library.list())
            if len(parts) == 3 and parts[:2] == ["api", "exercises"]:
                data = library.get(parts[2])
                return self._json(data) if data else self._not_found()
            if len(parts) >= 3 and parts[0] == "files":
                path = library.file(parts[1], "/".join(parts[2:]))
                if path is None:
                    return self._not_found()
                ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                return self._send(200, path.read_bytes(), ctype)
            self._not_found()

        def do_POST(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            if len(parts) == 4 and parts[:2] == ["api", "exercises"] and parts[3] == "status":
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(length) or b"{}")
                except (ValueError, json.JSONDecodeError):
                    return self._json({"error": "bad request"}, HTTPStatus.BAD_REQUEST)
                ok = library.set_status(parts[2], bool(body.get("added_to_hevy")))
                return self._json({"ok": True}) if ok else self._not_found()
            self._not_found()

    return Handler


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def serve(root: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(Library(root)))
    url = f"http://127.0.0.1:{port}/"
    print(f"Serving exercises from {root.resolve()}")
    print(f"  on this computer: {url}")
    if host == "0.0.0.0" and (ip := lan_ip()):
        print(f"  on your phone (same Wi-Fi): http://{ip}:{port}/")
    print("Press Ctrl+C to stop.")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
