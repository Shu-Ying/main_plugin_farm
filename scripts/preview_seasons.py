"""离线生成四季与蜂巢底图，以及同一农场状态的主题对照。"""

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ci_font import choose_font
from farm_core import Identity
from farm_render import FarmRenderer, RenderOptions
from farm_render.canvas import Canvas
from render_demo import demonstration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    renderer = FarmRenderer(args.font or choose_font())
    who = Identity("preview", "local", "qq", "seasons")
    snapshot, now = demonstration()
    themes = (("spring", "春季"), ("summer", "夏季"), ("autumn", "秋季"),
              ("winter", "冬季"), ("bee", "蜂巢 · 仅预览"))
    sheet = Image.new("RGB", (1536, 3 * 510), "#edf0eb")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(renderer.font_path), 24)
    for index, (theme, label) in enumerate(themes):
        options = RenderOptions(width=3072, theme=theme)
        image = renderer.assets.image(
            f"background/decorateIcon/decorate_{theme}_1.jpg", (3072, 1872),
        )
        canvas = Canvas(image)
        renderer._decorations(canvas, options, "background")
        renderer._decorations(canvas, options, "foreground")
        canvas.image.convert("RGB").save(
            args.output / f"background-{theme}.jpg", quality=92,
        )
        thumb = canvas.image.convert("RGB").resize((768, 468),
                                                   Image.Resampling.LANCZOS)
        x, y = (index % 2) * 768, (index // 2) * 510
        draw.text((x+15, y+8), label, font=font, fill="#203e2c")
        sheet.paste(thumb, (x, y+40))
        result = renderer.render(
            who, snapshot, now,
            RenderOptions.high(theme=theme, format="PNG"),
        )
        (args.output / f"farm-{theme}-1536.png").write_bytes(result.content)
    sheet.save(args.output / "all-themes.jpg", quality=92)
    print(f"Generated 5 backgrounds, 5 farm previews: {args.output}")


if __name__ == "__main__":
    main()
