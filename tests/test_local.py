import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from waveboard.local import LocalWorkspace
from waveboard.server import APIError, WaveBoardApp


class LocalWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "device"
        self.root.mkdir()
        self.web = Path(self.temp.name) / "web"
        self.web.mkdir()
        (self.web / "index.html").write_text("WaveBoard")
        self.app = WaveBoardApp(self.web, [self.root])
        self.addCleanup(self.app.close)
        self.local = LocalWorkspace(self.app)

    def test_operations_do_not_create_a_server_or_socket(self):
        with patch("socket.socket", side_effect=AssertionError("No hosting allowed")):
            self.assertEqual(self.local.request("/api/roots")["roots"][0]["id"], "custom")
            self.assertEqual(self.local.request("/api/files?root=custom")["entries"], [])
            self.assertEqual(self.local.resource("waveboard://app/index.html").read_text(), "WaveBoard")

    def test_resources_cannot_escape_roots_or_load_remote_content(self):
        outside = Path(self.temp.name) / "private.txt"
        outside.write_text("private")
        (self.root / "escape").symlink_to(outside)
        for url in ["https://example.com/file", "waveboard://other/index.html", "waveboard://app/../private.txt", "waveboard://app/api/file?root=custom&path=escape"]:
            with self.subTest(url=url), self.assertRaises(APIError):
                self.local.resource(url)

    def test_import_preserves_existing_files_and_cleans_failed_copy(self):
        source = Path(self.temp.name) / "sample.txt"
        source.write_text("original")
        url = "/api/upload?root=custom"
        result = self.local.import_file(url, source)
        self.assertEqual(result["entry"]["name"], "sample.txt")
        with self.assertRaises(APIError):
            self.local.import_file(url, source)
        self.assertEqual((self.root / "sample.txt").read_text(), "original")
        source2 = Path(self.temp.name) / "failed.txt"
        source2.write_text("copy")
        with patch("waveboard.local.shutil.copyfileobj", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.local.import_file(url, source2)
        self.assertFalse((self.root / "failed.txt").exists())

    def test_demo_import_is_read_only(self):
        demo = self.web / "assets/demo"
        demo.mkdir(parents=True)
        source = self.root / "sample.txt"
        source.write_text("sample")
        with self.assertRaises(APIError):
            self.local.import_file("/api/upload?root=demo", source)

    def test_presentation_uses_local_conversion_and_restricts_page_access(self):
        (self.root / "slides.pdf").write_bytes(b"%PDF")
        with patch.object(self.app._executor, "submit"):
            job = self.local.request("/api/presentations", "POST", {"root": "custom", "path": "slides.pdf"})
        self.assertEqual(self.local.request("/api/presentations/" + job["id"])["id"], job["id"])
        with self.assertRaises(APIError):
            self.local.resource(f"waveboard://app/api/presentations/{job['id']}/pages/1")
        with self.assertRaises(APIError):
            self.local.request("/api/presentations", "POST", {"root": "custom", "path": "../slides.pdf"})


if __name__ == "__main__":
    unittest.main()
