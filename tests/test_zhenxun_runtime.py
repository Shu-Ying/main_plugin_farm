import asyncio
from contextlib import closing
from dataclasses import replace
import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import shutil
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_zhenxun import build
from ci_font import choose_font


class ZhenxunRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build(ROOT, self.root / "built")
        self.package = "farm_fixture"
        module = ModuleType(self.package)
        module.__path__ = [str(self.root / "built/repository")]
        sys.modules[self.package] = module
        self.module = importlib.import_module(self.package + ".runtime")
        self.runtime = self.module.Runtime(self.root / "data", choose_font())
        self.seed_assets(self.runtime)
        await self.runtime.start()
        self.context = dict(bot_id="bot", platform="OneBot V11", user_id="1",
                            message_id="registration", display_name="离线玩家")

    async def asyncTearDown(self):
        await self.runtime.close()
        for name in tuple(sys.modules):
            if name == self.package or name.startswith(self.package + "."):
                del sys.modules[name]
        self.temporary.cleanup()

    def seed_assets(self, runtime):
        bundle = importlib.import_module(
            self.package + '._vendor.farm_render.bundle',
        )
        target = (runtime.data_dir / 'assets'
                  / bundle.expected_manifest()['sha256'] / 'assets.zip')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'src/farm_render/data/assets.zip', target)

    async def call(self, action, arguments="", message="event", **changes):
        return await self.runtime.execute(
            action, arguments,
            **{**self.context, "message_id":message, **changes},
        )

    async def test_plot_ids_command_registration_hint_and_read_only(self):
        from io import BytesIO
        from PIL import Image
        from unittest.mock import AsyncMock
        self.assertEqual(self.module.COMMANDS['地块编号'], 'plot_ids')
        self.assertIn('地块编号', await self.call('help', '文字'))
        first = await self.call('register')
        self.assertIn('6块土地', first)
        self.assertIn('地块编号', first)
        repeated = await self.call('register', message='again')
        self.assertNotIn('已获得6块土地', repeated)
        before = await self.runtime.service.snapshot(self.runtime_identity())
        with patch.object(self.runtime.service, 'snapshot',
                          new=AsyncMock(return_value=before)) as query:
            result = await self.call('plot_ids', message=None)
            query.assert_awaited_once()
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.width, 1024)
            self.assertEqual(image.format, 'JPEG')
        self.assertEqual(
            await self.runtime.service.snapshot(self.runtime_identity()),
            before,
        )
        self.assertIn('参数有误', await self.call('plot_ids', '1'))
        self.assertIn('开通农场', await self.call('plot_ids', user_id='other'))

    async def test_dynamic_help_image_text_fallback_and_no_player_access(self):
        from io import BytesIO
        from PIL import Image
        from unittest.mock import AsyncMock
        with patch.object(self.runtime.store, 'migrate_legacy',
                          new=AsyncMock()) as migrate:
            image = await self.call('help', message=None)
            migrate.assert_not_awaited()
        with Image.open(BytesIO(image)) as decoded:
            self.assertEqual(decoded.width, 1200)
        text = await self.call('help', '文字', message=None)
        for command in self.module.COMMANDS:
            self.assertIn(command, text)
        self.assertNotIn('购买农场币', text)
        self.assertIn('仅我的农场支持高清',
                      await self.call('help', '高清'))
        self.assertIn('参数有误', await self.call('help', '2'))
        with patch.object(self.runtime.rendering, 'help_menu',
                          new=AsyncMock(side_effect=OSError('fixture'))):
            self.assertEqual(await self.call('help'), text)
        rendering = self.runtime.rendering
        self.runtime.rendering = None
        try:
            self.assertEqual(await self.call('help'), text)
        finally:
            self.runtime.rendering = rendering

    async def test_help_uses_live_global_quality(self):
        from unittest.mock import AsyncMock
        with patch.object(self.runtime.rendering, 'help_menu',
                          new=AsyncMock(return_value=b'image')) as render:
            self.runtime.image_quality_provider = lambda: 91
            self.assertEqual(await self.call('help'), b'image')
            self.assertEqual(render.await_args.args[-1], 91)
            self.runtime.image_quality_provider = lambda: False
            self.assertIn('图片质量配置无效', await self.call('help'))
            self.assertIsInstance(await self.call('help', '文字'), str)

    async def test_reclaim_conditions_charge_replay_and_arguments(self):
        self.assertEqual(self.module.COMMANDS['开垦'], 'reclaim')
        self.assertIn('开垦 条件', await self.call('help', '文字'))
        await self.call('register')
        who = self.runtime_identity()
        asset = importlib.import_module(
            self.package + '._vendor.farm_core.domain',
        ).Asset

        def fund(repo):
            repo.asset(asset.POINT, 9500)
            repo.asset(asset.EXPERIENCE, 3000)
            return {}

        await self.runtime.store.transact(who, 'fund', 'fixture', {},
                                           self.runtime.service.clock(), fund)
        self.assertIn('7号', await self.call('reclaim', '条件', message=None))
        before = await self.runtime.service.snapshot(who)
        self.assertIn('参数有误', await self.call('reclaim', '2'))
        self.assertIn('未执行', await self.call('reclaim', message=None))
        self.assertEqual(await self.runtime.service.snapshot(who), before)
        result = await self.call('reclaim', message='reclaim')
        self.assertIn('开垦已完成', result)
        self.assertIn('10000农场币', result)
        self.assertEqual(result, await self.call('reclaim', message='reclaim'))
        after = await self.runtime.service.snapshot(who)
        self.assertEqual(len(after.plots), 7)
        self.assertEqual(after.account.point, 0)
        self.assertIn('8号', await self.call('reclaim', '条件', message=None))

    async def test_plot_ids_text_fallback_uses_actual_owned_slots(self):
        await self.call('register')
        rendering = self.runtime.rendering
        self.runtime.rendering = None
        try:
            text = await self.call('plot_ids', message=None)
        finally:
            self.runtime.rendering = rendering
        self.assertIn('已开垦（6块）：1、2、3、4、5、6', text)
        self.assertIn('待开垦（24块）：7、8、9', text)
        self.assertIn('农场详述', text)

    async def test_classified_warehouse_images_text_and_read_only_paging(self):
        from io import BytesIO
        from PIL import Image
        from unittest.mock import AsyncMock
        self.assertEqual(self.module.COMMANDS['我的作物'], 'crops')
        self.assertEqual(self.module.COMMANDS['我的种子'], 'seeds')
        await self.call('register')
        await self.call('buy', '胡萝卜 2', 'warehouse-buy')
        before = await self.runtime.service.snapshot(self.runtime_identity())
        with patch.object(self.runtime.service, 'snapshot',
                          new=AsyncMock(return_value=before)) as query:
            content = await self.call('seeds', message=None)
            query.assert_awaited_once()
        with Image.open(BytesIO(content)) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (768, 1152))
        self.assertIn('仅我的农场支持高清', await self.call(
            'seeds', '1 高清', message=None,
        ))
        self.assertIn('胡萝卜（#1） 2粒', await self.call(
            'seeds', '文字', message=None,
        ))
        self.assertEqual(before, await self.runtime.service.snapshot(
            self.runtime_identity(),
        ))
        for invalid in ('0', '999', 'abc'):
            self.assertIn('页码无效', await self.call('seeds', invalid))
        self.assertIn('开通农场', await self.call('crops', user_id='other'))
        rendering = self.runtime.rendering
        self.runtime.rendering = None
        try:
            text = await self.call('seeds', message=None)
            self.assertIn('胡萝卜（#1） 2粒', text)
            self.assertNotIn('累计经验', text)
            self.assertIn('暂无作物', await self.call('crops', message=None))
            self.assertEqual(text, await self.call('farm', 'my-seed'))
        finally:
            self.runtime.rendering = rendering

    async def test_steal_target_arguments_and_text_receipts(self):
        from farm_core.domain import Plot
        await self.call('register')
        await self.call('register', user_id='2')
        owner = replace(self.runtime_identity(), user_id='2')
        plant = self.runtime.service.catalogue.get('胡萝卜')
        now = self.runtime.service.clock()
        await self.runtime.service.store.transact(
            owner, 'fixture', 'fixture', {}, now,
            lambda repo: repo.save_plot(Plot(1, plant, now)),
        )
        self.assertIn('偷菜', await self.call('steal'))
        before = await self.runtime.service.snapshot(owner)
        for account in ('1', '2', '9999'):
            self.assertIn('不支持直接输入QQ号', await self.call(
                'steal', account, message='numeric-'+account,
            ))
        self.assertEqual(await self.runtime.service.snapshot(owner), before)
        self.assertIn('自己', await self.call('steal', target_user_id='1'))
        self.assertIn('开通', await self.call('steal', target_user_id='9999'))
        result = await self.call('steal', message='steal', target_user_id='2')
        self.assertIsInstance(result, str)
        self.assertIn('胡萝卜', result)
        self.assertIn('4/5', result)
        repeated = await self.call('steal', message='again', target_user_id='2')
        self.assertIn('本季已偷', repeated)
        self.assertIn('4/5', repeated)
        self.assertIn('目标', await self.call(
            'steal', '2', target_user_id='2', message='invalid',
        ))

    async def test_image_quality_reaches_every_encoder_and_farm_high(self):
        from io import BytesIO
        from PIL import Image
        canvas = importlib.import_module(
            self.package + '._vendor.farm_render.canvas',
        ).Canvas
        original = canvas.encode
        encoded = []

        def encode(instance, codec, quality=75, method=2):
            encoded.append(quality)
            return original(instance, codec, quality, method)

        await self.call('register')
        quality = 48
        self.runtime.image_quality_provider = lambda: quality
        with patch.object(canvas, 'encode', new=encode):
            for configured in (48, 95):
                quality = configured
                for action in ('farm', 'plot_ids', 'details', 'shop',
                               'seeds', 'crops'):
                    with self.subTest(quality=quality, action=action):
                        encoded.clear()
                        content = await self.call(action, message=None)
                        self.assertIsInstance(content, bytes)
                        self.assertTrue(encoded)
                        self.assertEqual(set(encoded), {quality})
                encoded.clear()
                content = await self.call('farm', '高清', message=None)
                self.assertEqual(set(encoded), {max(85, quality)})
                with Image.open(BytesIO(content)) as image:
                    self.assertEqual(image.width, 1536)

    async def test_only_farm_accepts_high_and_warehouse_keeps_text(self):
        await self.call('register')
        for action in ('plot_ids', 'details', 'shop', 'seeds', 'crops'):
            for arguments in ('高清', '1 高清'):
                with self.subTest(action=action, arguments=arguments):
                    self.assertIn('仅我的农场支持高清', await self.call(
                        action, arguments, message=None,
                    ))
        for action in ('seeds', 'crops'):
            self.assertIsInstance(await self.call(action, '1 文字'), str)
        help_text = await self.call('help', '文字')
        self.assertIn('仅我的农场支持高清', help_text)
        self.assertNotIn('地块编号 [高清]', help_text)
        self.assertNotIn('[高清/文字]', help_text)

    async def test_image_quality_validation_and_live_recovery(self):
        await self.call('register')
        for invalid in (0, 96, True, 74.5, '75', None):
            with self.subTest(invalid=invalid):
                self.runtime.image_quality_provider = lambda: invalid
                result = await self.call('farm')
                self.assertIsInstance(result, str)
                self.assertIn('图片质量配置无效', result)
        self.assertIsInstance(await self.call('seeds', '文字'), str)
        self.runtime.image_quality_provider = lambda: 1
        self.assertIsInstance(await self.call('farm'), bytes)
        self.runtime.image_quality_provider = lambda: 95
        self.assertIsInstance(await self.call('farm'), bytes)
        for invalid in (0, 96, True, 74.5, '75'):
            with self.assertRaises(ValueError):
                self.module.Runtime(self.root / 'unused', image_quality=invalid)

    async def test_original_commands_transactions_and_png(self):
        self.assertNotIn("测试农场", self.module.COMMANDS)
        self.assertIn("开通农场", self.module.COMMANDS)
        self.assertIn("我的农场", self.module.COMMANDS)
        self.assertIsInstance(await self.call("register"), str)
        await self.call("buy", "白萝卜 1", "buy")
        before = await self.call("inventory")
        await self.call("buy", "白萝卜 1", "buy")
        self.assertEqual(before, await self.call("inventory"))
        await self.call("sow", "白萝卜 1", "sow")
        result = await self.call("farm", "高清")
        self.assertIsInstance(result, bytes)
        await self.call("farm", "my-seed")
        self.assertIn("成熟", await self.call("harvest", message="harvest"))
        self.assertTrue((self.root / "data/farm-preview.log").exists())

    async def test_shop_filters_and_numbered_commands(self):
        catalogue = self.runtime.service.catalogue
        carrot = catalogue.get("胡萝卜")
        self.runtime.service.catalogue = type(catalogue)([
            carrot,
            replace(carrot, plant_id=9001, purchasable=False, name="禁售菜"),
            replace(carrot, plant_id=9002, enabled=False, name="停用菜"),
            replace(carrot, plant_id=9003, crop_type=11, name="特殊道具"),
        ])
        rendering = self.runtime.rendering
        self.runtime.rendering = None
        try:
            shop = await self.call("shop")
        finally:
            self.runtime.rendering = rendering
        self.assertIn("胡萝卜（#1）", shop)
        for name in ("禁售菜", "停用菜", "特殊道具"):
            self.assertNotIn(name, shop)
        await self.call("register")
        self.assertIn("已完成", await self.call("buy", "#1 1", "number"))
        self.assertIn("不出售", await self.call("buy", "禁售菜 1", "blocked"))
        self.assertIn("（#1）", await self.call("inventory"))

    async def test_shop_image_page_and_buy_by_name_or_id(self):
        from io import BytesIO
        from PIL import Image
        result = await self.call('shop')
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.size, (1024, 1536))
        await self.call('register')
        self.assertIn('已完成', await self.call('buy', '白萝卜 1', 'name'))
        plant = self.runtime.service.catalogue.get('白萝卜')
        self.assertIn('已完成', await self.call(
            'buy', f'#{plant.plant_id} 1', 'id',
        ))
        from unittest.mock import AsyncMock
        self.runtime.rendering.seed_shop = AsyncMock(return_value=b'shop')
        self.assertEqual(await self.call('shop', '2'), b'shop')
        args = self.runtime.rendering.seed_shop.call_args.args
        self.assertEqual(len(args[0]), 6)
        self.assertEqual(args[1].name, '离线玩家')
        self.assertEqual(args[2], 2)
        for page in ('0', '999999'):
            self.assertIn('页码无效', await self.call('shop', page))

    async def test_farm_uses_calendar_theme_and_bee_is_not_a_user_option(self):
        rendering = self.runtime.rendering
        from unittest.mock import AsyncMock
        rendering.my_farm = AsyncMock(return_value=SimpleNamespace(content=b"ok"))
        for now, expected in (
            (1767225600, "winter"), (1775001600, "spring"),
            (1782864000, "summer"), (1790812800, "autumn"),
        ):
            self.runtime.service.clock = lambda: now
            self.assertEqual(await self.call("farm"), b"ok")
            call = rendering.my_farm.call_args
            self.assertEqual(call.kwargs["options"].theme, expected)
            self.assertEqual(call.kwargs["now"], now)
        self.assertEqual(await self.call("farm", "高清"), b"ok")
        self.assertEqual(rendering.my_farm.call_args.kwargs["options"].width, 1536)
        self.assertIn("参数有误", await self.call("farm", "蜂巢"))

    async def test_pest_command_clears_pests_and_preserves_growth(self):
        self.assertEqual(self.module.COMMANDS["农场除虫"], "clear_pests")
        help_text = await self.call("help", "文字")
        self.assertIn("每只虫", help_text)
        self.assertIn("间隔至少2小时", help_text)
        self.runtime.service.clock = lambda: 1000
        await self.call("register")
        await self.call("buy", "白萝卜 1", "buy")
        await self.call("sow", "白萝卜 1", "sow")
        self.assertIn("没有虫", await self.call("clear_pests", message="empty"))
        duration = self.runtime.service.catalogue.get("白萝卜").growth_seconds
        first_pest_at = 1000 + max(7200, (duration + 1) // 2)
        self.runtime.service.clock = lambda: first_pest_at - 1
        self.assertNotIn("虫子1只", await self.call("inventory"))
        self.runtime.service.clock = lambda: first_pest_at
        self.assertIn("虫子1只", await self.call("inventory"))
        first = await self.call("clear_pests", message="clear")
        self.assertIn("除虫已完成", first)
        self.assertEqual(first, await self.call("clear_pests", message="clear"))
        self.assertIn("没有虫", await self.call("clear_pests", message="new"))

    async def test_duplicate_name_reports_numbered_choice(self):
        catalogue = self.runtime.service.catalogue
        carrot = catalogue.get("胡萝卜")
        self.runtime.service.catalogue = type(catalogue)([
            carrot, replace(carrot, plant_id=9001),
        ])
        await self.call("register")
        response = await self.call("buy", "胡萝卜 1", "ambiguous")
        self.assertIn("同名", response)
        self.assertIn("#编号", response)

    async def test_missing_message_id_and_other_identity(self):
        self.assertIn("未执行", await self.call("register", message=None))
        await self.call("register")
        response = await self.call("inventory", user_id="other")
        self.assertIsInstance(response, str)
        self.assertTrue("注册" in response or "开通" in response)
        self.assertNotEqual(
            self.module.operation_id("b", "p", "u", "1", "buy"),
            self.module.operation_id("b", "p", "u", "2", "buy"),
        )

    async def test_farm_details_image_pagination_text_and_single_snapshot(self):
        from io import BytesIO
        from PIL import Image
        from unittest.mock import AsyncMock
        self.assertEqual(self.module.COMMANDS['农场详述'], 'details')
        self.assertEqual(self.module.COMMANDS['我的种子'], 'seeds')
        await self.call('register')
        await self.call('buy', '白萝卜 1', 'buy-details')
        await self.call('sow', '白萝卜 1', 'sow-details')
        before = await self.runtime.service.snapshot(self.runtime_identity())
        with patch.object(self.runtime.service, 'snapshot',
                          new=AsyncMock(return_value=before)) as query:
            image = await self.call('details')
            query.assert_awaited_once()
        with Image.open(BytesIO(image)) as decoded:
            self.assertEqual(decoded.width, 1024)
        self.assertIsInstance(await self.call('inventory'), str)
        self.assertIn('页码无效', await self.call('details', '999'))
        self.assertIsInstance(await self.call('farm', 'detail'), bytes)
        rendering = self.runtime.rendering
        self.runtime.rendering = None
        try:
            text = await self.call('details')
            self.assertIn('白萝卜', text)
            self.assertIn('1/1季', text)
            self.assertNotIn('被偷', text)
        finally:
            self.runtime.rendering = rendering

    def runtime_identity(self):
        identity = importlib.import_module(
            self.package + '._vendor.farm_core',
        ).Identity
        return identity(self.runtime.deployment, self.context['bot_id'],
                        self.context['platform'], self.context['user_id'])

    async def test_invalid_arguments_and_missing_font_are_explicit(self):
        await self.call("register")
        for action, arguments in (("buy", "白萝卜 nope"),
                                  ("sow", "白萝卜 -2"),
                                  ("lock", ""), ("farm", "unknown")):
            self.assertIsInstance(await self.call(action, arguments), str)
        other = self.module.Runtime(
            self.root / "without-font", self.root / "missing.ttf",
        )
        self.seed_assets(other)
        await other.start()
        try:
            response = await other.execute("farm", "", **self.context)
            self.assertIn("FARM_PREVIEW_FONT", response)
        finally:
            await other.close()

    async def test_default_font_uses_host_resources_and_skips_broken_font(self):
        fonts = self.root / "host-fonts"
        fonts.mkdir()
        (fonts / "HYWenHei-85W.ttf").write_bytes(b"broken")
        shutil.copyfile(choose_font(), fonts / "msyh.ttf")
        other = self.module.Runtime(self.root / "default-font", font_dir=fonts)
        self.seed_assets(other)
        await other.start()
        try:
            self.assertIsNotNone(other.rendering)
            self.assertEqual(
                other.rendering.renderer.font_path,
                (fonts / "msyh.ttf").resolve(),
            )
            await other.execute("register", "", **self.context)
            result = await other.execute("farm", "", **self.context)
            self.assertIsInstance(result, bytes)
        finally:
            await other.close()

    async def test_explicit_font_overrides_host_defaults(self):
        explicit = Path(choose_font()).resolve()
        other = self.module.Runtime(
            self.root / "explicit-font", explicit,
            font_dir=self.root / "not-present",
        )
        self.seed_assets(other)
        await other.start()
        try:
            self.assertEqual(other.rendering.renderer.font_path, explicit)
        finally:
            await other.close()

    async def test_insufficient_funds_has_chinese_message_and_no_debit(self):
        await self.call("register")
        before = await self.call("inventory")
        self.assertEqual(
            await self.call("buy", "白萝卜 100000", "too-expensive"),
            "余额不足。",
        )
        self.assertEqual(before, await self.call("inventory"))

    async def test_existing_preview_directory_is_ignored(self):
        old = self.root / 'directories/farm_preview'
        target = old.with_name('farm_db')
        previous = self.module.Runtime(old, choose_font())
        self.seed_assets(previous)
        await previous.start()
        try:
            await previous.execute('register', '旧农场', **self.context)
        finally:
            await previous.close()
        old_database = old / 'farm.sqlite3'
        before = old_database.read_bytes()
        target.mkdir()
        current = self.module.Runtime(target, choose_font())
        self.seed_assets(current)
        await current.start()
        try:
            self.assertEqual(old_database.read_bytes(), before)
            self.assertTrue((target / 'farm.sqlite3').is_file())
            self.assertEqual(await current.execute(
                'inventory', '', **self.context,
            ), '请先发送：开通农场')
        finally:
            await current.close()

    async def test_first_command_imports_legacy_and_binds_identity(self):
        from test_legacy_migration import create_legacy

        source = self.root / 'data/farm.db'
        create_legacy(source)
        before = source.read_bytes()
        result = await self.call('inventory')
        self.assertIn('旧农场', result)
        self.assertIn('1234', result)
        self.assertTrue((self.root / 'data/farm.sqlite3').is_file())
        self.assertFalse((self.root / 'data/farm-preview.sqlite3').exists())
        self.assertEqual(await self.call('inventory'), result)
        self.assertIn('已绑定其他机器人或平台', await self.call(
            'register', bot_id='other',
        ))
        self.assertEqual(source.read_bytes(), before)

    async def test_failed_migration_does_not_register_empty_account(self):
        from test_legacy_migration import create_legacy
        import sqlite3

        source = self.root / 'data/farm.db'
        create_legacy(source)
        with closing(sqlite3.connect(source)) as db, db:
            db.execute("UPDATE userSeed SET seed='不存在的作物'")
        self.assertIn('无法迁移', await self.call('register'))
        identity = self.module.Identity(
            'zhenxun-preview', 'bot', 'OneBot V11', '1',
        )
        with self.assertRaisesRegex(self.module.FarmError, 'not_registered'):
            await self.runtime.store.snapshot(identity)

    async def test_mock_host_load_registers_hooks_and_original_matchers(self):
        hooks = {"start":[], "close":[], "commands":{}}
        driver = SimpleNamespace(
            config=SimpleNamespace(),
            on_startup=hooks["start"].append,
            on_shutdown=hooks["close"].append,
        )
        nonebot = ModuleType("nonebot")
        nonebot.get_driver = lambda: driver
        nonebot.require = lambda _: None

        def register(name, **kwargs):
            return SimpleNamespace(handle=lambda: (
                lambda handler: hooks["commands"].update({name:handler})
            ))

        nonebot.on_command = register
        adapters = ModuleType("nonebot.adapters")
        adapters.Bot = adapters.Event = adapters.Message = type(
            "HostType", (), {},
        )
        params = ModuleType("nonebot.params")
        params.CommandArg = lambda: None
        uninfo = ModuleType("nonebot_plugin_uninfo")
        uninfo.Uninfo = type("Uninfo", (), {})
        paths = ModuleType("zhenxun.configs.path_config")
        paths.DATA_PATH = self.root
        paths.FONT_PATH = self.root / "fonts"
        messages = ModuleType("zhenxun.utils.message")
        sent = []

        async def send(**kwargs):
            return None

        messages.MessageUtils = SimpleNamespace(build_message=lambda content: (
            sent.append(content) or SimpleNamespace(send=send)
        ))
        platform = ModuleType("zhenxun.utils.platform")
        platform.PlatformUtils = SimpleNamespace()
        config = ModuleType("zhenxun.configs.config")
        quality_values = {'value': 49}

        def configured_value(key, default, **kwargs):
            if key != '农场图片质量':
                return default
            value = quality_values['value']
            return value if not kwargs['build_model'] else int(value)

        config.Config = SimpleNamespace(
            get=lambda module: SimpleNamespace(
                configs={}, get=configured_value,
            ),
            get_config=lambda *args, **kwargs: int(quality_values['value']),
            _simple_data={},
        )
        modules = {m.__name__:m for m in (
            nonebot, adapters, params, uninfo, paths, messages, platform, config,
        )}
        with patch.dict(sys.modules, modules):
            imported = importlib.import_module(self.package + ".commands")
            self.assertEqual(imported.runtime.image_quality_provider(), 49)
            quality_values['value'] = 91
            self.assertEqual(imported.runtime.image_quality_provider(), 91)
            quality_values['value'] = 74.5
            self.assertEqual(imported.runtime.image_quality_provider(), 74.5)
            quality_values['value'] = True
            self.assertIs(imported.runtime.image_quality_provider(), True)
            quality_values['value'] = 75
            self.assertEqual(imported.runtime.data_dir,
                             (self.root / 'farm_db').resolve())
            self.assertEqual(set(hooks["commands"]), set(self.module.COMMANDS))
            self.assertEqual(len(hooks["start"]), 1)
            self.assertEqual(imported.resource_options(), ('Github', ''))
            self.seed_assets(imported.runtime)
            await hooks["start"][0]()
            try:
                bot = SimpleNamespace(self_id="bot", adapter=SimpleNamespace(
                    get_name=lambda:"OneBot V11",
                ))
                await hooks["commands"]["开通农场"](
                    bot, SimpleNamespace(message_id="m1"),
                    SimpleNamespace(user=SimpleNamespace(id="u", name="用户")),
                    SimpleNamespace(extract_plain_text=lambda:""),
                )
                self.assertTrue(sent)
                from unittest.mock import AsyncMock

                class Arguments(list):
                    def extract_plain_text(self):
                        return ''

                for segment in (
                    SimpleNamespace(type='at', data={'qq': '123'}),
                    SimpleNamespace(type='mention_user',
                                    data={'user_id': '123'}),
                ):
                    with patch.object(imported.runtime, 'execute',
                                      new=AsyncMock(return_value='结果')) as run:
                        await hooks['commands']['偷菜'](
                            bot, SimpleNamespace(message_id='steal'),
                            SimpleNamespace(user=SimpleNamespace(
                                id='u', name='用户',
                            )), Arguments([segment]),
                        )
                        self.assertEqual(run.await_args.kwargs[
                            'target_user_id'], '123')
            finally:
                await hooks["close"][0]()
            self.assertFalse(imported.runtime.started)
