"""纯快照农场合成：目标尺寸、独立素材、可见状态成图缓存。"""

from dataclasses import replace
import hashlib
from io import BytesIO
import logging
from pathlib import Path
from time import perf_counter

from PIL import Image, ImageDraw, UnidentifiedImageError

from .assets import Assets, ByteLRU
from .canvas import Canvas, font
from .layout import scene_from_snapshot
from .models import RenderOptions, RenderResult

logger = logging.getLogger(__name__)
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 4_000_000


class FarmRenderer:
    def __init__(
        self, font_path, asset_cache_bytes=32 * 1024 * 1024,
        result_cache_bytes=8 * 1024 * 1024,
    ):
        self.font_path = Path(font_path).resolve()
        if not self.font_path.is_file():
            raise ValueError("Configure an existing Chinese font path")
        font(self.font_path, 16)
        self.assets = Assets(asset_cache_bytes)
        self.results = ByteLRU(result_cache_bytes)

    def scene(self, identity, snapshot, now):
        return scene_from_snapshot(
            identity, snapshot, now, self.assets.metadata,
        )

    def request_key(
        self, identity, snapshot, now, options=None, avatar=None,
        supported=("JPEG",),
    ):
        options = options or RenderOptions()
        if avatar is not None and not isinstance(avatar, bytes):
            raise ValueError("Avatar must be bytes or None")
        digest = hashlib.sha256(avatar).hexdigest() if (
            avatar and len(avatar) <= MAX_AVATAR_BYTES
        ) else "default"
        scene = self.scene(identity, snapshot, now)
        return scene, options, options.codec(supported), digest

    def render(
        self, identity, snapshot, now, options=None, avatar=None,
        supported=("JPEG",),
    ):
        key = self.request_key(
            identity, snapshot, now, options, avatar, supported,
        )
        cached = self.results.get(key)
        if cached is not None:
            logger.info("farm render cache=hit bytes=%s", len(cached.content))
            return replace(cached, cache_hit=True, compose_ms=0, encode_ms=0)
        scene, options, codec, _ = key
        started = perf_counter()
        canvas = self._base(scene, options)
        self._plants(canvas, scene, options)
        self._panel(canvas, scene, options, avatar)
        composed = perf_counter()
        content = canvas.encode(codec, options.quality, options.method)
        encoded = perf_counter()
        result = RenderResult(
            content, {"JPEG":"image/jpeg", "PNG":"image/png",
                      "WEBP":"image/webp"}[codec],
            *canvas.image.size, (composed - started) * 1000,
            (encoded - composed) * 1000,
        )
        self.results.put(key, result, len(content) + 4096)
        logger.info(
            "farm render cache=miss compose_ms=%.2f encode_ms=%.2f "
            "width=%s height=%s bytes=%s codec=%s",
            result.compose_ms, result.encode_ms, result.width,
            result.height, len(content), codec,
        )
        return result

    @staticmethod
    def _scale(value, options):
        return round(value * options.width / 3072)

    def _base(self, scene, options):
        slots = frozenset(p.slot for p in scene.plots)
        key = ("base", options.theme, options.width, slots)
        cached = self.assets.cache.get(key)
        if cached is not None:
            return Canvas(cached.copy())
        s = lambda n: self._scale(n, options)
        size = (options.width, s(1872))
        background = self.assets.image(
            "background/decorateIcon/"
            f"decorate_{options.theme}_1.jpg", size,
        )
        canvas = Canvas(background)
        soil_size = tuple(max(1, s(n)) for n in (
            self.assets.metadata["soil_size"]
        ))
        tiles = {
            True: self.assets.image("soil/普通土地.png", soil_size),
            False: self.assets.image("soil/草土地.png", soil_size),
        }
        expansion = False
        for slot, pos in enumerate(self.assets.metadata["positions"], 1):
            xy = (s(pos["x"]), s(pos["y"]))
            canvas.paste(tiles[slot in slots], xy)
            if slot not in slots and not expansion:
                icon = self.assets.image(
                    "background/expansion.png", (max(1, s(90)),) * 2,
                )
                canvas.paste(icon, (xy[0] + s(70), xy[1] + s(10)))
                expansion = True
        self.assets.cache.put(key, canvas.image, size[0] * size[1] * 4)
        return canvas.copy()

    def _plants(self, canvas, scene, options):
        s = lambda n: self._scale(n, options)
        soil_w, soil_h = self.assets.metadata["soil_size"]
        first_ripe = True
        for plot in scene.plots:
            if not plot.sprite:
                continue
            pos = self.assets.metadata["positions"][plot.slot - 1]
            metadata = self.assets.metadata["images"].get(plot.sprite)
            if metadata is None:
                logger.warning("farm render missing packaged crop sprite")
                plant = Image.new("RGBA", (max(1, s(60)),) * 2, "#597b45")
                ImageDraw.Draw(plant).text(
                    (s(10), 0), "?", fill="white",
                    font=font(self.font_path, max(10, s(48))),
                )
            else:
                size = plot.size or metadata["size"]
                plant = self.assets.image(
                    plot.sprite, tuple(max(1, s(n)) for n in size),
                )
            offset_x, offset_y = plot.offset
            xy = (
                s(pos["x"] + soil_w / 2 + offset_x) - plant.width // 2,
                s(pos["y"] + soil_h / 2 + offset_y) - plant.height // 2,
            )
            canvas.paste(plant, xy)
            if plot.state == "ripe" and first_ripe:
                icon = self.assets.image(
                    "background/ripe.png", (max(1, s(100)),) * 2,
                )
                canvas.paste(icon, (s(pos["x"] + 70), s(pos["y"] - 80)))
                first_ripe = False

    def _avatar(self, content, size):
        if content and len(content) <= MAX_AVATAR_BYTES:
            try:
                with Image.open(BytesIO(content)) as image:
                    if image.width * image.height > MAX_AVATAR_PIXELS:
                        raise ValueError("Avatar dimensions exceed limit")
                    image.thumbnail(size, Image.Resampling.LANCZOS)
                    avatar = Image.new("RGBA", size, "#cce3c1")
                    avatar.alpha_composite(image.convert("RGBA"), (
                        (size[0] - image.width) // 2,
                        (size[1] - image.height) // 2,
                    ))
                    return avatar
            except (UnidentifiedImageError, OSError, ValueError,
                    Image.DecompressionBombError):
                logger.warning("farm render avatar rejected; using default")
        avatar = Image.new("RGBA", size, "#dce8cf")
        draw = ImageDraw.Draw(avatar)
        w, h = size
        draw.ellipse((w*.3, h*.12, w*.7, h*.52), fill="#6f8a54")
        draw.ellipse((w*.15, h*.55, w*.85, h*1.2), fill="#6f8a54")
        return avatar

    def _panel(self, canvas, scene, options, avatar):
        s = lambda n: self._scale(n, options)
        canvas.rectangle(
            tuple(s(n) for n in (90, 75, 1160, 425)),
            "#fff9e8", s(24),
        )
        canvas.paste(self._avatar(avatar, (s(170), s(170))), (s(125), s(125)))
        size = max(12, s(55))
        name = canvas.fit_text(
            scene.account.name, self.font_path, size, s(790),
        )
        canvas.text((s(330), s(105)), name, self.font_path, size, "#493525")
        account = scene.account
        lines = (
            f"等级 {account.level}    经验 {account.experience}",
            f"农场币 {account.point}    点券 {account.vip_point}",
            f"已解锁 {len(scene.plots)}/30 块地",
        )
        for index, line in enumerate(lines):
            size = max(10, s(43))
            text = canvas.fit_text(line, self.font_path, size, s(790))
            canvas.text(
                (s(330), s(195 + index * 65)), text,
                self.font_path, size, "#674d34",
            )
