"""真寻接入编排；核心私有导入，测试数据与旧版隔离。"""

import hashlib
import json
import logging
from pathlib import Path
import shlex

from ._vendor.farm_core import Catalogue, FarmService, Identity, SQLiteStore
from ._vendor.farm_core.domain import FarmError
from ._vendor.farm_core.presentation import receipt_text, snapshot_text
from ._vendor.farm_render import FarmRenderer, RenderOptions, RenderService

logger = logging.getLogger(__name__)
COMMANDS = {
    "开通农场":"register", "我的农场":"farm", "农场详述":"inventory",
    "我的农场币":"inventory", "我的点券":"inventory",
    "我的种子":"inventory", "我的作物":"inventory",
    "种子商店":"shop", "农场帮助":"help", "购买种子":"buy",
    "播种":"sow", "收获":"harvest", "铲除":"eradicate",
    "作物加锁":"lock", "作物解锁":"unlock", "出售作物":"sell",
}
HELP = (
    "开通农场 [名称]｜我的农场 [高清]｜农场详述\n"
    "种子商店 [页码]｜购买种子 作物 数量｜播种 作物 [数量]\n"
    "收获｜铲除｜我的种子｜我的作物\n"
    "作物加锁 作物｜作物解锁 作物｜出售作物 [作物] [数量]\n"
    "本版使用独立预览数据库，不会读取旧版资产。"
)
ERRORS = {
    "not_registered":"请先发送：开通农场",
    "unknown_plant":"没有这种作物，请查看种子商店。",
    "invalid_integer":"数量必须为有效的正整数。",
    "insufficient_funds":"余额不足。",
    "insufficient_stock":"库存不足。",
    "insufficient_empty_plots":"空地不足。",
    "level_required":"等级不足。", "plant_locked":"该作物已锁定。",
    "nothing_to_harvest":"当前没有成熟作物。",
    "nothing_to_eradicate":"当前没有枯萎作物。",
    "nothing_to_sell":"当前没有可出售作物。",
    "operation_conflict":"该事件已处理但参数不一致，请发送新消息。",
}


def operation_id(bot_id, platform, user_id, message_id, action):
    if message_id is None or str(message_id) == "":
        return None
    return hashlib.sha256(json.dumps(
        [str(bot_id), platform, user_id, str(message_id), action],
        ensure_ascii=False,
    ).encode()).hexdigest()


class Runtime:
    def __init__(self, data_dir, font_path=None, deployment="zhenxun-preview",
                 image_format="AUTO"):
        self.data_dir = Path(data_dir).resolve()
        self.font_path = font_path
        self.deployment = deployment
        self.image_format = image_format
        self.store = SQLiteStore(self.data_dir / "farm-preview.sqlite3")
        self.service = FarmService(self.store, Catalogue.bundled())
        self.rendering = None
        self.started = False
        self.log_handler = None

    async def start(self):
        if self.started:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        await self.store.initialize()
        self.log_handler = logging.FileHandler(
            self.data_dir / "farm-preview.log", encoding="utf-8",
        )
        self.log_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
        ))
        logging.getLogger(__package__).setLevel(logging.INFO)
        logging.getLogger(__package__).addHandler(self.log_handler)
        if self.font_path:
            try:
                self.rendering = RenderService(FarmRenderer(self.font_path))
            except (ValueError, OSError):
                logger.warning("farm preview font unavailable; text mode only")
        self.started = True
        logger.info("farm preview initialized schema=1")

    async def close(self):
        try:
            if self.rendering:
                await self.rendering.close()
        finally:
            await self.store.close()
            self.started = False
            if self.log_handler:
                logging.getLogger(__package__).removeHandler(self.log_handler)
                self.log_handler.close()
                self.log_handler = None

    async def execute(
        self, action, arguments, *, bot_id, platform, user_id, message_id,
        display_name="农场玩家", avatar=None,
    ):
        if not self.started:
            return "农场尚未初始化，请检查启动日志。"
        try:
            who = Identity(self.deployment, str(bot_id), platform, str(user_id))
            args = shlex.split(arguments)
            if action == "farm" and args:
                aliases = {
                    "detail":"inventory", "my-point":"inventory",
                    "my-vipPoint":"inventory", "my-seed":"inventory",
                    "my-plant":"inventory", "seed-shop":"shop",
                    "buy-seed":"buy", "sowing":"sow", "harvest":"harvest",
                    "eradicate":"eradicate", "lock-plant":"lock",
                    "unlock-plant":"unlock", "sell-plant":"sell",
                    "farm-help":"help",
                }
                if args[0] in aliases:
                    action = aliases[args[0]]
                    args = args[1:]
            op = operation_id(
                bot_id, platform, str(user_id), message_id, action,
            )
            if action == "help":
                return HELP
            if action == "shop":
                page = int(args[0]) if args else 1
                if not 1 <= page <= 100 or len(args) > 1:
                    raise ValueError()
                plants = sorted(
                    self.service.catalogue, key=lambda p: p.plant_id,
                )
                chunk = plants[(page-1)*12:page*12]
                return "种子商店 " + str(page) + "页\n" + "\n".join(
                    f"{p.name}：{p.cost}{'点券' if p.is_vip else '农场币'}"
                    f" / 等级{p.level}" for p in chunk
                )
            if action == "inventory":
                if args:
                    raise ValueError()
                return snapshot_text(await self.service.snapshot(who))
            if action == "farm":
                if args not in ([], ["高清"]):
                    raise ValueError()
                if not self.rendering:
                    return "请配置 FARM_PREVIEW_FONT 为可用中文字体路径。"
                options = (RenderOptions.high(format=self.image_format)
                           if args else RenderOptions(format=self.image_format))
                picture = await self.rendering.my_farm(
                    self.service, who, options=options, avatar=avatar,
                    supported=("JPEG",),
                )
                return picture.content
            if op is None:
                return "无法取得稳定消息标识，本次写操作未执行。"
            if action == "register":
                name = " ".join(args) if args else display_name
                name = " ".join(str(name).split())[:64] or "农场玩家"
                receipt = await self.service.register(who, name, op)
            elif action in ("buy", "sow", "sell"):
                if action == "sell" and not args:
                    receipt = await self.service.sell(who, None, None, op)
                else:
                    if len(args) not in (1, 2) or (action == "buy"
                                                 and len(args) != 2):
                        raise ValueError()
                    count = int(args[1]) if len(args) == 2 else None
                    receipt = await getattr(self.service, action)(
                        who, args[0], count, op,
                    )
            elif action in ("lock", "unlock"):
                if len(args) != 1:
                    raise ValueError()
                receipt = await self.service.lock(
                    who, args[0], action == "lock", op,
                )
            elif action in ("harvest", "eradicate"):
                if args:
                    raise ValueError()
                receipt = await getattr(self.service, action)(who, op)
            else:
                return HELP
            return receipt_text(receipt)
        except FarmError as error:
            return ERRORS.get(error.code, "操作未完成：" + error.code)
        except ValueError:
            return "参数有误，请发送：农场帮助"
