import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_render_assets import export


class RenderExportTests(unittest.TestCase):
    def test_export_preserves_published_land_numbering_and_calibration(self):
        _, metadata = export(ROOT)
        stored = (ROOT / "src/farm_render/data/metadata.json").read_bytes()
        self.assertEqual(json.loads(metadata), json.loads(stored))
        self.assertEqual(metadata, stored)
