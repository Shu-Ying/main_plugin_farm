from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_zhenxun import source_identity
from release_metadata import commit_message


class ReleaseMetadataTests(unittest.TestCase):
    def test_multiline_unicode_message_is_bound_to_build_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            def git(*args, message=None):
                return subprocess.check_output(
                    ["git", "-c", "user.name=Farm Test",
                     "-c", "user.email=farm-test@example.invalid", *args],
                    cwd=temporary, input=message, text=True, encoding="utf-8",
                    stderr=subprocess.DEVNULL,
                ).strip()

            git("init", "--quiet")
            original = '修复农场显示\n\n保留正文、引号和 $() 字符。\n第二行。'
            git("commit", "--allow-empty", "--file=-", message=original)
            source = source_identity(temporary)
            self.assertEqual(source["message"], original)
            self.assertEqual(source["commit"], git("rev-parse", "HEAD"))
            git("commit", "--allow-empty", "--file=-", message="后续提交")
            manifest = {"source": source, "version": "2.0.1"}
            expected = (
                original + "\n\nFarm-Source-Commit: " + source["commit"]
                + "\nFarm-Version: 2.0.1"
            )
            self.assertEqual(commit_message(manifest), expected)
            self.assertNotIn("后续提交", commit_message(manifest))

    def test_old_or_invalid_metadata_requires_rebuilding(self):
        for source in ({"commit": "old"}, {"message": " "},
                       {"message": None}, {"message": 123}):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "rebuild"):
                    commit_message({"source": source, "version": "2.0.1"})
