import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_nonebot import build
from publish_nonebot import publish
from verify_nonebot import MANIFEST, ROOT_NAME, read_package, verify_files


class NoneBotPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = build(ROOT, self.root / "built")
        self.files = read_package(self.bundle)

    def test_reproducible_standard_package_and_shared_runtime(self):
        other = build(ROOT, self.root / "second")
        self.assertEqual(self.bundle.read_bytes(), other.read_bytes())
        self.assertEqual(self.files["nonebot_plugin_farm/runtime.py"], (
            ROOT / "integrations/shared/runtime.py"
        ).read_bytes())
        for suffix in ("farm_core/data/plants.json",
                       "farm_render/data/asset-manifest.json",
                       "farm_render/data/font-manifest.json",
                       "farm_render/data/OFL-Xiaolai.txt"):
            self.assertTrue(any(name.endswith(suffix) for name in self.files))
        self.assertEqual(verify_files(self.files)["target"], "nonebot")
        self.assertFalse(any(name.endswith('.ttf') for name in self.files))
        for name in ("font-manifest.json", "OFL-Xiaolai.txt"):
            self.assertEqual(
                self.files[
                    "nonebot_plugin_farm/_vendor/farm_render/data/" + name
                ],
                (ROOT / "src/farm_render/data" / name).read_bytes(),
            )
        self.assertIn("pyproject.toml", self.files)
        self.assertIn(".github/workflows/publish.yaml", self.files)
        self.assertFalse(any("legacy/" in name for name in self.files))
        self.assertFalse(any(name.endswith('/assets.zip')
                             for name in self.files))
        with self.assertRaises(FileExistsError):
            build(ROOT, self.root / "built")

    def test_host_entry_has_no_zhenxun_import(self):
        import ast
        for name, content in self.files.items():
            if not name.endswith(".py"):
                continue
            tree = ast.parse(content, feature_version=(3, 10))
            for node in ast.walk(tree):
                imports = ([node.module] if isinstance(node, ast.ImportFrom)
                           else [alias.name for alias in node.names]
                           if isinstance(node, ast.Import) else [])
                self.assertFalse(any(
                    value and value.startswith(("zhenxun", "zhenxun_utils"))
                    for value in imports
                ), name)

    def test_tampering_and_paths_rejected(self):
        files = dict(self.files)
        files["pyproject.toml"] += b"# changed\n"
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify_files(files)
        for path in ("../escape", "extra", "C:/escape", "..\\escape"):
            bundle = self.root / "bad.zip"
            bundle.write_bytes(self.bundle.read_bytes())
            with ZipFile(bundle, "a") as archive:
                archive.writestr(path, b"invalid")
            with self.assertRaises(ValueError):
                read_package(bundle)

    def clean_package(self):
        files = dict(self.files)
        manifest = json.loads(files[MANIFEST])
        manifest["source"]["dirty"] = False
        files[MANIFEST] = json.dumps(manifest).encode()
        bundle = self.root / "clean.zip"
        with ZipFile(bundle, "w") as archive:
            for name, content in files.items():
                archive.writestr(f"{ROOT_NAME}/{name}", content)
        return bundle, manifest

    def test_default_publish_is_offline_and_dirty_source_is_rejected(self):
        def forbidden(*args):
            self.fail("dry-run must not make requests")

        report = publish(self.bundle, request=forbidden)
        self.assertFalse(report["published"])
        self.assertEqual(report["repository"], "Shu-Ying/nonebot_plugin_farm")
        self.assertEqual(report["branch"], "main")
        bundle, manifest = self.clean_package()
        manifest["source"]["dirty"] = True
        self.files[MANIFEST] = json.dumps(manifest).encode()
        with ZipFile(bundle, "w") as archive:
            for name, content in self.files.items():
                archive.writestr(f"{ROOT_NAME}/{name}", content)
        with self.assertRaisesRegex(ValueError, "clean source"):
            publish(bundle, True, forbidden)

    def test_fixed_sync_preserves_history_and_includes_pypi_workflow(self):
        bundle, manifest = self.clean_package()
        calls = []

        def request(method, path, data):
            calls.append((method, path, data))
            if path == "":
                return {"default_branch": "main"}
            if path.startswith("git/ref/"):
                return {"object": {"sha": "existing"}}
            if path.startswith("contents/"):
                return None
            return {"sha": "generated"}

        with patch.dict("os.environ", {"FARM_RELEASE_TOKEN": "test-token"}):
            self.assertTrue(publish(bundle, True, request)["published"])
        tree = next(data for method, path, data in calls
                    if path == "git/trees")
        self.assertEqual({entry["path"] for entry in tree["tree"]},
                         set(self.files))
        commit = next(data for method, path, data in calls
                      if path == "git/commits")
        self.assertEqual(commit["parents"], ["existing"])
        self.assertEqual(commit["message"], (
            manifest["source"]["message"] + "\n\n"
            + "Farm-Source-Commit: " + manifest["source"]["commit"] + "\n"
            + "Farm-Version: " + manifest["version"]
        ))
        self.assertIn(("PATCH", "git/refs/heads/main", {
            "sha": "generated", "force": False,
        }), calls)

    def test_wrong_owner_and_concurrent_change_are_rejected(self):
        bundle, manifest = self.clean_package()
        for wrong_owner in (True, False):
            calls = []

            def request(method, path, data):
                calls.append((method, path, data))
                if path == "":
                    return {"default_branch": "main"}
                if path.startswith("contents/"):
                    previous = {**manifest, "target": (
                        "zhenxun" if wrong_owner else "nonebot"
                    )}
                    return {"encoding": "base64", "content": base64.b64encode(
                        json.dumps(previous).encode(),
                    ).decode()}
                if method == "GET":
                    reads = sum(p.startswith("git/ref/") for _, p, _ in calls)
                    return {"object": {"sha": (
                        "existing" if reads == 1 else "changed"
                    )}}
                return {"sha": "generated"}

            with patch.dict("os.environ", {"FARM_RELEASE_TOKEN": "test"}):
                with self.assertRaises((ValueError, RuntimeError)):
                    publish(bundle, True, request)
            self.assertFalse(any(method == "PATCH" for method, _, _ in calls))
