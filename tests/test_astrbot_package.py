import ast
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


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
        metadata = json.loads(files['metadata.yaml'])
        self.assertEqual(metadata['display_name'], '真寻农场')
        self.assertEqual(metadata['support_platforms'], ['aiocqhttp'])
        self.assertTrue(metadata['short_desc'])
        self.assertEqual(files['logo.png'],
                         (ROOT / 'logo-astrbot.png').read_bytes())
        self.assertEqual(files['logo-readme.png'],
                         (ROOT / 'logo.png').read_bytes())
        self.assertIn('农场', metadata['tags'])
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(files['logo.png'])) as logo:
            self.assertEqual(logo.format, 'PNG')
            self.assertEqual(logo.width, logo.height)
            self.assertEqual(logo.size, (256, 256))
            self.assertIn('A', logo.getbands())
            self.assertEqual(logo.getchannel('A').getextrema()[0], 0)
        self.assertEqual(files['CHANGELOG.md'], (
            ROOT / 'integrations/astrbot/CHANGELOG.md'
        ).read_bytes())
        readme = files['README.md'].decode()
        self.assertIn('logo.png', readme)
        self.assertIn('width="400"', readme)
        self.assertNotIn('<!-- FARM_COMMANDS -->', readme)
        self.assertIn('images/help-astrbot.png', readme)
        self.assertIn('images/farm-preview.png', files)
        self.assertFalse(any(name.endswith('/assets.zip') for name in files))
        from verify_astrbot import verify_package
        with patch('verify_astrbot.MAX_ARCHIVE_BYTES', 1):
            with self.assertRaisesRegex(ValueError, '16 MiB'):
                verify_package(first, marketplace=True)
        source_tree = ast.parse((ROOT / 'integrations/shared/runtime.py')
                                .read_bytes())
        built_tree = ast.parse(files['runtime.py'])
        source_runtime = next(node for node in source_tree.body
                              if isinstance(node, ast.ClassDef))
        built_runtime = next(node for node in built_tree.body
                             if isinstance(node, ast.ClassDef))
        self.assertEqual(ast.dump(source_runtime), ast.dump(built_runtime))
        self.assertFalse('_vendor/farm_core/__main__.py' in files)
        for name, content in files.items():
            self.assertNotIn('.git/', name)
            self.assertNotIn('farm.sqlite3', name)
            if name.endswith('.py'):
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        self.assertFalse(any(
                            alias.name.split('.')[0] == 'logging'
                            for alias in node.names
                        ), name)
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse((node.module or '').startswith(
                            ('nonebot', 'zhenxun', 'logging'),
                        ))
        for snippet in (b'\nimport logging\n',
                        b'\nlogger.setLevel(20)\n'):
            invalid = dict(files)
            invalid['main.py'] += snippet
            invalid_manifest = json.loads(invalid['FARM-MANIFEST.json'])
            invalid_manifest['files']['main.py'] = hashlib.sha256(
                invalid['main.py'],
            ).hexdigest()
            invalid['FARM-MANIFEST.json'] = json.dumps(
                invalid_manifest,
            ).encode()
            with self.assertRaisesRegex(ValueError, 'logging'):
                verify_files(invalid)
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
        api.logger = Mock()
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
                    'font_path': 'ignored-custom.ttf',
                    'data_dir': str(self.root / 'existing-custom-data'),
                    'image_quality': 55,
                })
                self.assertEqual(plugin.runtime.data_dir,
                                 (self.root / 'existing-custom-data').resolve())
                self.assertIsNone(plugin.runtime.font_path)
                self.assertEqual(plugin.runtime.resource_source, 'Github')
                # 使用真实开发素材预置缓存，模拟宿主测试不访问网络。
                manifest = json.loads((ROOT /
                    'src/farm_render/data/asset-manifest.json').read_bytes())
                cached = (plugin.runtime.data_dir / 'assets'
                          / manifest['sha256'] / 'assets.zip')
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes((ROOT /
                    'src/farm_render/data/assets.zip').read_bytes())
                font_manifest = json.loads((ROOT /
                    'src/farm_render/data/font-manifest.json').read_bytes())
                fonts = (plugin.runtime.data_dir / 'fonts'
                         / font_manifest['sha256'])
                fonts.mkdir(parents=True, exist_ok=True)
                (fonts / 'Xiaolai-Regular.ttf').write_bytes(
                    Path(choose_font()).read_bytes())
                (fonts / 'OFL-Xiaolai.txt').write_bytes((ROOT /
                    'src/farm_render/data/OFL-Xiaolai.txt').read_bytes())
                with patch(
                    package.__name__ +
                    '._vendor.farm_render.catalogue_bundle._fetch',
                    side_effect=OSError('offline fixture'),
                ):
                    await plugin.initialize()
                self.assertIs(main.logger, api.logger)
                self.assertIsNone(plugin.runtime.log_handler)
                self.assertIsNone(plugin.runtime.console_handler)
                self.assertFalse((plugin.runtime.data_dir /
                                  'farm-preview.log').exists())
                api.logger.info.assert_any_call(
                    '农场启动：正在检查作物版本和本地缓存',
                )
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
                self.assertIn('参数有误', await call('我的种子 文字'))
                self.assertTrue(
                    (self.root / 'existing-custom-data/farm.sqlite3').is_file(),
                )
                self.assertFalse(
                    (self.root / 'plugin-data/farm.sqlite3').exists(),
                )
                await plugin.terminate()
                self.assertFalse(plugin.runtime.started)
                plugin = main.FarmPlugin(object(), {
                    'data_dir': str(self.root / 'existing-custom-data'),
                })
                await plugin.initialize()
                reopened = Event('开通农场')
                reopened.message_obj = SimpleNamespace(message_id='after-reload')
                response = [r async for r in plugin.farm(reopened)][0]
                self.assertIn('农场已存在', response)
                await plugin.terminate()
            finally:
                if 'plugin' in locals() and plugin.runtime.started:
                    await plugin.terminate()
                for name in tuple(sys.modules):
                    if name.startswith(package.__name__ + '.'):
                        del sys.modules[name]
