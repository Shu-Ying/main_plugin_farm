from dataclasses import replace
from io import BytesIO
import unittest

from PIL import Image

from farm_core import Catalogue
from farm_core.domain import Account, InventoryItem, Plot, Snapshot
from farm_render import FarmRenderer
from farm_render.warehouse import (
    render_warehouse, warehouse_page, warehouse_rows, warehouse_text,
)


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = Catalogue.bundled()
        self.carrot = self.catalogue.get('胡萝卜')
        self.berry = self.catalogue.get('草莓')
        self.snapshot = Snapshot(Account('仓库', 500, 0, 0), (
            InventoryItem('草莓', 3, 8, True, self.berry.plant_id),
            InventoryItem('胡萝卜', 2, 10, False, self.carrot.plant_id),
            InventoryItem('零库存', 0, 0, False, 999999),
        ), (Plot(1), Plot(2)))

    def test_separate_positive_stocks_groups_and_exclude_locked_value(self):
        crops = warehouse_rows(self.snapshot, self.catalogue, 'crops')
        self.assertEqual([r.group for r in crops], ['可出售', '已锁定'])
        text = warehouse_text(crops, self.snapshot, 'crops', 1, 1)
        self.assertIn(f'可出售价值 {10*self.carrot.price:,}', text)
        self.assertIn('胡萝卜（#1） 10个', text)
        self.assertNotIn('零库存', text)
        seeds = warehouse_rows(self.snapshot, self.catalogue, 'seeds')
        self.assertEqual([r.group for r in seeds], ['单季种子', '多季种子'])
        self.assertEqual([r.quantity for r in seeds], [2, 3])
        self.assertIn('当前空地 2/2块', warehouse_text(
            seeds, self.snapshot, 'seeds', 1, 1,
        ))

    def test_pagination_preserves_ids_and_unknown_directory_is_not_zero(self):
        items = tuple(InventoryItem('未知', 1, 2, False, i)
                      for i in range(9000, 9025))
        snapshot = replace(self.snapshot, inventory=items)
        rows = warehouse_rows(snapshot, self.catalogue, 'seeds')
        self.assertEqual([r.plant_id for r in warehouse_page(rows, 2)[0]],
                         list(range(9012, 9024)))
        self.assertEqual(warehouse_page(rows, 3)[1], 3)
        self.assertEqual(rows[0].group, '信息缺失')
        for page in (0, 4, True):
            with self.assertRaises(ValueError):
                warehouse_page(rows, page)
        crops = warehouse_rows(snapshot, self.catalogue, 'crops')
        self.assertIn('不含目录缺失项', warehouse_text(
            crops, snapshot, 'crops', 1, 3,
        ))

    def test_empty_stock_and_no_snapshot_mutation(self):
        snapshot = replace(self.snapshot, inventory=())
        rows = warehouse_rows(snapshot, self.catalogue, 'seeds')
        self.assertEqual(warehouse_page(rows, 1), ((), 1))
        self.assertIn('种子商店', warehouse_text(
            rows, snapshot, 'seeds', 1, 1,
        ))
        self.assertEqual(snapshot.inventory, ())

    def test_render_crops_and_seeds_as_compressed_jpeg(self):
        from scripts.ci_font import choose_font
        renderer = FarmRenderer(choose_font())
        for kind in ('crops', 'seeds'):
            rows = warehouse_rows(self.snapshot, self.catalogue, kind)
            content = render_warehouse(renderer, rows, self.snapshot,
                                       kind, 1, 1)
            with Image.open(BytesIO(content)) as image:
                self.assertEqual(image.format, 'JPEG')
                self.assertEqual(image.size, (1024, 1536))
            self.assertLess(len(content), 500000)
