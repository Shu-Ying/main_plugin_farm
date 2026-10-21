from pathlib import Path
import sys
import unittest

from PIL import Image

from farm_render.placement import ground_contact, place_sprite

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from export_render_assets import fit_grid


class SceneTransformTests(unittest.TestCase):
    def test_visible_base_ignores_canvas_padding_and_top_heavy_foliage(self):
        image = Image.new('RGBA', (120, 200))
        image.paste((0, 255, 0, 255), (5, 5, 115, 45))
        image.paste((120, 70, 30, 255), (70, 80, 90, 100))
        x, y = ground_contact(image)
        self.assertEqual(x, 80)
        self.assertEqual(y, 90.5)
        padded = Image.new('RGBA', (160, 300))
        padded.paste(image, (20, 30))
        self.assertEqual(ground_contact(padded), (x+20, y+30))
        self.assertEqual(ground_contact(Image.new('RGBA', (10, 20))), (5, 10))

    def test_affine_fit_recovers_scale_rotation_and_shear(self):
        source = [(i % 6 * 70, i // 6 * 40) for i in range(30)]
        target = [(3*x+.2*y+600, .1*x-2*y+400) for x, y in source]
        transform, errors = fit_grid(source, target)
        for actual, expected in zip(sum(transform, []), (3, .2, .1, -2)):
            self.assertAlmostEqual(actual, expected)
        self.assertLess(errors['maximum'], 1e-8)
        target[0], target[-1] = target[-1], target[0]
        with self.assertRaises(ValueError):
            fit_grid(source, target)

    def test_transparent_margin_is_preserved_and_pivot_maps_to_parent(self):
        image = Image.new('RGBA', (20, 40))
        image.paste((255, 0, 0, 255), (8, 8, 12, 12))
        result, xy = place_sprite(
            image, (100, 100), (0, -10), (.5, 1), 1,
            ((2, 0), (0, -2)), 1,
        )
        self.assertEqual(result.size, (40, 80))
        self.assertEqual(xy, (80, 40))
        self.assertEqual(result.getpixel((20, 20)), (255, 0, 0, 255))
        self.assertEqual(result.getpixel((20, 70))[3], 0)

    def test_zero_transform_is_rejected(self):
        with self.assertRaises(ValueError):
            place_sprite(Image.new('RGBA', (5, 5)), (0, 0), (0, 0),
                         (.5, 1), 1, ((0, 0), (0, 0)), 1)
