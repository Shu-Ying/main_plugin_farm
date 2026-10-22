import ast
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class AstrBotPackageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    async def test_reproducible_complete_package_and_tamper_rejection(self):
        from build_astrbot import build
        from verify_astrbot import verify_files, read_package
        first = build(ROOT, self.root / 'one')
        second = build(ROOT, self.root / 'two')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        files = read_package(first)
        manifest = verify_files(files)
        version = (ROOT / 'version.txt').read_text().strip()
        self.assertEqual(manifest['version'], version)
        self.assertEqual(json.loads(files['metadata.yaml'])['version'], version)
        self.assertEqual(files['runtime.py'], (
            ROOT / 'integrations/zhenxun/runtime.py'
        ).read_bytes())
        for name, content in files.items():
            self.assertNotIn('.git/', name)
            self.assertNotIn('farm.sqlite3', name)
            if name.endswith('.py'):
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse((node.module or '').startswith(
                            ('nonebot', 'zhenxun'),
                        ))
        files['main.py'] += b'\n# tampered\n'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            verify_files(files)
        with self.assertRaises(FileExistsError):
            build(ROOT, self.root / 'one')
        expected = hashlib.sha256(first.read_bytes()).hexdigest()
        self.assertIn(expected, first.with_suffix('.zip.sha256').read_text())

    async def test_mock_host_commands_images_identity_and_shutdown(self):
        from build_astrbot import build
        from ci_font import choose_font
        build(ROOT, self.root / 'host')
        package = ModuleType('astrbot_farm_fixture')
        package.__path__ = [str(self.root / 'host/repository')]
        api = ModuleType('astrbot.api')
        api.AstrBotConfig = dict
        events = ModuleType('astrbot.api.event')
        commands = {}

        def command(name, alias=None):
            def decorate(handler):
                commands.update({c: handler for c in {name} | (alias or set())})
                return handler
            return decorate

        events.filter = SimpleNamespace(command=command)
        events.AstrMessageEvent = type('Event', (), {})
        star = ModuleType('astrbot.api.star')

        class Star:
            def __init__(self, context):
                self.context = context

        star.Star, star.Context = Star, object
        star.StarTools = SimpleNamespace(
            get_data_dir=lambda name: self.root / 'plugin-data',
        )
        components = ModuleType('astrbot.api.message_components')
        components.At = type('At', (), {})
        components.Image = SimpleNamespace(fromBytes=lambda content: content)
        modules = {m.__name__: m for m in (
            package, api, events, star, components,
        )}
        with patch.dict(sys.modules, modules):
            try:
                main = importlib.import_module(package.__name__ + '.main')
                plugin = main.FarmPlugin(object(), {
                    'font_path': str(choose_font()), 'image_quality': 55,
                })
                await plugin.initialize()
                self.assertEqual(set(commands), set(main.COMMANDS))

                class Event:
                    message_obj = SimpleNamespace(message_id='one')

                    def __init__(self, text, platform_id='bot-a'):
                        self.text, self.platform_id = text, platform_id

                    def get_message_str(self):
                        return self.text

                    def get_self_id(self):
                        return 'bot'

                    def get_platform_id(self):
                        return self.platform_id

                    def get_platform_name(self):
                        return 'aiocqhttp'

                    def get_sender_id(self):
                        return '123456'

                    def get_sender_name(self):
                        return '离线测试'

                    def get_messages(self):
                        return []

                    def plain_result(self, text):
                        return text

                    def chain_result(self, chain):
                        return chain

                async def call(text, platform_id='bot-a'):
                    return [r async for r in plugin.farm(
                        Event(text, platform_id),
                    )][0]

                first = await call('开通农场')
                self.assertIn('6块土地', first)
                again = await call('开通农场')
                self.assertIsInstance(again, str)
                self.assertIn('开通农场', await call('我的种子', 'bot-b'))
                from io import BytesIO
                from PIL import Image
                avatar_buffer = BytesIO()
                Image.new('RGB', (64, 64), '#ee2222').save(
                    avatar_buffer, format='PNG',
                )
                avatar_bytes = avatar_buffer.getvalue()
                with patch.object(plugin._avatars, 'get', new=AsyncMock(
                        return_value=avatar_bytes)) as avatar_get:
                    with patch.object(plugin.runtime, 'execute',
                                      wraps=plugin.runtime.execute) as execute:
                        result = await call('我的农场 高清')
                        self.assertEqual(execute.call_args.kwargs['avatar'],
                                         avatar_bytes)
                        await call('农场详述')
                        await call('地块编号')
                        await call('我的种子 文字')
                        self.assertIsNone(execute.call_args.kwargs['avatar'])
                    self.assertEqual(avatar_get.await_count, 3)
                    avatar_get.assert_awaited_with('aiocqhttp', '123456')
                with Image.open(BytesIO(result[0])) as image:
                    self.assertEqual(image.width, 1536)
                    red, green, blue = image.getpixel((70, 70))[:3]
                    self.assertGreater(red, 180)
                    self.assertLess(green, 90)
                    self.assertLess(blue, 90)
                self.assertIn('仅我的农场', await call('我的种子 高清'))
                self.assertIn('暂无种子', await call('我的种子 文字'))
                self.assertTrue(
                    (self.root / 'plugin-data/farm.sqlite3').is_file(),
                )
                await plugin.terminate()
                self.assertFalse(plugin.runtime.started)
            finally:
                if 'plugin' in locals() and plugin.runtime.started:
                    await plugin.terminate()
                for name in tuple(sys.modules):
                    if name.startswith(package.__name__ + '.'):
                        del sys.modules[name]
