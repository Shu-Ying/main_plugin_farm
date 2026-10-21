"""普通 NoneBot 配置；不依赖真寻配置系统。"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Config(BaseModel):
    """农场启动配置。"""

    farm_data_dir: Optional[Path] = Field(
        None, description="数据目录；默认兼容旧版 localstore 农场目录",
    )
    farm_font: Optional[Path] = Field(
        None, description="中文字体路径；不可用时退回文字响应",
    )
    farm_deployment: str = Field(
        "nonebot", min_length=1, description="农场存档部署标识",
    )
    farm_image_format: Literal["AUTO", "JPEG", "PNG"] = Field(
        "AUTO", description="图片格式，AUTO 优先使用压缩 JPEG",
    )
