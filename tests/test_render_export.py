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
        data = json.loads(metadata)
        self.assertEqual(len(data['plants']), 202)
        self.assertEqual(len(data['positions']), 30)
        self.assertEqual(data['placement']['mode'], 'visible_contact_center')
        self.assertEqual(metadata, export(ROOT)[1])
