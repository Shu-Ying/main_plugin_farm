import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from format_generated import format_generated


class FormatGeneratedTests(unittest.TestCase):
    def test_formats_sorts_and_is_idempotent_without_changing_assets(self):
        files = {
            "package/main.py": (
                b"import sys\r\nimport os\r\n\r\n"
                b"def run( ):\r\n  return 'ok',os.name,sys.version\r\n"
            ),
            "images/example.png": b"unchanged binary\x00",
        }
        format_generated(ROOT, files)
        source = files["package/main.py"]
        self.assertTrue(source.startswith(b"import os\nimport sys\n"))
        self.assertIn(b'    return "ok", os.name, sys.version\n', source)
        self.assertNotIn(b"\r", source)
        ast.parse(source, feature_version=(3, 10))
        self.assertEqual(files["images/example.png"], b"unchanged binary\x00")
        first = files.copy()
        format_generated(ROOT, files)
        self.assertEqual(files, first)

    def test_ruff_failure_does_not_partially_update_file_collection(self):
        files = {"good.py": b"x=1\n", "bad.py": b"def broken(:\n"}
        before = files.copy()
        with self.assertRaisesRegex(RuntimeError, "failed Ruff"):
            format_generated(ROOT, files)
        self.assertEqual(files, before)

    def test_rejects_unsafe_paths_and_missing_ruff(self):
        for name in ("../outside.py", "C:/outside.py", "/outside.py"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    format_generated(ROOT, {name: b"x=1\n"})
        with patch(
            "format_generated.importlib.util.find_spec", return_value=None
        ):
            with self.assertRaisesRegex(RuntimeError, "requirements-build"):
                format_generated(ROOT, {"main.py": b"x=1\n"})
