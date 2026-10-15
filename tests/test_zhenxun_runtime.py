import asyncio
import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
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
        build(ROOT, self.root / "built", "0.1.0-preview.1")
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
        other = self.module.Runtime(self.root / "without-font")
        await other.start()
        try:
            response = await other.execute("farm", "", **self.context)
            self.assertIn("FARM_PREVIEW_FONT", response)
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
