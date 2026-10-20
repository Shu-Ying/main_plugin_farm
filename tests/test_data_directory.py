import importlib.util
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
