"""在临时目录加载真实 NoneBot 插件，离线验证生命周期与命令适配。"""

import argparse
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


async def exercise(module, bot, event, Message, UniMessage):
    from nonebot_plugin_alconna import Image

    runtime = module.runtime
    await runtime.start()
    try:
        session = SimpleNamespace(user=SimpleNamespace(id="10001", name="测试"))
        with patch.object(UniMessage, "send", autospec=True) as send:
            await module.handler_for("register")(
                bot, event, session, Message(),
            )
            if "开通" not in str(send.call_args.args[0]):
                raise AssertionError("Registration handler failed")
            await module.handler_for("farm")(
                bot, event, session, Message(),
            )
            # 无字体环境允许文字退化；有字体时必须生成统一图片段。
            response = send.call_args.args[0]
            if runtime.rendering and not response[Image]:
                raise AssertionError("Image response was not a UniMessage")
            await module.handler_for("steal")(
                bot, event, session, Message("[CQ:at,qq=10002]"),
            )
            if "目标尚未" not in str(send.call_args.args[0]):
                raise AssertionError("Mention target was not mapped")
            await module.handler_for("steal")(
                bot, event, session, Message("[CQ:at,qq=all]"),
            )
            if "具体" not in str(send.call_args.args[0]):
                raise AssertionError("Everyone mention was not rejected")
        context = dict(
            bot_id=str(bot.self_id), platform=bot.adapter.get_name(),
            user_id="10001", message_id="buy",
        )
        first = await runtime.execute("buy", "胡萝卜 1", **context)
        second = await runtime.execute("buy", "胡萝卜 1", **context)
        if first != second:
            raise AssertionError("Repeated event was not idempotent")
        context["message_id"] = None
        refused = await runtime.execute("sow", "胡萝卜 1", **context)
        if "未执行" not in refused:
            raise AssertionError("Write without message ID was accepted")
    finally:
        await runtime.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path)
    args = parser.parse_args()
    if args.repository:
        sys.path.insert(0, str(args.repository.resolve()))
    import nonebot
    from nonebot.adapters.onebot.v11 import Adapter, Bot, Message
    from nonebot.adapters.onebot.v11.event import PrivateMessageEvent

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        nonebot.init(
            driver="~none",
            localstore_data_dir=root / "data",
            localstore_config_dir=root / "config",
            localstore_cache_dir=root / "cache",
        )
        driver = nonebot.get_driver()
        driver.register_adapter(Adapter)
        plugin = nonebot.load_plugin("nonebot_plugin_farm")
        if plugin is None:
            raise AssertionError("NoneBot plugin failed to load")
        from nonebot_plugin_farm import commands, __version__
        from nonebot_plugin_alconna import UniMessage

        expected = (root / "data/nonebot_plugin_farm"
                    / "nonebot_plugin_farm/farm_db")
        if commands.runtime.data_dir != expected.resolve():
            raise AssertionError("Legacy localstore directory changed")
        adapter = driver._adapters[Adapter.get_name()]
        bot = Bot(adapter, "12345")
        event = PrivateMessageEvent(
            time=0, self_id=12345, post_type="message",
            sub_type="friend", user_id=10001, message_type="private",
            message_id=1, message=Message(), original_message=Message(),
            raw_message="", font=0, sender={"user_id": 10001},
        )
        asyncio.run(exercise(commands, bot, event, Message, UniMessage))
        if any(name == "zhenxun" or name.startswith("zhenxun.")
               for name in sys.modules):
            raise AssertionError("Unexpected Zhenxun import")
        print(f"NoneBot {__version__}: load, lifecycle, messages checked")


if __name__ == "__main__":
    main()
