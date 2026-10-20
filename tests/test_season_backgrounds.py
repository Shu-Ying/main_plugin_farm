from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from farm_core import Identity
from farm_core.domain import Account, Plot, Snapshot
from farm_render import FarmRenderer, RenderOptions

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ci_font import choose_font


class SeasonBackgroundTests(unittest.TestCase):
    def test_calendar_uses_beijing_time_and_month_boundaries(self):
        from farm_render.seasons import season_for

        cases = (
            ("2026-02-28T15:59:59", "winter"),
            ("2026-02-28T16:00:00", "spring"),
            ("2026-05-31T15:59:59", "spring"),
            ("2026-05-31T16:00:00", "summer"),
            ("2026-08-31T16:00:00", "autumn"),
            ("2026-11-30T16:00:00", "winter"),
            ("2026-12-31T16:00:00", "winter"),
        )
        for value, expected in cases:
            utc = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            self.assertEqual(season_for(int(utc.timestamp())), expected)

    def test_every_theme_has_nine_decorations_and_known_fallbacks(self):
        renderer = FarmRenderer(choose_font())
        layouts = renderer.assets.metadata["decorations"]
        for theme in ("default", "spring", "summer", "autumn", "winter", "bee"):
            self.assertEqual(len(layouts[theme]), 9)
            self.assertEqual(RenderOptions(theme=theme).theme, theme)
            for item in layouts[theme]:
                self.assertIn(item["sprite"], renderer.assets.metadata["images"])
        spring_mail = layouts["spring"][6]
        autumn_workshop = layouts["autumn"][7]
        self.assertEqual(spring_mail["source_theme"], "default")
        self.assertEqual(autumn_workshop["source_theme"], "default")

    def test_shorter_house_keeps_ground_baseline_and_aspect_ratio(self):
        renderer = FarmRenderer(choose_font())
        layouts = renderer.assets.metadata["decorations"]
        spring, winter = layouts["spring"][0], layouts["winter"][0]
        self.assertAlmostEqual(
            spring["position"][1] + spring["size"][1],
            winter["position"][1] + winter["size"][1], places=5,
        )
        self.assertAlmostEqual(winter["size"][0] / winter["size"][1],
                               890 / 821, places=5)

    def test_dock_is_drawn_after_crops_and_theme_cache_is_separate(self):
        renderer = FarmRenderer(choose_font())
        who = Identity("test", "local", "qq", "seasons")
        data = Snapshot(Account("四季测试", 500, 0, 0), (), (Plot(1),))
        for theme in ("spring", "summer", "autumn", "winter", "bee"):
            first = renderer.render(who, data, 0, RenderOptions(theme=theme))
            warm = renderer.render(who, data, 1, RenderOptions(theme=theme))
            self.assertFalse(first.cache_hit)
            self.assertTrue(warm.cache_hit)
        scene = renderer.scene(who, data, 0)
        order = []
        with patch.object(renderer, "_plants", side_effect=lambda *a:
                          order.append("plants")), patch.object(
            renderer, "_decorations", side_effect=lambda c, o, layer:
            order.append(layer)
        ):
            renderer.render(who, data, 0, RenderOptions(width=1536))
        self.assertLess(order.index("plants"), order.index("foreground"))
