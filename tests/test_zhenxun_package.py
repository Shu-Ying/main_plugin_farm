import importlib.util
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from build_zhenxun import build
    from install_zhenxun import install
    from verify_zhenxun import verify_package
except ImportError:
    build = None


class PublisherRequestTests(unittest.TestCase):
    def test_repository_url_has_no_trailing_slash(self):
        from publish_zhenxun import github
        with patch("publish_zhenxun.urlopen") as opened:
            opened.return_value.__enter__.return_value.read.return_value = (
                b'{"default_branch": "main"}'
            )
            self.assertEqual(github("GET", "", None, "test-token"), {
                "default_branch": "main",
            })
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url,
                         "https://api.github.com/repos/"
                         "Shu-Ying/zhenxun_plugin_farm")

    def test_repository_404_is_not_treated_as_missing_branch(self):
        from publish_zhenxun import github
        error = HTTPError("https://api.github.com", 404, "Not Found",
                          {}, None)
        with patch("publish_zhenxun.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
                github("GET", "", None, "test-token")

    def test_optional_resource_404_returns_none(self):
        from publish_zhenxun import github
        error = HTTPError("https://api.github.com", 404, "Not Found",
                          {}, None)
        with patch("publish_zhenxun.urlopen", side_effect=error):
            self.assertIsNone(github(
                "GET", "git/ref/heads/farm-preview", None, "test-token",
                allow_missing=True,
            ))


class ZhenxunPackageTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build, "真寻打包功能未实现")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "bundle"
        self.bundle = build(ROOT, self.output)

    def test_reproducible_private_complete_package(self):
        other = build(ROOT, self.root / "second")
        self.assertEqual(self.bundle.read_bytes(), other.read_bytes())
        manifest = verify_package(self.bundle)
        self.assertEqual(manifest["target"], "zhenxun")
        self.assertEqual(manifest["version"],
                         (ROOT / "version.txt").read_text().strip())
        self.assertIn("dirty", manifest["source"])
        with ZipFile(self.bundle) as archive:
            paths = archive.namelist()
            self.assertFalse(any(p.endswith("assets.zip") for p in paths))
            self.assertTrue(any(p.endswith('asset-manifest.json')
                                for p in paths))
            self.assertFalse(any("astrbot" in p or "legacy/" in p
                                 for p in paths))
            source = archive.read(next(
                p for p in paths if p.endswith("farm_render/models.py")
            )).decode()
            self.assertIn("from ..farm_core.domain", source)
            self.assertNotIn("from farm_core.domain", source)
        with self.assertRaises(FileExistsError):
            build(ROOT, self.output)

    def test_install_and_existing_target_are_safe(self):
        plugins = self.root / "plugins"
        plugins.mkdir()
        target = install(self.bundle, plugins)
        sentinel = target / "do-not-overwrite.txt"
        sentinel.write_text("preserved")
        with self.assertRaises(FileExistsError):
            install(self.bundle, plugins)
        self.assertEqual(sentinel.read_text(), "preserved")
        self.assertTrue((target / "__init__.py").is_file())

    def test_readme_image_is_in_repository_archive_and_manifest(self):
        expected = (ROOT / "images/farm-preview.png").read_bytes()
        relative = "images/farm-preview.png"
        self.assertEqual(
            (self.output / "repository" / relative).read_bytes(), expected,
        )
        manifest = verify_package(self.bundle)
        self.assertIn(relative, manifest["files"])
        with ZipFile(self.bundle) as archive:
            self.assertEqual(archive.read(
                f"zhenxun_plugin_farm_preview/{relative}",
            ), expected)

    def test_tampering_extra_path_and_traversal_rejected(self):
        for name in ("../outside.txt", "C:/escape.txt", "extra.txt",
                     "..\\outside.txt"):
            with self.subTest(name=name):
                bad = self.root / (str(len(name)) + ".zip")
                bad.write_bytes(self.bundle.read_bytes())
                with ZipFile(bad, "a") as archive:
                    archive.writestr(name, "bad")
                with self.assertRaises(ValueError):
                    verify_package(bad)
        bad = self.root / "corrupt.zip"
        with ZipFile(self.bundle) as original, ZipFile(bad, "w") as changed:
            for item in original.infolist():
                content = original.read(item.filename)
                if item.filename.endswith("requirements.txt"):
                    content += b"bad\n"
                changed.writestr(item, content)
        with self.assertRaises(ValueError):
            install(bad, self.root)
        self.assertFalse((self.root / "zhenxun_plugin_farm_preview").exists())

    def test_publisher_is_fixed_target_and_dry_by_default(self):
        from publish_zhenxun import publish
        report = publish(self.bundle)
        self.assertFalse(report["published"])
        self.assertEqual(report["branch"], "main")
        self.assertEqual(report["repository"], "Shu-Ying/zhenxun_plugin_farm")
        self.assertNotIn("token", json.dumps(report))
        from build_zhenxun import read_version
        for value in ("bad; echo secret", "", "1.0.0\n2.0.0"):
            with self.subTest(value=value):
                (self.root / "version.txt").write_text(value)
                with self.assertRaises(ValueError):
                    read_version(self.root)

    def test_version_file_controls_package_version(self):
        from build_zhenxun import read_version
        (self.root / "version.txt").write_text("1.2.3-preview.4\n")
        self.assertEqual(read_version(self.root), "1.2.3-preview.4")
        with patch("build_zhenxun.read_version",
                   return_value="1.2.3-preview.4"):
            bundle = build(ROOT, self.root / "versioned")
        self.assertTrue(bundle.name.endswith("-1.2.3-preview.4.zip"))
        self.assertEqual(verify_package(bundle)["version"], "1.2.3-preview.4")
        with ZipFile(bundle) as archive:
            self.assertEqual(archive.read(
                "zhenxun_plugin_farm_preview/_version.py",
            ), b'__version__ = "1.2.3-preview.4"\n')

    def clean_package(self):
        from verify_zhenxun import read_package, MANIFEST, ROOT_NAME
        files = read_package(self.bundle)
        manifest = json.loads(files[MANIFEST])
        manifest["source"]["dirty"] = False
        files[MANIFEST] = json.dumps(manifest).encode()
        path = self.root / "clean.zip"
        with ZipFile(path, "w") as archive:
            for name, content in files.items():
                archive.writestr(f"{ROOT_NAME}/{name}", content)
        return path, manifest

    def test_publish_uses_nonforced_managed_branch_and_rejects_race(self):
        from publish_zhenxun import publish
        package, manifest = self.clean_package()
        for race in (False, True):
            calls = []
            reads = []

            def request(method, path, data):
                calls.append((method, path, data))
                if path == "":
                    return {"default_branch":"main"}
                if path.startswith("contents/"):
                    return {"encoding":"base64", "content":base64.b64encode(
                        json.dumps(manifest).encode(),
                    ).decode()}
                if method == "GET":
                    reads.append(1)
                    return {"object":{"sha":(
                        "raced" if race and len(reads) > 1 else "parent"
                    )}}
                return {"sha":"created"}

            with patch.dict("os.environ", {"FARM_RELEASE_TOKEN":"unit-test"}):
                if race:
                    with self.assertRaises(RuntimeError):
                        publish(package, True, request)
                    self.assertFalse(any(c[0] == "PATCH" for c in calls))
                else:
                    self.assertTrue(publish(
                        package, True, request,
                    )["published"])
                    self.assertIn(("PATCH", "git/refs/heads/main", {
                        "sha":"created", "force":False,
                    }), calls)

    def test_publish_creates_missing_preview_branch(self):
        from publish_zhenxun import publish
        package, _ = self.clean_package()
        calls = []

        def request(method, path, data):
            calls.append((method, path, data))
            if path == "":
                return {"default_branch": "main"}
            if method == "GET":
                return None
            return {"sha": "created"}

        with patch.dict("os.environ", {"FARM_RELEASE_TOKEN": "unit-test"}):
            self.assertTrue(publish(package, True, request)["published"])
        self.assertIn(("POST", "git/refs", {
            "ref": "refs/heads/main", "sha": "created",
        }), calls)
        self.assertFalse(any(c[0] == "PATCH" for c in calls))

    def test_inaccessible_repository_has_distinct_error(self):
        from publish_zhenxun import publish
        package, _ = self.clean_package()
        with patch.dict("os.environ", {"FARM_RELEASE_TOKEN": "unit-test"}):
            with self.assertRaisesRegex(ValueError, "not accessible"):
                publish(package, True, lambda *args: None)

    def test_publish_replaces_unmanaged_main_and_preserves_history(self):
        from publish_zhenxun import publish
        from verify_zhenxun import read_package
        package, _ = self.clean_package()
        calls = []

        def unmanaged(method, path, data):
            calls.append((method, path, data))
            if path == "":
                return {"default_branch": "main"}
            if path.startswith("git/ref/"):
                return {"object": {"sha": "existing"}}
            if path.startswith("contents/"):
                return None
            return {"sha": "created"}

        with patch.dict("os.environ", {"FARM_RELEASE_TOKEN": "unit-test"}):
            self.assertTrue(publish(package, True, unmanaged)["published"])
        tree = next(data for method, path, data in calls
                    if method == "POST" and path == "git/trees")
        self.assertNotIn("base_tree", tree)
        self.assertEqual({entry["path"] for entry in tree["tree"]},
                         set(read_package(package)))
        commit = next(data for method, path, data in calls
                      if method == "POST" and path == "git/commits")
        self.assertEqual(commit["parents"], ["existing"])
        manifest = json.loads(read_package(package)["FARM-MANIFEST.json"])
        self.assertEqual(commit["message"], (
            manifest["source"]["message"] + "\n\n"
            + "Farm-Source-Commit: " + manifest["source"]["commit"] + "\n"
            + "Farm-Version: " + manifest["version"]
        ))
        self.assertIn(("PATCH", "git/refs/heads/main", {
            "sha": "created", "force": False,
        }), calls)

    def test_symlink_and_duplicate_rejected(self):
        from zipfile import ZipInfo
        for kind in ("duplicate", "link"):
            bad = self.root / (kind + ".zip")
            bad.write_bytes(self.bundle.read_bytes())
            with ZipFile(bad, "a") as archive:
                item = ZipInfo("zhenxun_plugin_farm_preview/extra")
                if kind == "duplicate":
                    item.filename = archive.namelist()[0]
                else:
                    item.create_system = 3
                    item.external_attr = 0o120777 << 16
                archive.writestr(item, b"outside")
            with self.assertRaises(ValueError):
                verify_package(bad)
