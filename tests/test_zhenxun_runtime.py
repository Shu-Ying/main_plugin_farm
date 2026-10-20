import asyncio
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
        await self.runtime.start()
        self.context = dict(bot_id="bot", platform="OneBot V11", user_id="1",
                            message_id="registration", display_name="离线玩家")

    async def asyncTearDown(self):
        await self.runtime.close()
        for name in tuple(sys.modules):
            if name == self.package or name.startswith(self.package + "."):
                del sys.modules[name]
        self.temporary.cleanup()

    async def call(self, action, arguments="", message="event", **changes):
        return await self.runtime.execute(
            action, arguments,
            **{**self.context, "message_id":message, **changes},
        )

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
        shop = await self.call("shop")
        self.assertIn("胡萝卜（#1）", shop)
        for name in ("禁售菜", "停用菜", "特殊道具"):
            self.assertNotIn(name, shop)
        await self.call("register")
        self.assertIn("已完成", await self.call("buy", "#1 1", "number"))
        self.assertIn("不出售", await self.call("buy", "禁售菜 1", "blocked"))
        self.assertIn("（#1）", await self.call("inventory"))

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
        self.assertIn("每只虫", await self.call("help"))
        self.runtime.service.clock = lambda: 1000
        await self.call("register")
        await self.call("buy", "白萝卜 1", "buy")
        await self.call("sow", "白萝卜 1", "sow")
        self.assertIn("没有虫", await self.call("clear_pests", message="empty"))
        duration = self.runtime.service.catalogue.get("白萝卜").growth_seconds
        self.runtime.service.clock = lambda: 1000 + max(3600, (duration+3)//4)
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

    async def test_invalid_arguments_and_missing_font_are_explicit(self):
        await self.call("register")
        for action, arguments in (("buy", "白萝卜 nope"),
                                  ("sow", "白萝卜 -2"),
                                  ("lock", ""), ("farm", "unknown")):
            self.assertIsInstance(await self.call(action, arguments), str)
        other = self.module.Runtime(
            self.root / "without-font", self.root / "missing.ttf",
        )
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

    async def test_mock_host_load_registers_hooks_and_original_matchers(self):
        hooks = {"start":[], "close":[], "commands":{}}
        driver = SimpleNamespace(
            config=SimpleNamespace(farm_preview_data_dir=self.root / "host"),
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
        modules = {m.__name__:m for m in (
            nonebot, adapters, params, uninfo, paths, messages, platform,
        )}
        with patch.dict(sys.modules, modules):
            imported = importlib.import_module(self.package + ".commands")
            self.assertEqual(set(hooks["commands"]), set(self.module.COMMANDS))
            self.assertEqual(len(hooks["start"]), 1)
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
            finally:
                await hooks["close"][0]()
            self.assertFalse(imported.runtime.started)
