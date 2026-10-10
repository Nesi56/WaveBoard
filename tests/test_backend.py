"""Run with: python -m unittest discover -s tests -v"""

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from waveboard.server import APIError, WaveBoardApp, WaveBoardServer, byte_range, confined_path


class PathAndRangeTests(unittest.TestCase):
    def test_ranges_support_video_seeking(self):
        self.assertEqual(byte_range(None, 10), (0, 9, False))
        self.assertEqual(byte_range("bytes=3-6", 10), (3, 6, True))
        self.assertEqual(byte_range("bytes=5-", 10), (5, 9, True))
        self.assertEqual(byte_range("bytes=-3", 10), (7, 9, True))
        self.assertEqual(byte_range("bytes=0-500", 10), (0, 9, True))
        self.assertEqual(byte_range("bytes=-500", 10), (0, 9, True))

    def test_invalid_ranges_are_rejected(self):
        for value in ("bytes=10-", "bytes=7-2", "bytes=-0", "bytes=-", "bytes=0-1,4-5", "items=0-1"):
            with self.subTest(value=value), self.assertRaises(APIError) as error:
                byte_range(value, 10)
            self.assertEqual(error.exception.status, 416)
        with self.assertRaises(APIError):
            byte_range("bytes=0-", 0)

    def test_confined_paths_reject_absolute_traversal_and_drive_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for relative in ("../secret", "sub/../../secret", "/etc/passwd", "C:/Windows", "sub\\secret", "bad\x00name"):
                with self.subTest(relative=relative), self.assertRaises(APIError):
                    confined_path(base, relative, must_exist=False)
            self.assertEqual(confined_path(base, "new.txt", must_exist=False), base.resolve() / "new.txt")

    def test_symlink_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            root.mkdir()
            target = base / "private.txt"
            target.write_text("private")
            try:
                (root / "escape.txt").symlink_to(target)
            except OSError:
                self.skipTest("This OS does not permit this account to create symlinks")
            with self.assertRaises(APIError) as error:
                confined_path(root, "escape.txt")
            self.assertEqual(error.exception.status, 403)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="waveboard-test-")
        cls.base = Path(cls.temporary.name)
        cls.root = cls.base / "files"
        cls.root.mkdir()
        (cls.root / "folder").mkdir()
        (cls.root / "video.mp4").write_bytes(b"0123456789")
        (cls.root / "empty.txt").write_bytes(b"")
        (cls.root / ".hidden").write_text("hidden")
        (cls.root / "deck.pptx").write_bytes(b"demo")
        (cls.root / "document.html").write_text("<script>alert(1)</script>")
        cls.web = cls.base / "web"
        cls.web.mkdir()
        (cls.web / "index.html").write_text("<h1>WaveBoard</h1>")
        (cls.web / "assets" / "demo").mkdir(parents=True)
        cls.app = WaveBoardApp(web_dir=cls.web, roots=[cls.root])
        cls.server = WaveBoardServer(("127.0.0.1", 0), cls.app)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.app.close()
        cls.temporary.cleanup()

    def request(self, path, *, method="GET", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def file_url(self, relative):
        return "/api/file?" + urlencode({"root": "custom", "path": relative})

    def test_status_and_static_ui(self):
        status, _, body = self.request("/api/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual([root["id"] for root in data["roots"]], ["custom", "demo"])
        self.assertIn("pdf_available", data["presentation"])
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"WaveBoard", body)
        self.assertIn("text/html", headers["Content-Type"])

    def test_file_listing_and_parent(self):
        status, _, body = self.request("/api/files?root=custom&path=")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIsNone(data["parent"])
        self.assertEqual(data["entries"][0]["name"], "folder")
        self.assertTrue(data["entries"][0]["is_dir"])
        self.assertNotIn(".hidden", [entry["name"] for entry in data["entries"]])
        status, _, body = self.request("/api/files?root=custom&path=folder")
        self.assertEqual(json.loads(body)["parent"], "")
        status, _, body = self.request("/api/files?root=custom&hidden=1")
        self.assertIn(".hidden", [entry["name"] for entry in json.loads(body)["entries"]])

    def test_full_range_and_head_requests(self):
        status, headers, body = self.request(self.file_url("video.mp4"))
        self.assertEqual((status, body), (200, b"0123456789"))
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        status, headers, body = self.request(self.file_url("video.mp4"), headers={"Range": "bytes=3-6"})
        self.assertEqual((status, body), (206, b"3456"))
        self.assertEqual(headers["Content-Range"], "bytes 3-6/10")
        self.assertEqual(headers["Content-Length"], "4")
        status, headers, body = self.request(self.file_url("video.mp4"), method="HEAD", headers={"Range": "bytes=-2"})
        self.assertEqual((status, body), (206, b""))
        self.assertEqual(headers["Content-Length"], "2")
        self.assertEqual(headers["Content-Range"], "bytes 8-9/10")

    def test_unsatisfiable_range_and_empty_file(self):
        status, headers, _ = self.request(self.file_url("video.mp4"), headers={"Range": "bytes=100-200"})
        self.assertEqual(status, 416)
        self.assertEqual(headers["Content-Range"], "bytes */10")
        status, headers, body = self.request(self.file_url("empty.txt"))
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(headers["Content-Length"], "0")

    def test_traversal_and_unknown_root_are_rejected(self):
        for url in (self.file_url("../secret.txt"), "/%2e%2e/private.txt", "/api/file?root=missing&path=video.mp4"):
            with self.subTest(url=url):
                status, _, _ = self.request(url)
                self.assertIn(status, (403, 404))

    def test_untrusted_html_is_downloaded_and_sandboxed(self):
        status, headers, _ = self.request(self.file_url("document.html"))
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Disposition"].startswith("attachment"))
        self.assertIn("sandbox", headers["Content-Security-Policy"])

    def test_upload_and_duplicate_protection(self):
        route = "/api/upload?" + urlencode({"root": "custom", "path": "folder", "name": "test drawing.png"})
        status, _, body = self.request(route, method="POST", body=b"drawing", headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["path"], "folder/test drawing.png")
        self.assertEqual((self.root / "folder" / "test drawing.png").read_bytes(), b"drawing")
        status, _, _ = self.request(route, method="POST", body=b"replacement")
        self.assertEqual(status, 409)
        self.assertEqual((self.root / "folder" / "test drawing.png").read_bytes(), b"drawing")

    def test_upload_rejects_traversal_and_demo_writes(self):
        for values in ({"root": "custom", "path": "", "name": "../escape.txt"}, {"root": "custom", "path": "..", "name": "escape.txt"}, {"root": "demo", "path": "", "name": "new.txt"}):
            status, _, _ = self.request("/api/upload?" + urlencode(values), method="POST", body=b"secret")
            self.assertIn(status, (400, 403))
        self.assertFalse((self.base / "escape.txt").exists())

    def test_cross_origin_and_dns_rebinding_requests_are_rejected(self):
        for headers in ({"Origin": "https://example.com"}, {"Sec-Fetch-Site": "cross-site"}, {"Host": "attacker.example"}):
            status, _, _ = self.request("/api/status", headers=headers)
            self.assertEqual(status, 403)
        status, _, _ = self.request("/api/status", headers={"Origin": f"http://127.0.0.1:{self.server.server_port}"})
        self.assertEqual(status, 200)

    def test_missing_presentation_dependencies_are_actionable(self):
        with patch("waveboard.server.shutil.which", return_value=None):
            status, _, body = self.request("/api/presentations", method="POST", body=json.dumps({"root": "custom", "path": "deck.pptx"}), headers={"Content-Type": "application/json"})
        self.assertEqual(status, 202)
        job = json.loads(body)
        self.assertEqual(job["status"], "error")
        self.assertIn("LibreOffice", job["error"])
        self.assertIn("pdftoppm", job["error"])
        status, _, body = self.request("/api/presentations/" + job["id"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["id"], job["id"])
        status, _, _ = self.request(f"/api/presentations/{job['id']}/pages/1")
        self.assertEqual(status, 404)

    def test_presentation_request_validation(self):
        for body, headers, expected in (("{}", {}, 415), ("{", {"Content-Type": "application/json"}, 400), (json.dumps({"root": "custom", "path": "video.mp4"}), {"Content-Type": "application/json"}, 400)):
            status, _, _ = self.request("/api/presentations", method="POST", body=body, headers=headers)
            self.assertEqual(status, expected)


class PresentationConversionTests(unittest.TestCase):
    def test_pdf_pages_are_sorted_numerically_and_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.pdf"
            source.write_bytes(b"fake pdf")
            app = WaveBoardApp(web_dir=root, roots=[root])
            identifier = "a" * 32
            app._jobs[identifier] = {"id": identifier, "status": "queued", "pages": []}

            def fake_renderer(command, **options):
                self.assertEqual(command[0], "fake-pdftoppm")
                self.assertNotIn("shell", options)
                output = Path(command[-1]).parent
                (output / "slide-10.png").write_bytes(b"tenth")
                (output / "slide-2.png").write_bytes(b"second")
                (output / "slide-1.png").write_bytes(b"first")
                return type("Result", (), {"returncode": 0})()

            try:
                with patch("waveboard.server.subprocess.run", side_effect=fake_renderer):
                    app._convert_presentation(identifier, source, None, "fake-pdftoppm")
                job = app.presentation_job(identifier)
                self.assertEqual(job["status"], "ready")
                self.assertEqual(len(job["pages"]), 3)
                self.assertEqual((app.jobs_dir / identifier / "page-1.png").read_bytes(), b"first")
                self.assertEqual((app.jobs_dir / identifier / "page-2.png").read_bytes(), b"second")
                self.assertEqual((app.jobs_dir / identifier / "page-3.png").read_bytes(), b"tenth")
            finally:
                app.close()

    def test_failed_converter_sets_error_without_publishing_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.pptx"
            source.write_bytes(b"fake powerpoint")
            app = WaveBoardApp(web_dir=root, roots=[root])
            identifier = "b" * 32
            app._jobs[identifier] = {"id": identifier, "status": "queued", "pages": []}
            try:
                with patch("waveboard.server.subprocess.run", return_value=type("Result", (), {"returncode": 1})()):
                    app._convert_presentation(identifier, source, "fake-office", "fake-pdftoppm")
                job = app.presentation_job(identifier)
                self.assertEqual(job["status"], "error")
                self.assertEqual(job["pages"], [])
                self.assertIn("LibreOffice", job["error"])
            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()
