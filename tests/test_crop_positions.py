from pathlib import Path
from dataclasses import replace
import sys
import unittest
from unittest.mock import patch

from farm_core import Catalogue, Identity
from farm_core.domain import Account, Plot, Snapshot
from farm_render import FarmRenderer, RenderOptions
from farm_render.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ci_font import choose_font


class CropPositionTests(unittest.TestCase):
    def setUp(self):
        self.renderer = FarmRenderer(choose_font())
        self.who = Identity("test", "local", "qq", "one")

    def scene(self, name, now):
        plant = Catalogue.bundled().get(name)
        return self.renderer.scene(self.who, Snapshot(
            Account("公式预览", 500, 0, 0), (),
            (Plot(1, plant, plant.growth_seconds),),
        ), now)

    def test_growth_stages_use_full_canvas_bottom_for_every_crop(self):
        for name in ("草莓", "橙子", "樱桃", "茄子", "黄瓜"):
            phases = self.renderer.assets.metadata["plants"][name]["phase"]
            for now in dict.fromkeys(map(int, phases.split(","))):
                for width in (1024, 1536, 3072):
                    with self.subTest(name=name, now=now, width=width):
                        scene = self.scene(name, now)
                        canvas = Canvas.new((width, round(1872*width/3072)))
                        with patch.object(canvas, "paste") as paste:
                            self.renderer._plants(
                                canvas, scene, RenderOptions(width=width),
                            )
                        image, xy = paste.call_args_list[0].args
                        meta = self.renderer.assets.metadata
                        pos = meta["positions"][0]
                        sw, sh = meta["soil_size"]
                        scale = width / 3072
                        self.assertLessEqual(abs(
                            xy[0] + image.width / 2
                            - (pos["x"] + sw/2) * scale
                        ), 1)
                        self.assertLessEqual(abs(
                            xy[1] + image.height
                            - (pos["y"] + sh) * scale
                        ), .5)
                        native = meta["images"][scene.plots[0].sprite]["size"]
                        self.assertEqual(image.size, tuple(
                            max(1, round(n * .75 * sh / 79.5 * scale))
                            for n in native
                        ))

    def test_seed_and_wither_use_public_sprites_and_distinct_targets(self):
        seed = self.scene("草莓", 0)
        self.assertEqual(seed.plots[0].sprite, "webgl/seed.png")
        plant = Catalogue.bundled().get("草莓")
        dead = self.renderer.scene(self.who, Snapshot(
            seed.account, (), (Plot(1, plant, None, plant.crop),),
        ), 999999)
        self.assertEqual(dead.plots[0].sprite, "webgl/wither.png")
        for scene, shift in ((seed, 0), (dead, 8)):
            canvas = Canvas.new((3072, 1872))
            with patch.object(canvas, "paste") as paste:
                self.renderer._plants(canvas, scene, RenderOptions(width=3072))
            image, xy = paste.call_args_list[0].args
            meta = self.renderer.assets.metadata
            pos = meta["positions"][0]
            height = meta["soil_size"][1]
            self.assertLessEqual(abs(
                xy[1] + image.height - (pos["y"] + height/2
                                       + shift*height/79.5)
            ), .5)

    def test_missing_sprite_keeps_safe_placeholder(self):
        scene = self.scene("草莓", 14400)
        self.renderer.assets.metadata["images"].pop(scene.plots[0].sprite)
        result = self.renderer.render(
            self.who, Snapshot(scene.account, (), (
                Plot(1, Catalogue.bundled().get("草莓"), 86400),
            )), 14400,
        )
        self.assertTrue(result.content)

    def test_exported_configuration_has_no_manual_stage_anchors(self):
        meta = self.renderer.assets.metadata
        self.assertEqual(meta["placement"]["schema"], 2)
        self.assertTrue(all("stages" not in p for p in meta["plants"].values()))

    def test_pest_count_changes_cache_and_pest_positions_use_land_center(self):
        plant = Catalogue.bundled().get("草莓")
        clean = Snapshot(Account("虫害预览", 0, 0, 0), (), (
            Plot(1, plant, 86400),
        ))
        infested = replace(clean, plots=(replace(
            clean.plots[0], pest_count=3, pest_spawned=3,
        ),))
        first = self.renderer.render(self.who, clean, 40000)
        second = self.renderer.render(self.who, infested, 40000)
        self.assertFalse(second.cache_hit)
        self.assertNotEqual(first.content, second.content)
        scene = self.renderer.scene(self.who, infested, 40000)
        canvas = Canvas.new((3072, 1872))
        with patch.object(canvas, "paste") as paste:
            self.renderer._pests(canvas, scene, RenderOptions(width=3072))
        self.assertEqual(paste.call_count, 3)
        meta = self.renderer.assets.metadata
        pos = meta["positions"][0]
        sw, sh = meta["soil_size"]
        unit = sh / 79.5
        for call, (x, y) in zip(paste.call_args_list,
                                ((-26, 13), (-5, 42), (24, 24))):
            image, xy = call.args
            self.assertLessEqual(abs(xy[0] + image.width/2
                - (pos["x"]+sw/2+x*unit)), .5)
            self.assertLessEqual(abs(xy[1] + image.height/2
                - (pos["y"]+sh/2-y*unit)), .5)
        self.assertEqual(len(meta["pest"]["frames"]), 38)

    def test_pest_frames_are_varied_and_stable_across_renderers_and_sizes(self):
        plant = Catalogue.bundled().get("草莓")
        data = Snapshot(Account("随机帧测试", 0, 0, 0), (), tuple(
            Plot(slot, plant, 86400, pest_count=3, pest_spawned=3)
            for slot in range(1, 6)
        ))
        scene = self.renderer.scene(self.who, data, 40000)
        restarted = FarmRenderer(choose_font())
        self.assertEqual(scene, restarted.scene(self.who, data, 40001))
        frames = [frame for view in scene.plots for frame in view.pest_frames]
        self.assertGreater(len(set(frames)), 3)
        for view in scene.plots:
            self.assertEqual(len(set(view.pest_frames)), 3)
        for width in (1024, 1536):
            options = RenderOptions(width=width, format="PNG")
            first = self.renderer.render(self.who, data, 40000, options)
            cached = self.renderer.render(self.who, data, 40001, options)
            cold = restarted.render(self.who, data, 40001, options)
            self.assertTrue(cached.cache_hit)
            self.assertEqual(first.content, cached.content)
            self.assertEqual(first.content, cold.content)

    def test_pest_frames_survive_partial_clear_and_change_for_next_season(self):
        plant = Catalogue.bundled().get("草莓")
        plot = Plot(1, plant, 86400, pest_count=3, pest_spawned=3)
        data = Snapshot(Account("随机帧测试", 0, 0, 0), (), (plot,))
        initial = self.renderer.scene(self.who, data, 40000).plots[0]
        fewer = replace(data, plots=(replace(plot, pest_count=1),))
        remaining = self.renderer.scene(self.who, fewer, 40000).plots[0]
        self.assertEqual(remaining.pest_frames, initial.pest_frames[:1])
        next_season = replace(data, plots=(replace(
            plot, harvest_count=1, mature_at=plant.regrowth_seconds+100,
        ),))
        changed = self.renderer.scene(self.who, next_season, 40000).plots[0]
        self.assertNotEqual(changed.pest_frames, initial.pest_frames)
