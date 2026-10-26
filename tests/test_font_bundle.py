import hashlib
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from farm_render import font_bundle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ci_font import choose_font


class FontBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = Path(choose_font()).read_bytes()
        cls.license = (ROOT / "src/farm_render/data/OFL-Xiaolai.txt").read_bytes()
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("Xiaolai-Regular.ttf", cls.font)
            archive.writestr("OFL-Xiaolai.txt", cls.license)
        cls.archive = output.getvalue()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        manifest = font_bundle.expected_manifest()
        manifest.update(
            sha256=hashlib.sha256(self.archive).hexdigest(),
            size_bytes=len(self.archive),
        )
        self.manifest = manifest
        patcher = patch.object(font_bundle, "expected_manifest",
                               return_value=manifest)
        patcher.start()
        self.addCleanup(patcher.stop)

    def download(self, url, destination, limit):
        self.assertEqual(limit, len(self.archive))
        destination.write(self.archive)

    def test_service_download_cache_and_license_repair(self):
        with patch.object(font_bundle, "_copy_remote",
                          side_effect=self.download) as fetch:
            path = font_bundle.ensure_font(
                self.root, "farm_service", "https://farm.example/prefix/",
            )
            self.assertEqual(fetch.call_args.args[0],
                "https://farm.example/prefix/v1/fonts/"
                + self.manifest["sha256"] + "/assets.zip")
            self.assertEqual(path.read_bytes(), self.font)
            license_path = path.with_name("OFL-Xiaolai.txt")
            self.assertEqual(license_path.read_bytes(), self.license)
            path.write_bytes(b"corrupt")
            license_path.unlink()
            font_bundle.ensure_font(self.root)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(path.read_bytes(), self.font)
            self.assertEqual(license_path.read_bytes(), self.license)

    def test_corrupt_download_leaves_no_font_or_partial(self):
        def corrupt(url, destination, limit):
            destination.write(b"bad")
        with patch.object(font_bundle, "_copy_remote", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "SHA256"):
                font_bundle.ensure_font(self.root)
        self.assertFalse(list(self.root.rglob("*.ttf")))
        self.assertFalse(list(self.root.rglob("*.download")))

    def test_mirrors_follow_selected_resource_source(self):
        for source in ("Github", "Gitea"):
            with patch.object(font_bundle, "_copy_remote",
                              side_effect=self.download) as fetch:
                font_bundle.ensure_font(self.root / source, source)
                self.assertEqual(fetch.call_args.args[0],
                    self.manifest["sources"][source.lower()])
