from dataclasses import replace
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ci_font import choose_font
from farm_core import Catalogue
from farm_core.domain import Account
from farm_render import FarmRenderer
from farm_render.shop import shop_page, render_shop
from farm_render.canvas import Canvas


class ShopRenderTests(unittest.TestCase):
    def test_pages_filter_unavailable_and_keep_stable_ids(self):
        plant = Catalogue.bundled().get('胡萝卜')
        plants = [replace(plant, plant_id=i) for i in range(1, 9)]
        plants += [replace(plant, plant_id=99, purchasable=False)]
        rows, total = shop_page(plants, 2)
        self.assertEqual(total, 2)
        self.assertEqual([p.plant_id for p in rows], [7, 8])
        for page in (0, 3, True):
            with self.assertRaises(ValueError):
                shop_page(plants, page)
        self.assertEqual(shop_page([], 1), ((), 1))

    def test_shop_uses_actual_fields_and_missing_icon_fallback(self):
        renderer = FarmRenderer(choose_font())
        plant = Catalogue.bundled().get('胡萝卜')
        rows = (plant, replace(plant, plant_id=99999,
                              name='不存在的素材', is_vip=True, vip_buy=35))
        with patch.object(Canvas, 'text', autospec=True) as text:
            result = render_shop(
                renderer, rows, Account('商店', 12580, 36, 0), 1, 1,
            )
        labels = [call.args[2] for call in text.call_args_list]
        self.assertIn(f'{plant.cost:,} 农场币 / 粒', labels)
        self.assertIn('35 点券 / 粒', labels)
        self.assertIn('暂无图', labels)
        self.assertIn(f'按编号：购买种子 #{plant.plant_id} 5', labels)
        self.assertIn('按名称：购买种子 胡萝卜 5', labels)
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.size, (1024, 1536))
            self.assertEqual(image.format, 'PNG')
