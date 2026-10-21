import asyncio
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import os
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image, features

from farm_core import Catalogue, Identity
from farm_core.domain import Account, Plot, Snapshot

try:
    from farm_render import FarmRenderer, RenderOptions, RenderService
    from farm_render.assets import ByteLRU
    from farm_render.canvas import Canvas
except ImportError:
    FarmRenderer = None


FONT = Path("C:/Windows/Fonts/msyh.ttc")
if not FONT.exists():
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT = Path(os.environ.get("FARM_TEST_FONT", FONT))


def snapshot(plots=None, **account):
    values = dict(name="演示农场", point=500, vip_point=0, experience=0)
    values.update(account)
    return Snapshot(Account(**values), (), tuple(
        plots if plots is not None else [Plot(i) for i in range(1, 7)]
    ))


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(FarmRenderer, "共享图片模块尚未实现")
        self.renderer = FarmRenderer(FONT)
        self.who = Identity("test", "local", "qq", "one")
        self.plant = next(iter(Catalogue.bundled()))

    def test_plot_ids_follow_positions_and_mark_owned_slots(self):
        options = RenderOptions(width=1536, show_plot_ids=True)
        scene = self.renderer.scene(self.who, snapshot(), 0)
        canvas = Canvas.new((1536, 936), 'white')
        with patch.object(canvas, 'text', wraps=canvas.text) as text:
            self.renderer._plot_ids(canvas, scene, options)
        self.assertEqual(
            [call.args[1] for call in text.call_args_list[:30]],
            [str(i) for i in range(1, 31)],
        )
        for slot, color in ((1, '#fff2ca'), (6, '#fff2ca'),
                            (7, '#d5e8bc'), (30, '#d5e8bc')):
            pos = self.renderer.assets.metadata['positions'][slot-1]
            x, y = round((pos['x']+117)/2), round((pos['y']+78)/2)
            from PIL import ImageColor
            self.assertEqual(canvas.image.getpixel((x-15, y))[:3],
                             ImageColor.getrgb(color))

    def test_plot_id_image_has_separate_cache_from_normal_farm(self):
        plain = self.renderer.render(self.who, snapshot(), 0)
        options = RenderOptions(show_plot_ids=True)
        numbered = self.renderer.render(self.who, snapshot(), 0, options)
        self.assertFalse(numbered.cache_hit)
        self.assertNotEqual(plain.content, numbered.content)
        self.assertTrue(self.renderer.render(
            self.who, snapshot(), 0, options,
        ).cache_hit)
        self.assertEqual(
            self.renderer.render(self.who, snapshot(), 0).content,
            plain.content,
        )

    def test_canvas_alpha_crop_text_and_formats(self):
        canvas = Canvas.new((100, 80), "white")
        overlay = Image.new("RGBA", (20, 20), (255, 0, 0, 128))
        canvas.paste(overlay, (0, 0))
        self.assertEqual(canvas.image.getpixel((5, 5))[:3], (255, 127, 127))
        self.assertEqual(canvas.crop((0, 0, 10, 10)).image.size, (10, 10))
        self.assertEqual(canvas.resize((50, 40)).image.size, (50, 40))
        text = canvas.fit_text("long farm name" * 20, FONT, 16, 80)
        self.assertLessEqual(canvas.measure_text(text, FONT, 16), 80)
        canvas.text((1, 30), text, FONT, 16, "black")
        for fmt in ("PNG", "JPEG", "WEBP"):
            if fmt == "WEBP" and not features.check("webp"):
                continue
            content = canvas.encode(fmt, 75, 2)
            with Image.open(BytesIO(content)) as image:
                self.assertEqual(image.format, fmt)
                self.assertEqual(image.size, (100, 80))

    def test_profiles_formats_and_bad_avatar_fallback(self):
        for width in (1024, 1536):
            for fmt in ("JPEG", "PNG", "WEBP"):
                if fmt == "WEBP" and not features.check("webp"):
                    continue
                result = self.renderer.render(
                    self.who, snapshot(), 0,
                    RenderOptions(width=width, format=fmt), b"broken avatar",
                )
                with Image.open(BytesIO(result.content)) as image:
                    self.assertEqual(image.width, width)
                    self.assertEqual(image.format, fmt)
                self.assertEqual(result.width, width)
                self.assertGreater(result.compose_ms, 0)

    def test_stage_boundaries_multiseason_and_withered(self):
        plant = self.plant
        plot = Plot(1, plant, plant.growth_seconds)
        view = lambda p, now: self.renderer.scene(
            self.who, snapshot([p]), now,
        ).plots[0]
        self.assertEqual(view(plot, 0).state, "growing")
        self.assertEqual(view(plot, plant.growth_seconds).state, "ripe")
        self.assertNotEqual(view(plot, 0).sprite, view(plot, 20000).sprite)
        multi = replace(plant, crop=3)
        again = Plot(1, multi, multi.regrowth_seconds + 100, 1)
        self.assertEqual(view(again, 100).stage, 0)
        self.assertGreater(view(again, again.mature_at - 1).stage, 0)
        dead = replace(again, harvest_count=3)
        self.assertEqual(view(dead, 999999).state, "withered")
        self.assertEqual(view(dead, 999999).sprite, "webgl/wither.png")

    def test_result_cache_visible_state_scope_and_time(self):
        plant = self.plant
        data = snapshot([Plot(1, plant, plant.growth_seconds)])
        first = self.renderer.render(self.who, data, 0)
        warm = self.renderer.render(self.who, data, 1)
        self.assertFalse(first.cache_hit)
        self.assertTrue(warm.cache_hit)
        self.assertEqual(first.content, warm.content)
        ripe = self.renderer.render(self.who, data, plant.growth_seconds)
        self.assertFalse(ripe.cache_hit)
        self.assertNotEqual(first.content, ripe.content)
        changed = replace(data, account=replace(data.account, point=501))
        self.assertFalse(self.renderer.render(
            self.who, changed, 0,
        ).cache_hit)
        other = replace(self.who, realm="other")
        self.assertFalse(self.renderer.render(other, data, 0).cache_hit)
        self.assertFalse(self.renderer.render(
            self.who, data, 0, avatar=b"changed",
        ).cache_hit)
        changed = replace(data, account=replace(data.account, experience=200))
        self.assertFalse(self.renderer.render(self.who, changed, 0).cache_hit)

    def test_web_panel_avatar_uses_prefab_rect_and_frame_overlays_it(self):
        avatar = BytesIO()
        Image.new("RGB", (80, 40), "red").save(avatar, "PNG")
        scene = self.renderer.scene(self.who, snapshot(), 0)
        for width in (1024, 1536, 3072):
            options = RenderOptions(width=width)
            s = lambda n: round(n * width / 1920)
            actual = Canvas.new((width, round(width * 1872 / 3072)))
            with patch.object(actual, "paste", wraps=actual.paste) as paste:
                self.renderer._panel(actual, scene, options, avatar.getvalue())
            calls = paste.call_args_list
            self.assertEqual(calls[1].args[0].size,
                             (s(111.387001), s(107.707199)))
            self.assertEqual(calls[1].args[1], (s(32.274426), s(39.761826)))
            self.assertEqual(calls[1].args[0].getpixel((0, 0)),
                             (255, 0, 0, 255))
            self.assertEqual(calls[2].args[1], (s(3.093), s(8.865)))
            self.assertEqual(calls[2].args[0].size, (s(169.75), s(169.5)))

    def test_web_panel_fields_fit_their_prefab_rectangles(self):
        options = RenderOptions(width=3072)
        for exp, level, current, threshold in (
            (0, 0, 0, 200), (199, 0, 199, 200), (200, 1, 0, 400),
            (599, 1, 399, 400), (600, 2, 0, 600), (3420, 5, 420, 1200),
        ):
            data = snapshot(name="农场", point=12580, vip_point=36,
                            experience=exp)
            scene = self.renderer.scene(self.who, data, 0)
            canvas = Canvas.new((3072, 1872))
            with patch.object(canvas, "text") as text, patch.object(
                canvas, "rectangle",
            ) as rectangle:
                self.renderer._panel(canvas, scene, options, None)
            self.assertEqual([c.args[1] for c in text.call_args_list], [
                '农场', f'{current} / {threshold}', str(level), '12580', '36',
            ])
            from farm_render.canvas import font
            rectangles = ((161.2451, 40.9, 298.0353, 31.2),
                          (177.6, 89.7879, 223, 22.0242),
                          (400.9734, 85.3627, 56, 30),
                          (178.4624, 128.2392, 123.6104, 30),
                          (342, 128.2392, 108, 30))
            for call, rect in zip(text.call_args_list, rectangles):
                position, value, path, size, _ = call.args
                box = font(path, size).getbbox(value)
                left, top = position[0] + box[0], position[1] + box[1]
                self.assertGreaterEqual(left, round(rect[0] * 1.6) - 1)
                self.assertGreaterEqual(top, round(rect[1] * 1.6) - 1)
                self.assertLessEqual(left + box[2] - box[0],
                                     round((rect[0] + rect[2]) * 1.6) + 1)
                self.assertLessEqual(top + box[3] - box[1],
                                     round((rect[1] + rect[3]) * 1.6) + 1)

    def test_web_experience_fill_clips_texture_without_resizing(self):
        options = RenderOptions(width=1536)
        original = self.renderer.assets.image(
            'webgl/panel/ExpProgress.png', (172, 18),
        )
        for exp, current, required in (
            (0, 0, 200), (100, 100, 200), (199, 199, 200),
            (599, 399, 400), (1199, 599, 600),
        ):
            scene = self.renderer.scene(
                self.who, snapshot(experience=exp), 0,
            )
            canvas = Canvas.new((1536, 936))
            with patch.object(canvas, 'paste') as paste:
                self.renderer._panel(canvas, scene, options, None)
            calls = paste.call_args_list
            if exp == 0:
                self.assertEqual(len(calls), 6)
            else:
                self.assertEqual(len(calls), 7)
                filled = current * 172 // required
                self.assertEqual(calls[4].args[0].tobytes(),
                                 original.crop((0, 0, filled, 18)).tobytes())

    def test_lru_budget_and_shared_image_safety(self):
        cache = ByteLRU(10)
        cache.put("a", b"123456", 6)
        cache.put("b", b"abcdef", 6)
        self.assertIsNone(cache.get("a"))
        self.assertLessEqual(cache.used_bytes, 10)
        cache.put("huge", bytes(20), 20)
        self.assertIsNone(cache.get("huge"))
        image = self.renderer.assets.image("soil/草土地.png", (80, 50))
        before = image.tobytes()
        image.paste("red", (0, 0, 80, 50))
        fresh = self.renderer.assets.image("soil/草土地.png", (80, 50))
        self.assertEqual(before, fresh.tobytes())
        self.assertLessEqual(
            self.renderer.assets.cache.used_bytes,
            self.renderer.assets.cache.limit,
        )

    def test_auto_codec_fallback_and_invalid_options(self):
        with patch("farm_render.models.features.check", return_value=False):
            self.assertEqual(RenderOptions().codec(("WEBP", "JPEG")), "JPEG")
            with self.assertRaises(ValueError):
                RenderOptions(format="WEBP").codec(("WEBP",))
        for kwargs in ({"width":True}, {"width":99999}, {"quality":101},
                       {"method":7}, {"theme":"../oops"}):
            with self.assertRaises(ValueError):
                RenderOptions(**kwargs)

    def test_first_stage_exact_boundary_and_target_canvas(self):
        plot = Plot(1, self.plant, self.plant.growth_seconds)
        metadata = self.renderer.assets.metadata["plants"][self.plant.name]
        threshold = int(metadata["phase"].split(",")[0])
        data = snapshot([plot])
        self.assertEqual(self.renderer.scene(
            self.who, data, threshold - 1,
        ).plots[0].stage, 0)
        self.assertEqual(self.renderer.scene(
            self.who, data, threshold,
        ).plots[0].stage, 1)
        widths = []
        original = Canvas.__init__

        def capture(canvas, image):
            widths.append(image.width)
            original(canvas, image)

        with patch.object(Canvas, "__init__", capture):
            self.renderer.render(self.who, data, 0)
        self.assertTrue(widths)
        self.assertEqual(set(widths), {1024})

    def test_missing_sprite_and_private_logs(self):
        metadata = self.renderer.assets.metadata
        plant = next(p for p in Catalogue.bundled() if (
            f'plant/{p.name}/1.png' not in metadata["images"]
        ))
        data = snapshot([Plot(1, plant, 0)], name="PRIVATE FARM")
        with self.assertLogs("farm_render.renderer", "INFO") as recorded:
            result = self.renderer.render(self.who, data, 0)
        self.assertTrue(result.content)
        logs = " ".join(recorded.output)
        self.assertIn("missing packaged crop sprite", logs)
        self.assertNotIn("PRIVATE FARM", logs)
        self.assertNotIn(self.who.key, logs)

    def test_oversized_avatar_is_not_decoded(self):
        content = BytesIO()
        Image.new("RGB", (3000, 3000), "white").save(content, "PNG")
        result = self.renderer.render(
            self.who, snapshot(), 0, avatar=content.getvalue(),
        )
        self.assertTrue(result.content)
        with self.assertRaises(ValueError):
            FarmRenderer(Path("missing-font.ttf"))


class AsyncRenderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(FarmRenderer, "异步渲染模块尚未实现")
        self.renderer = FarmRenderer(FONT)
        self.who = Identity("test", "local", "qq", "async")

    async def test_snapshot_once_and_loop_not_blocked(self):
        class Source:
            calls = 0

            async def snapshot(inner, who):
                inner.calls += 1
                return snapshot()

        source = Source()
        service = RenderService(self.renderer)
        original = self.renderer.render
        reached = threading.Event()

        def slow(*args, **kwargs):
            reached.set()
            time.sleep(0.1)
            return original(*args, **kwargs)

        self.renderer.render = slow
        task = asyncio.create_task(service.my_farm(source, self.who, now=0))
        await asyncio.to_thread(reached.wait, 2)
        self.assertFalse(task.done())
        self.assertTrue((await task).content)
        self.assertEqual(source.calls, 1)
        await service.close()

    async def test_singleflight_cancel_capacity_and_close(self):
        service = RenderService(self.renderer, concurrency=1, max_pending=1)
        entered = threading.Event()
        release = threading.Event()
        original = self.renderer.render
        calls = []

        def slow(*args, **kwargs):
            calls.append(1)
            entered.set()
            release.wait(3)
            return original(*args, **kwargs)

        self.renderer.render = slow
        data = snapshot()
        first = asyncio.create_task(service.render(self.who, data, 0))
        await asyncio.to_thread(entered.wait, 2)
        same = asyncio.create_task(service.render(self.who, data, 0))
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        with self.assertRaises(RuntimeError):
            await service.render(replace(self.who, user_id="two"), data, 0)
        closing = asyncio.create_task(service.close())
        await asyncio.sleep(0.02)
        self.assertFalse(closing.done())
        release.set()
        self.assertTrue((await same).content)
        await closing
        self.assertEqual(len(calls), 1)
        with self.assertRaises(RuntimeError):
            await service.render(self.who, data, 0)

    async def test_failure_frees_capacity_for_retry(self):
        service = RenderService(self.renderer)
        original = self.renderer.render
        with patch.object(self.renderer, "render", side_effect=ValueError):
            with self.assertRaises(ValueError):
                await service.render(self.who, snapshot(), 0)
        self.renderer.render = original
        self.assertTrue((await service.render(
            self.who, snapshot(), 0,
        )).content)
        await service.close()

    async def test_limit_bounds_distinct_parallel_jobs(self):
        service = RenderService(self.renderer, concurrency=2, max_pending=4)
        lock = threading.Lock()
        active = 0
        maximum = 0
        original = self.renderer.render

        def observed(*args, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(0.03)
                return original(*args, **kwargs)
            finally:
                with lock:
                    active -= 1

        self.renderer.render = observed
        await asyncio.gather(*(
            service.render(replace(self.who, user_id=str(i)), snapshot(), 0)
            for i in range(4)
        ))
        self.assertEqual(maximum, 2)
        self.assertEqual(active, 0)
        await service.close()
