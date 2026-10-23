import asyncio
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image

from farm_core.commands import (
    COMMAND_SPECS, CommandSpec, command_map, command_specs, help_groups,
    help_text,
)
from farm_render import FarmRenderer, RenderService
from farm_render.help import help_layout, render_help, wrap_text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ci_font import choose_font


class HelpMenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.renderer = FarmRenderer(choose_font())

    def test_registration_and_help_share_platform_definitions(self):
        exchange = CommandSpec(
            '购买农场币', 'fixture_exchange', '金币兑换',
            '购买农场币 数量', '仅用于测试已接入的平台命令。',
            platforms=('zhenxun',),
        )
        specs = (*COMMAND_SPECS, exchange)
        for platform in ('zhenxun', 'nonebot', 'astrbot'):
            selected = command_specs(platform, specs)
            mapping = command_map(platform, specs)
            self.assertEqual('购买农场币' in mapping, platform == 'zhenxun')
            self.assertEqual('金币兑换' in help_text(selected),
                             platform == 'zhenxun')
            for spec in selected:
                self.assertEqual(mapping[spec.name], spec.action)
                self.assertIn(spec.usage, help_text(selected))
            self.assertEqual(mapping['除虫'], mapping['农场除虫'])
        with self.assertRaises(ValueError):
            command_map('zhenxun', (*specs, exchange))

    def test_long_future_commands_wrap_without_loss_and_grow(self):
        specs = command_specs('astrbot')
        long = '很长的新增指令参数与说明' * 8
        lines = wrap_text(long, self.renderer.font_path, 28, 484)
        self.assertEqual(''.join(lines), long)
        from farm_render.canvas import Canvas
        self.assertTrue(all(Canvas.measure_text(
            line, self.renderer.font_path, 28,
        ) <= 484 for line in lines))
        extra = tuple(CommandSpec(
            f'新增{i}', f'action{i}', '新增功能', long, long,
        ) for i in range(10))
        before = help_layout(specs, self.renderer.font_path)[1]
        after = help_layout((*specs, *extra), self.renderer.font_path)[1]
        self.assertGreater(after, before)
        grouped = help_groups((*specs, *extra))
        self.assertEqual(grouped[-1][0], '新增功能')

    async def test_image_codec_quality_cache_and_concurrent_dedup(self):
        specs = command_specs('astrbot')
        service = RenderService(self.renderer)
        try:
            with patch('farm_render.service.render_help',
                       wraps=render_help) as fn:
                results = await asyncio.gather(*(
                    service.help_menu(specs, 'astrbot', 'JPEG', 75)
                    for _ in range(4)
                ))
                self.assertEqual(fn.call_count, 1)
                self.assertTrue(all(r == results[0] for r in results))
                self.assertEqual(await service.help_menu(
                    specs, 'astrbot', 'JPEG', 75,
                ), results[0])
                self.assertEqual(fn.call_count, 1)
                changed = (*specs, replace(specs[-1], name='扩展帮助',
                                          usage='扩展帮助'))
                await service.help_menu(changed, 'astrbot', 'JPEG', 75)
                await service.help_menu(specs, 'nonebot', 'JPEG', 75)
                await service.help_menu(specs, 'astrbot', 'JPEG', 90)
                self.assertEqual(fn.call_count, 4)
            with Image.open(BytesIO(results[0])) as image:
                self.assertEqual(image.width, 1200)
                self.assertGreater(image.height, 1200)
                self.assertEqual(image.format, 'JPEG')
            png = await service.help_menu(specs, 'astrbot', 'PNG', 75)
            with Image.open(BytesIO(png)) as image:
                self.assertEqual(image.format, 'PNG')
        finally:
            await service.close()
        with self.assertRaises(RuntimeError):
            await service.help_menu(specs, 'astrbot')
