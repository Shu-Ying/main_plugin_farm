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
        self.assertEqual(
            self.module.data_directory(self.base), self.base / 'farm_db',
        )
        custom = self.base / 'custom'
        self.assertEqual(self.module.data_directory(self.base, custom), custom)
