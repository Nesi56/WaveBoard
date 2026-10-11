"""Direct desktop operations; no HTTP server or listening sockets."""
import re
from pathlib import Path, PurePosixPath
import shutil
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from .server import APIError, MAX_UPLOAD_BYTES, confined_path, file_entry


class LocalWorkspace:
    def __init__(self, app):
        self.app = app

    def resource(self, url):
        parsed = urlsplit(url)
        if parsed.scheme != "waveboard" or parsed.netloc != "app":
            raise APIError(403, "Only local WaveBoard resources are allowed.")
        query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=32)
        if parsed.path == "/api/file":
            return self.app.locate(query)[2]
        match = re.fullmatch(r"/api/presentations/([a-f0-9]{32})/pages/([1-9][0-9]*)", parsed.path)
        if match:
            identifier, page = match.groups()
            job = self.app.presentation_job(identifier)
            if job["status"] != "ready" or int(page) > len(job["pages"]):
                raise APIError(404, "This slide is not available.")
            return self.app.jobs_dir / identifier / f"page-{page}.png"
        if parsed.path.startswith("/api/"):
            raise APIError(404, "Unknown local resource.")
        return confined_path(self.app.web_dir, unquote(parsed.path).lstrip("/") or "index.html")

    def request(self, url, method="GET", body=None):
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/api/"):
            raise APIError(403, "Only local workspace operations are allowed.")
        query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=32)
        if method == "GET":
            if parsed.path == "/api/status":
                return self.app.status()
            if parsed.path == "/api/roots":
                return {"roots": [root.json() for root in self.app.roots()]}
            if parsed.path == "/api/files":
                return self.app.list_files(query)
            match = re.fullmatch(r"/api/presentations/([a-f0-9]{32})", parsed.path)
            if match:
                return self.app.presentation_job(match.group(1))
        if method == "POST" and parsed.path == "/api/presentations":
            if not isinstance(body, dict) or not all(isinstance(body.get(k), str) for k in ("root", "path")):
                raise APIError(400, "Choose a presentation.")
            return self.app.start_presentation(body["root"], body["path"])
        if method == "POST" and parsed.path == "/api/import":
            if not isinstance(body, dict) or not all(isinstance(body.get(k), str) for k in (
                "source_root", "source_path", "root", "path"
            )):
                raise APIError(400, "Choose the source file and destination folder.")
            source_root = self.app.root(body["source_root"])
            source = confined_path(source_root.path, body["source_path"])
            return self.import_file("/api/upload?" + urlencode({"root": body["root"], "path": body["path"]}), source)
        raise APIError(404, "Unknown local operation.")

    def import_file(self, url, source):
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or parsed.path != "/api/upload":
            raise APIError(403, "Invalid local import operation.")
        query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=32)
        root, relative, directory = self.app.locate(query)
        if root.kind == "demo" or not directory.is_dir():
            raise APIError(403, "Choose a writable device folder.")
        source = Path(source)
        name = source.name
        if not name or name in {".", ".."} or any(c in name for c in "/\\\x00:") or len(name) > 240:
            raise APIError(400, "Choose a valid file name.")
        if not source.is_file() or source.stat().st_size > MAX_UPLOAD_BYTES:
            raise APIError(413, "Choose a file smaller than 512 MB.")
        target_relative = str(PurePosixPath(relative) / name)
        target = confined_path(root.path, target_relative, must_exist=False)
        try:
            output = target.open("xb")
        except FileExistsError:
            raise APIError(409, "A file with this name already exists.") from None
        try:
            with output, source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return {"root": root.id, "path": target_relative, "entry": file_entry(target, target_relative)}
