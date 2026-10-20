import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DataDirectoryTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            'farm_data_paths', ROOT / 'integrations/zhenxun/data_paths.py',
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_default_and_explicit_directory(self):
        self.assertEqual(self.module.data_directories(self.base), (
            self.base / 'farm_db', self.base / 'farm_preview',
        ))
        custom = self.base / 'custom'
        self.assertEqual(self.module.data_directories(self.base, custom), (
            custom, None,
        ))

    def test_migrate_preserves_database_log_and_sidecars(self):
        old = self.base / 'farm_preview'
        old.mkdir()
        for name in ('farm-preview.sqlite3', 'farm-preview.sqlite3-wal',
                     'farm-preview.log'):
            (old / name).write_bytes(name.encode())
        target = self.base / 'farm_db'
        self.assertTrue(self.module.prepare_directory(target, old))
        self.assertFalse(old.exists())
        for path in target.iterdir():
            self.assertEqual(path.read_bytes(), path.name.encode())
        self.assertFalse(self.module.prepare_directory(target, old))

    def test_conflicting_directory_stops_without_overwrite(self):
        old, target = self.base / 'farm_preview', self.base / 'farm_db'
        old.mkdir()
        target.mkdir()
        (old / 'farm-preview.sqlite3').write_bytes(b'old')
        (target / 'farm-preview.sqlite3').write_bytes(b'new')
        with self.assertRaises(FileExistsError):
            self.module.prepare_directory(target, old)
        self.assertEqual((old / 'farm-preview.sqlite3').read_bytes(), b'old')
        self.assertEqual((target / 'farm-preview.sqlite3').read_bytes(), b'new')

    def test_migration_rejects_paths_outside_default_siblings(self):
        with self.assertRaises(ValueError):
            self.module.prepare_directory(
                self.base / 'farm_db', self.base / 'other/farm_preview',
            )

    @unittest.skipUnless(os.name == 'nt', 'Windows short paths only')
    def test_migration_accepts_short_and_long_parent_paths(self):
        import ctypes

        parent = self.base / 'Farm migration long directory'
        parent.mkdir()
        buffer = ctypes.create_unicode_buffer(32768)
        get_short_path = ctypes.windll.kernel32.GetShortPathNameW
        get_short_path.argtypes = (
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
        )
        get_short_path.restype = ctypes.c_uint
        length = get_short_path(str(parent), buffer, len(buffer))
        self.assertTrue(0 < length < len(buffer))
        short_parent = Path(buffer.value)
        if short_parent == parent.resolve():
            self.skipTest('Short path aliases are disabled on this volume')
        old = short_parent / 'farm_preview'
        old.mkdir()
        (old / 'farm-preview.sqlite3').write_bytes(b'preserved')
        target = parent.resolve() / 'farm_db'
        self.assertTrue(self.module.prepare_directory(target, old))
        self.assertEqual((target / 'farm-preview.sqlite3').read_bytes(),
                         b'preserved')
        self.assertFalse(old.exists())
