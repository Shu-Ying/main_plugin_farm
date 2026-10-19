"""使用正式渲染器离线绘制作物统一公式与虫子预览。"""

import argparse
from dataclasses import replace
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ci_font import choose_font
from farm_core import Catalogue, Identity
from farm_core.domain import Account, Plot, Snapshot
from farm_render import FarmRenderer, RenderOptions
from farm_render.canvas import Canvas


def preview(renderer, output, width, names):
    scale = width / 3072
    native = lambda n: max(1, round(n * scale))
    cell_w, cell_h = 360, 440
    sheet = Image.new("RGB", (cell_w * 6, 95 + len(names) * (cell_h+45)),
                      "#edf0eb")
    draw = ImageDraw.Draw(sheet)
    title_font = ImageFont.truetype(str(renderer.font_path), 28)
    text_font = ImageFont.truetype(str(renderer.font_path), 21)
    draw.text((20, 12), f"正式渲染器 · 统一定位与虫子 / 输出档位 {width}",
              font=title_font, fill="#172b20")
    draw.text((20, 53), "使用包内完整图片；红线为生长图片对齐基线；"
              "虫子使用原版固定坐标。", font=text_font, fill="#344c3f")
    who = Identity("preview", "local", "qq", "formula")
    old_position = renderer.assets.metadata["positions"][0]
    renderer.assets.metadata["positions"][0] = {"x": 63, "y": 220}
    try:
        for row, name in enumerate(names):
            plant = Catalogue.bundled().get(name)
            info = renderer.assets.metadata["plants"][name]
            phases = tuple(dict.fromkeys(map(int, info["phase"].split(","))))
            times = (0,) + phases
            top = 95 + row * (cell_h + 45)
            draw.text((20, top), name, font=text_font, fill="#172b20")
            data = Snapshot(Account("公式预览", 0, 0, 0), (), (
                Plot(1, plant, plant.growth_seconds,
                     pest_count=3, pest_spawned=3),
            ))
            for stage, now in enumerate(times):
                scene = renderer.scene(who, data, now)
                view = scene.plots[0]
                if stage == 0:
                    view = replace(view, pest_count=0, pest_frames=())
                scene = replace(scene, plots=(view,))
                canvas = Canvas.new((native(cell_w), native(cell_h)), "#edf0eb")
                soil = renderer.assets.image(
                    "soil/普通土地.png", (native(234), native(156)),
                )
                canvas.paste(soil, (native(63), native(220)))
                renderer._plants(canvas, scene, RenderOptions(width=width))
                renderer._pests(canvas, scene, RenderOptions(width=width))
                painter = ImageDraw.Draw(canvas.image)
                painter.line((0, native(376), native(360), native(376)),
                             fill="#bd4545", width=1)
                left = stage * cell_w
                draw.text((left+12, top+32), "公共种子" if stage == 0 else
                          f"生长阶段{stage} · 3只虫", font=text_font,
                          fill="#172b20")
                sheet.paste(canvas.image, (
                    left + (cell_w-canvas.image.width)//2, top+65,
                ))
    finally:
        renderer.assets.metadata["positions"][0] = old_position
    path = output / f"crop-formula-{width}.png"
    sheet.save(path)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--plants", nargs="+", default=(
        "草莓", "橙子", "樱桃", "黄瓜", "桂圆",
    ))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    renderer = FarmRenderer(args.font or choose_font())
    for width in (1024, 1536, 3072):
        print(preview(renderer, args.output, width, args.plants))


if __name__ == "__main__":
    main()
