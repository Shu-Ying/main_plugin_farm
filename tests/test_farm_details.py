from dataclasses import replace
from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ci_font import choose_font
from farm_core import Catalogue, Identity
from farm_core.domain import Account, Plot, Snapshot, boosted
from farm_render import FarmRenderer
from farm_render.details import detail_rows, render_details


class DetailTests(unittest.TestCase):
    def setUp(self):
        self.renderer = FarmRenderer(choose_font())
        self.plant = Catalogue.bundled().get('草莓')
        self.who = Identity('test', 'local', 'qq', 'details')

    def snapshot(self, plots):
        return Snapshot(Account('详述演示', 500, 0, 0), (), tuple(plots))

    def test_frozen_maturity_loss_survives_clearing_and_integer_rounding(self):
        plot = Plot(1, self.plant, 100, yield_bonus=10,
                    pest_count=0, pest_spawned=3, maturity_pests=3)
        rows, pages = detail_rows(self.renderer, self.who,
                                 self.snapshot([plot]), 200, 1)
        self.assertEqual(pages, 1)
        self.assertEqual(rows[0].amount,
                         boosted(self.plant.harvest, 10)*85//100)
        self.assertEqual(rows[0].state, '已成熟')
        self.assertIn('15%', rows[0].pest_note)
        self.assertIn('成熟时', rows[0].pest_note)

    def test_current_pests_and_season_boundary_empty_withered_pagination(self):
        plot = Plot(1, self.plant, 1000, pest_count=2, pest_spawned=2)
        rows, _ = detail_rows(self.renderer, self.who,
                             self.snapshot([plot]), 200, 1)
        self.assertEqual(rows[0].amount, self.plant.harvest*90//100)
        self.assertIn('预计', rows[0].pest_note)
        data = self.snapshot([Plot(i) for i in range(1, 12)] + [
            replace(plot, slot=12, harvest_count=self.plant.crop),
        ])
        rows, pages = detail_rows(self.renderer, self.who, data, 200, 2)
        self.assertEqual(pages, 2)
        self.assertEqual([r.slot for r in rows], [11, 12])
        self.assertIsNone(rows[0].amount)
        self.assertEqual(rows[1].state, '已枯萎')
        self.assertIsNone(rows[1].amount)
        with self.assertRaises(ValueError):
            detail_rows(self.renderer, self.who, data, 200, 3)

    def test_render_full_farm_and_table(self):
        data = self.snapshot([Plot(1, self.plant, 100)])
        result = render_details(self.renderer, self.who, data, 200, 1,
                                'autumn', 'PNG')
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.width, 1024)
            self.assertGreater(image.height, 624)
