from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class BuildPluginTests(unittest.TestCase):
    def test_all_platforms_from_another_directory_and_repeated_output(self):
        from build_plugin import build_plugin
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for platform in ('nonebot', 'zhenxun', 'astrbot'):
                first = build_plugin(platform, root=root / platform)
                before = first.read_bytes()
                second = build_plugin(platform, root=root / platform)
                self.assertNotEqual(first.parent, second.parent)
                self.assertEqual(first.read_bytes(), before)
                self.assertTrue(second.is_file())

    @unittest.skipUnless(os.name == 'nt', 'Windows entry points')
    def test_cmd_entries_and_nonzero_failure(self):
        with tempfile.TemporaryDirectory(prefix='farm build ') as temporary:
            root = Path(temporary)
            env = {**os.environ, 'FARM_PYTHON': sys.executable,
                   'FARM_BUILD_NO_PAUSE': '1'}
            for platform in ('nonebot', 'zhenxun', 'astrbot'):
                script = ROOT / f'build_{platform}.cmd'
                result = subprocess.run(
                    ['cmd.exe', '/d', '/c', str(script), '-OutputDirectory',
                     str(root / platform)], cwd=root, env=env,
                    capture_output=True, timeout=120,
                )
                self.assertEqual(result.returncode, 0, result.stdout.decode(
                    errors='replace',
                ) + result.stderr.decode(errors='replace'))
                self.assertEqual(len(list((root / platform).glob('*.zip'))), 1)
            env['FARM_PYTHON'] = str(root / 'not-a-python.exe')
            failed = subprocess.run(
                ['cmd.exe', '/d', '/c', str(ROOT / 'build_astrbot.cmd')],
                cwd=root, env=env, capture_output=True, timeout=30,
            )
            self.assertNotEqual(failed.returncode, 0)
