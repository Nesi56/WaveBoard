"""Dependency-free local web server and file services for WaveBoard.

The desktop app reuses the local file/conversion services without starting HTTP.
Optional desktop packages ``libreoffice-impress``
and ``poppler-utils`` enable PowerPoint and PDF slide rendering on Ubuntu.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import getpass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import subprocess
import tempfile
import threading
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit
import uuid

from . import __version__

PROJECT_DIR = Path(__file__).resolve().parent.parent
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_PRESENTATION_BYTES = 250 * 1024 * 1024
MAX_PRESENTATION_PAGES = 200
MIME_OVERRIDES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".obj": "text/plain; charset=utf-8",
    ".stl": "application/octet-stream",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".webm": "video/webm",
    ".mp4": "video/mp4",
}


class APIError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Root:
    id: str
    label: str
    path: Path
    kind: str

    def json(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label, "path": str(self.path), "kind": self.kind}


def confined_path(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    """Resolve a relative API path without permitting traversal or symlink escape."""
    if "\x00" in relative or "\\" in relative or ":" in relative:
        raise APIError(400, "Use a relative path inside the selected location.")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise APIError(403, "This path is outside the selected location.")
    try:
        base = root.resolve(strict=True)
        result = base.joinpath(*parts.parts).resolve(strict=must_exist)
        result.relative_to(base)
    except (ValueError, RuntimeError):
        raise APIError(403, "This path is outside the selected location.") from None
    except FileNotFoundError:
        raise APIError(404, "This file or location is no longer available.") from None
    except PermissionError:
        raise APIError(403, "Permission denied for this location.") from None
    return result


def file_entry(path: Path, relative: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": PurePosixPath(relative).name,
        "path": relative,
        "is_dir": path.is_dir(),
        "size": stat.st_size if path.is_file() else 0,
        "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "extension": path.suffix.lower(),
    }


def byte_range(value: str | None, size: int) -> tuple[int, int, bool]:
    """Parse one HTTP byte range. Browsers use this for seeking local videos."""
    if value is None:
        return 0, max(0, size - 1), False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or size == 0 or not any(match.groups()):
        raise APIError(416, "Requested range is not available.")
    left, right = match.groups()
    if left:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
        if start >= size or start > end:
            raise APIError(416, "Requested range is not available.")
    else:
        suffix = int(right)
        if suffix == 0:
            raise APIError(416, "Requested range is not available.")
        start, end = max(0, size - suffix), size - 1
    return start, end, True


class WaveBoardApp:
    def __init__(self, web_dir: Path | None = None, roots: list[Path] | None = None):
        self.web_dir = (web_dir or PROJECT_DIR / "web").resolve()
        self.custom_roots = [p.expanduser().resolve() for p in roots] if roots else None
        self._temporary = tempfile.TemporaryDirectory(prefix="waveboard-slides-")
        self.jobs_dir = Path(self._temporary.name)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="slides")

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._temporary.cleanup()

    def roots(self) -> list[Root]:
        result: list[Root] = []
        if self.custom_roots:
            for index, path in enumerate(self.custom_roots):
                if path.is_dir():
                    result.append(Root("custom" if index == 0 else f"custom-{index + 1}", path.name or str(path), path, "local"))
        else:
            result.append(Root("home", "This device", Path.home().resolve(), "local"))
            if os.name == "posix":
                user = getpass.getuser()
                candidates: set[Path] = set()
                for base in (Path("/media") / user, Path("/run/media") / user, Path("/media"), Path("/mnt")):
                    try:
                        candidates.update(p for p in base.iterdir() if p.is_dir() and p.is_mount())
                    except (OSError, PermissionError):
                        continue
                for path in sorted(candidates):
                    resolved = path.resolve()
                    identifier = hashlib.sha256(str(resolved).encode()).hexdigest()[:12]
                    result.append(Root(f"usb-{identifier}", path.name, resolved, "usb"))
        demo = self.web_dir / "assets" / "demo"
        if demo.is_dir():
            result.append(Root("demo", "Demo files", demo.resolve(), "demo"))
        return result

    def root(self, identifier: str) -> Root:
        for root in self.roots():
            if root.id == identifier:
                return root
        raise APIError(404, "Location not found. Reconnect the drive and refresh.")

    def locate(self, query: dict[str, list[str]]) -> tuple[Root, str, Path]:
        identifier = query.get("root", [""])[0]
        relative = query.get("path", [""])[0]
        root = self.root(identifier)
        return root, relative, confined_path(root.path, relative)

    def list_files(self, query: dict[str, list[str]]) -> dict[str, Any]:
        root, relative, directory = self.locate(query)
        if not directory.is_dir():
            raise APIError(400, "Choose a folder to browse.")
        relative = str(PurePosixPath(relative))
        if relative == ".":
            relative = ""
        entries = []
        show_hidden = query.get("hidden", ["0"])[0] == "1"
        for child in directory.iterdir():
            if not show_hidden and child.name.startswith("."):
                continue
            child_relative = str(PurePosixPath(relative) / child.name)
            try:
                safe = confined_path(root.path, child_relative)
                if safe.is_dir() or safe.is_file():
                    entries.append(file_entry(safe, child_relative))
            except (APIError, OSError):
                continue
        entries.sort(key=lambda entry: (not entry["is_dir"], entry["name"].casefold()))
        parent = str(PurePosixPath(relative).parent) if relative else None
        return {"root": root.id, "path": relative, "parent": "" if parent == "." else parent, "entries": entries}

    @staticmethod
    def presentation_support() -> dict[str, Any]:
        office = shutil.which("libreoffice") or shutil.which("soffice")
        renderer = shutil.which("pdftoppm")
        missing = []
        if not office:
            missing.append("LibreOffice Impress")
        if not renderer:
            missing.append("Poppler (pdftoppm)")
        return {"available": not missing, "pdf_available": bool(renderer), "reason": "Install " + " and ".join(missing) + " to play presentations." if missing else "PowerPoint and PDF presentation playback is ready."}

    def status(self) -> dict[str, Any]:
        import platform
        return {"platform": platform.system(), "home": str(Path.home()), "roots": [root.json() for root in self.roots()], "presentation": self.presentation_support(), "version": __version__}

    def start_presentation(self, root_id: str, relative: str) -> dict[str, Any]:
        root = self.root(root_id)
        source = confined_path(root.path, relative)
        if not source.is_file() or source.suffix.lower() not in {".ppt", ".pptx", ".odp", ".pdf"}:
            raise APIError(400, "Choose a PowerPoint, OpenDocument, or PDF presentation.")
        if source.stat().st_size > MAX_PRESENTATION_BYTES:
            raise APIError(413, "Presentations must be smaller than 250 MB.")
        office = shutil.which("libreoffice") or shutil.which("soffice")
        renderer = shutil.which("pdftoppm")
        identifier = uuid.uuid4().hex
        job: dict[str, Any] = {"id": identifier, "status": "queued", "pages": [], "name": source.name}
        with self._jobs_lock:
            active = sum(item["status"] in {"queued", "converting"} for item in self._jobs.values())
            if active >= 6 or len(self._jobs) >= 100:
                raise APIError(429, "The presentation queue is full. Finish existing jobs or restart WaveBoard.")
            self._jobs[identifier] = job
        if not renderer or (source.suffix.lower() != ".pdf" and not office):
            job.update(status="error", error=self.presentation_support()["reason"])
            return dict(job)
        self._executor.submit(self._convert_presentation, identifier, source, office, renderer)
        return self.presentation_job(identifier)

    def presentation_job(self, identifier: str) -> dict[str, Any]:
        with self._jobs_lock:
            job = self._jobs.get(identifier)
            if job is None:
                raise APIError(404, "This presentation is no longer loaded.")
            return dict(job)

    def _update_job(self, identifier: str, **values: Any) -> None:
        with self._jobs_lock:
            self._jobs[identifier].update(values)

    def _convert_presentation(self, identifier: str, source: Path, office: str | None, renderer: str) -> None:
        self._update_job(identifier, status="converting")
        job_dir = self.jobs_dir / identifier
        try:
            job_dir.mkdir()
            local_input = job_dir / ("source" + source.suffix.lower())
            shutil.copyfile(source, local_input)
            pdf = local_input
            if source.suffix.lower() != ".pdf":
                profile = job_dir / "office-profile"
                result = subprocess.run([str(office), f"-env:UserInstallation={profile.as_uri()}", "--headless", "--nologo", "--nodefault", "--norestore", "--convert-to", "pdf", "--outdir", str(job_dir), str(local_input)], capture_output=True, text=True, timeout=180, check=False, **_subprocess_options())
                pdf = job_dir / "source.pdf"
                if result.returncode != 0 or not pdf.exists():
                    raise RuntimeError("LibreOffice could not open this presentation. Try exporting it as a PDF.")
            result = subprocess.run([renderer, "-png", "-scale-to", "1600", "-f", "1", "-l", str(MAX_PRESENTATION_PAGES), str(pdf), str(job_dir / "slide")], capture_output=True, text=True, timeout=300, check=False, **_subprocess_options())
            if result.returncode != 0:
                raise RuntimeError("The presentation could not be rendered. Check that the file is readable and not password protected.")
            pages = sorted(job_dir.glob("slide-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
            if not pages:
                raise RuntimeError("No slides were found in this presentation.")
            for number, page in enumerate(pages, 1):
                page.rename(job_dir / f"page-{number}.png")
            self._update_job(identifier, status="ready", pages=[f"/api/presentations/{identifier}/pages/{number}" for number in range(1, len(pages) + 1)], page_limit=MAX_PRESENTATION_PAGES)
        except subprocess.TimeoutExpired:
            self._update_job(identifier, status="error", error="The presentation took too long to render. Try a smaller file or export it as PDF.")
        except (OSError, RuntimeError) as error:
            self._update_job(identifier, status="error", error=str(error))


def _subprocess_options() -> dict[str, Any]:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


class WaveBoardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app: WaveBoardApp):
        self.app = app
        self.allowed_hosts = {"localhost", "127.0.0.1", "::1", socket.gethostname().lower(), address[0].lower()}
        if address[0] in {"0.0.0.0", "::"}:
            try:
                self.allowed_hosts.update(item[4][0].lower() for item in socket.getaddrinfo(socket.gethostname(), None))
            except socket.gaierror:
                pass
        super().__init__(address, WaveBoardHandler)


class WaveBoardServer6(WaveBoardServer):
    address_family = socket.AF_INET6


def open_servers(host: str, port: int, app: WaveBoardApp) -> list[WaveBoardServer]:
    """Listen on host:port. "localhost" means both loopback addresses, 127.0.0.1 and ::1.

    Browsers may try either address for localhost, so both must reach WaveBoard and
    not another program. A machine without IPv6 only gets 127.0.0.1.
    """
    if host != "localhost":
        return [WaveBoardServer((host, port), app)]
    servers = [WaveBoardServer(("127.0.0.1", port), app)]
    try:
        servers.append(WaveBoardServer6(("::1", servers[0].server_port), app))
    except OSError as error:
        if error.errno in {errno.EADDRINUSE, errno.EACCES}:
            servers[0].server_close()
            raise
    return servers


class WaveBoardHandler(BaseHTTPRequestHandler):
    server: WaveBoardServer
    server_version = "WaveBoard/" + __version__

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid logging user file names and query strings.
        if args and str(args[0]).startswith(("GET /api/status", "GET /api/presentations/")):
            return
        print(f"[{self.log_date_time_string()}] {self.command} {urlsplit(self.path).path}")

    def _headers(self, status: int, content_type: str, length: int, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _json(self, data: dict[str, Any], status: int = 200, headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(encoded), headers)
        if self.command != "HEAD":
            self.wfile.write(encoded)

    def _origin_allowed(self) -> bool:
        host = urlsplit("//" + self.headers.get("Host", "")).hostname
        if host not in self.server.allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != self.headers.get("Host", ""):
                return False
        # Blocks ordinary cross-site browser requests, including requests that omit Origin.
        return self.headers.get("Sec-Fetch-Site", "") != "cross-site"

    def _dispatch(self) -> None:
        try:
            if not self._origin_allowed():
                raise APIError(403, "WaveBoard only accepts requests from its own interface.")
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=32)
            if self.command == "POST":
                self._post(parsed.path, query)
            else:
                self._get(parsed.path, query)
        except APIError as error:
            self._json({"error": str(error)}, error.status)
        except (FileNotFoundError, NotADirectoryError):
            self._json({"error": "This file or location is no longer available."}, 404)
        except PermissionError:
            self._json({"error": "Permission denied for this location."}, 403)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except ValueError:
            self._json({"error": "Invalid request."}, 400)
        except OSError:
            self._json({"error": "The device could not read or write this file."}, 500)

    def do_GET(self) -> None:
        self._dispatch()

    def do_HEAD(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def _get(self, route: str, query: dict[str, list[str]]) -> None:
        app = self.server.app
        if route == "/api/status":
            self._json(app.status())
        elif route == "/api/roots":
            self._json({"roots": [root.json() for root in app.roots()]})
        elif route == "/api/files":
            self._json(app.list_files(query))
        elif route == "/api/file":
            _, _, path = app.locate(query)
            self._file(path, user_file=True)
        elif match := re.fullmatch(r"/api/presentations/([a-f0-9]{32})(?:/pages/([1-9][0-9]*))?", route):
            identifier, page = match.groups()
            job = app.presentation_job(identifier)
            if page:
                if job["status"] != "ready" or int(page) > len(job["pages"]):
                    raise APIError(404, "This slide is not available.")
                self._file(app.jobs_dir / identifier / f"page-{page}.png")
            else:
                self._json(job)
        elif route.startswith("/api/"):
            raise APIError(404, "Unknown API endpoint.")
        else:
            from urllib.parse import unquote
            relative = unquote(route).lstrip("/") or "index.html"
            self._file(confined_path(app.web_dir, relative))

    def _file(self, path: Path, *, user_file: bool = False) -> None:
        if not path.is_file():
            raise APIError(404, "File not found.")
        size = path.stat().st_size
        try:
            start, end, partial = byte_range(self.headers.get("Range"), size)
        except APIError as error:
            self._json({"error": str(error)}, 416, {"Content-Range": f"bytes */{size}"})
            return
        mime = MIME_OVERRIDES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        extra = {"Accept-Ranges": "bytes"}
        if partial:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        if user_file:
            safe_inline = mime.startswith(("image/", "video/", "audio/", "model/")) or path.suffix.lower() in {".pdf", ".obj", ".stl"}
            disposition = "inline" if safe_inline else "attachment"
            extra["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(path.name)}"
            extra["Content-Security-Policy"] = "sandbox; default-src 'none'"
        length = end - start + 1 if size else 0
        with path.open("rb") as stream:
            self._headers(206 if partial else 200, mime, length, extra)
            if self.command == "HEAD":
                return
            stream.seek(start)
            remaining = length
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _content_length(self, maximum: int) -> int:
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "Chunked uploads are not supported.")
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise APIError(411, "Content-Length is required.")
        try:
            size = int(raw)
        except ValueError:
            raise APIError(400, "Invalid content length.") from None
        if size < 0:
            raise APIError(400, "Invalid content length.")
        if size > maximum:
            raise APIError(413, f"This file exceeds the {maximum // (1024 * 1024)} MB limit.")
        return size

    def _post(self, route: str, query: dict[str, list[str]]) -> None:
        app = self.server.app
        if route == "/api/upload":
            root, relative, directory = app.locate(query)
            if root.kind == "demo":
                raise APIError(403, "Demo files are read only. Choose a device folder for imports.")
            if not directory.is_dir():
                raise APIError(400, "Choose a folder for the uploaded file.")
            name = query.get("name", [""])[0]
            if not name or name in {".", ".."} or any(char in name for char in "/\\\x00:") or len(name) > 240:
                raise APIError(400, "Choose a valid file name without path separators.")
            size = self._content_length(MAX_UPLOAD_BYTES)
            destination_relative = str(PurePosixPath(relative) / name)
            destination = confined_path(root.path, destination_relative, must_exist=False)
            try:
                stream = destination.open("xb")
            except FileExistsError:
                raise APIError(409, "A file with this name already exists. Rename it before importing.") from None
            completed = False
            try:
                with stream:
                    remaining = size
                    self.connection.settimeout(60)
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise APIError(400, "The upload was interrupted. Please try again.")
                        stream.write(chunk)
                        remaining -= len(chunk)
                completed = True
            finally:
                if not completed:
                    destination.unlink(missing_ok=True)
            self._json({"root": root.id, "path": destination_relative, "entry": file_entry(destination, destination_relative)}, 201)
        elif route == "/api/presentations":
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise APIError(415, "Use application/json for presentation requests.")
            size = self._content_length(16 * 1024)
            try:
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict) or not isinstance(data.get("root"), str) or not isinstance(data.get("path"), str):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                raise APIError(400, "Provide the presentation root and path.") from None
            self._json(app.start_presentation(data["root"], data["path"]), 202)
        else:
            raise APIError(404, "Unknown API endpoint.")


def main() -> None:
    parser = argparse.ArgumentParser(description="WaveBoard local projector workspace")
    parser.add_argument("--host", default="localhost",
                        help="Bind address (default: localhost, meaning 127.0.0.1 and ::1 on this computer only)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default: 8765)")
    parser.add_argument("--root", type=Path, action="append", help="Restrict file browsing to this directory; may be repeated")
    args = parser.parse_args()
    if args.root and any(not path.expanduser().is_dir() for path in args.root):
        parser.error("Every --root must be an existing directory.")
    app = WaveBoardApp(roots=args.root)
    try:
        server, *others = open_servers(args.host, args.port, app)
    except OSError as error:
        app.close()
        parser.exit(1, f"Could not start WaveBoard on port {args.port}: {error}\n")
    for other in others:
        threading.Thread(target=other.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True).start()
    host = f"[{args.host}]" if ":" in args.host else args.host
    print(f"WaveBoard is ready at http://{host}:{server.server_port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping WaveBoard…")
    finally:
        for other in others:
            other.shutdown()
            other.server_close()
        server.server_close()
        app.close()
