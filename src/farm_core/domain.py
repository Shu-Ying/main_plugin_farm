"""不可变领域数据及源自旧版的纯计算规则。"""

from dataclasses import asdict, dataclass
from enum import Enum
from math import isqrt
import json
from typing import Any

MAX_VALUE = 2**63 - 1
MAX_QUANTITY = 1_000_000


class FarmError(ValueError):
    """可由接入层区分的业务失败。"""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class StorageError(RuntimeError):
    """数据库故障，不得作为无农场或业务成功处理。"""


class SchemaError(StorageError):
    """数据库不属于本核心或 schema 不兼容。"""


class Asset(str, Enum):
    """资产字段；经验与两种货币分别记账。"""

    POINT = "point"  # 农场币。
    VIP_POINT = "vip_point"  # 点券，不与农场币自动兑换。
    EXPERIENCE = "experience"  # 累计经验。


def integer(value: int, minimum: int = 0, maximum: int = MAX_VALUE) -> int:
    """拒绝布尔值、非整数及超出明确范围的数值。"""
    if type(value) is not int or not minimum <= value <= maximum:
        raise FarmError("invalid_integer")
    return value


def text(value: str, maximum: int = 128) -> str:
    """身份和操作标识必须是有界的非空字符串。"""
    if not isinstance(value, str) or not value.strip():
        raise FarmError("invalid_text")
    if len(value) > maximum or any(ord(char) < 32 for char in value):
        raise FarmError("invalid_text")
    return value


def quantity(value: int) -> int:
    return integer(value, 1, MAX_QUANTITY)


def level_for(experience: int) -> int:
    """沿用 200*k*(k+1)//2 门槛，避免浮点误差。"""
    return (isqrt(1 + integer(experience) // 25) - 1) // 2


def boosted(base: int, percent: int = 0) -> int:
    """单地块向下取整；调用方只对各地块结果求和。"""
    integer(base)
    integer(percent, -100, 10_000)
    return integer(base * (100 + percent) // 100)


@dataclass(frozen=True)
class Identity:
    """调用方明确提供的身份，核心不猜测账号等价性。"""

    deployment: str  # 独立部署标识。
    realm: str  # 调用方决定的游戏共享范围。
    platform: str  # 消息平台命名空间，不是机器人框架名称。
    user_id: str  # 平台用户标识，始终保存为字符串。

    def __post_init__(self):
        for value in asdict(self).values():
            text(value)

    @property
    def key(self) -> str:
        return json.dumps(
            list(asdict(self).values()), ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class Plant:
    """播种时保存的不可变结算定义。"""

    plant_id: int  # 旧作物目录 ID。
    name: str  # 唯一作物名称。
    level: int  # 购买等级门槛。
    buy: int  # 普通种子农场币价格。
    is_vip: bool  # 是否使用点券购买。
    vip_buy: int  # 点券种子价格。
    experience: int  # 每季基础经验。
    harvest: int  # 每季基础产量。
    price: int  # 每个收获物的农场币售价。
    growth_seconds: int  # 首次成熟所需秒数。
    crop: int  # 最多可收获季数。
    regrowth_seconds: int  # 兼容旧版的多季再生长秒数。

    def __post_init__(self):
        text(self.name)
        if type(self.is_vip) is not bool:
            raise FarmError("invalid_catalogue")
        for name in (
            "plant_id", "growth_seconds", "crop", "regrowth_seconds",
            "harvest",
        ):
            integer(getattr(self, name), 1)
        for name in ("level", "buy", "vip_buy", "experience", "price"):
            integer(getattr(self, name))

    @property
    def asset(self) -> Asset:
        return Asset.VIP_POINT if self.is_vip else Asset.POINT

    @property
    def cost(self) -> int:
        return self.vip_buy if self.is_vip else self.buy

    @classmethod
    def from_legacy(cls, row: dict[str, Any]) -> "Plant":
        try:
            for key in (
                "id", "level", "buy", "isVip", "vipBuy", "experience",
                "harvest", "price", "time", "crop",
            ):
                integer(row[key])
            if row["isVip"] not in (0, 1):
                raise FarmError("invalid_catalogue")
            if not isinstance(row["phase"], str):
                raise FarmError("invalid_catalogue")
            parts = row["phase"].split(",")
            if not parts or any(not p.isascii() or not p.isdigit()
                                for p in parts):
                raise FarmError("invalid_catalogue")
            phases = list(dict.fromkeys(int(part) for part in parts))
            for phase in phases:
                integer(phase, 1)
            if len(phases) < 2 or phases != sorted(phases):
                raise FarmError("invalid_catalogue")
            return cls(
                row["id"], row["name"], row["level"], row["buy"],
                bool(row["isVip"]), row["vipBuy"], row["experience"],
                row["harvest"], row["price"], row["time"] * 3600,
                row["crop"], sum(phases[1:]),
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FarmError("invalid_catalogue") from exc


@dataclass(frozen=True)
class Account:
    """已提交的账户查询快照。"""

    name: str  # 农场名称。
    point: int  # 当前农场币。
    vip_point: int  # 当前点券。
    experience: int  # 当前累计经验。

    @property
    def level(self) -> int:
        return level_for(self.experience)


@dataclass(frozen=True)
class InventoryItem:
    """同一作物的种子、产物和锁定状态。"""

    name: str  # 作物名称。
    seeds: int = 0  # 未播种种子数。
    crops: int = 0  # 已收获产物数。
    locked: bool = False  # 是否禁止出售产物。


@dataclass(frozen=True)
class Plot:
    """地块状态；空地无 plant，最后一季后保留枯萎实例。"""

    slot: int  # 从 1 开始的地块编号。
    plant: Plant | None = None  # 播种时冻结的作物规则。
    mature_at: int | None = None  # 下一季成熟 UTC 秒数。
    harvest_count: int = 0  # 当前实例已收获季数。
    yield_bonus: int = 0  # 此地块产量加成百分比。
    experience_bonus: int = 0  # 此地块经验加成百分比。

    @property
    def withered(self) -> bool:
        return self.plant is not None and self.harvest_count >= self.plant.crop


@dataclass(frozen=True)
class Snapshot:
    """同一数据库读事务内取得的一致快照。"""

    account: Account  # 账户。
    inventory: tuple[InventoryItem, ...]  # 按名称排序的仓库。
    plots: tuple[Plot, ...]  # 按编号排序的地块。


@dataclass(frozen=True)
class Receipt:
    """可持久化、可重放的交易结果；data 只是脱离数据库的返回副本。"""

    operation_id: str  # 调用方稳定提供的幂等操作标识。
    action: str  # 已提交的业务动作。
    data: dict[str, Any]  # 实际成交数值与提交后的资产。
