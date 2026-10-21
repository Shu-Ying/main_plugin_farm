"""离线校验统一地块映射：成熟胡萝卜与随机五种作物各阶段。"""

import argparse
from dataclasses import replace
from pathlib import Path
import random
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ci_font import choose_font
from farm_core import Catalogue, Identity
from farm_core.domain import Account, Plot, Snapshot
from farm_render import FarmRenderer, RenderOptions
from farm_render.canvas import Canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    renderer = FarmRenderer(choose_font())
    who = Identity('preview', 'local', 'qq', 'crop-mapping')
    catalogue = Catalogue.bundled()
    carrot = catalogue.get('胡萝卜')
    data = Snapshot(Account('成熟胡萝卜 · 统一公式校验', 11, 0, 6), (), tuple(
        Plot(i, carrot, 100, pest_count=3, pest_spawned=3, maturity_pests=3)
        for i in range(1, 4)
    ))
    result = renderer.render(who, data, 200, RenderOptions.high(
        format='JPEG', theme='autumn',
    ))
    (args.output / 'carrot-mature-1536.jpg').write_bytes(result.content)
    clean = replace(data, plots=tuple(
        replace(plot, pest_count=0) for plot in data.plots
    ))
    result = renderer.render(who, clean, 200, RenderOptions.high(
        format='JPEG', theme='autumn',
    ))
    (args.output / 'carrot-mature-clear-1536.jpg').write_bytes(result.content)
    candidates = [p for p in catalogue if p.buyable
                  and p.name in renderer.assets.metadata['plants']
                  and f'plant/{p.name}/4.png' in
                  renderer.assets.metadata['images']]
    chosen = random.Random(20261021).sample(candidates, 5)
    font = ImageFont.truetype(str(renderer.font_path), 24)
    sheet = Image.new('RGB', (1536, 6*270), '#f4efdf')
    draw = ImageDraw.Draw(sheet)
    for row, plant in enumerate([carrot]+chosen):
        phases = list(dict.fromkeys(map(int,
            renderer.assets.metadata['plants'][plant.name]['phase'].split(','),
        )))
        draw.text((20, row*270+10), f'{plant.name}  #{plant.plant_id}',
                  font=font, fill='#513819')
        for stage, now in enumerate([0]+phases):
            snapshot = Snapshot(data.account, (), (
                Plot(1, plant, plant.growth_seconds),
            ))
            scene = renderer.scene(who, snapshot, now)
            canvas = Canvas.new((1024, 624), '#f4efdf')
            pos = renderer.assets.metadata['positions'][0]
            soil = renderer.assets.image('soil/普通土地.png', (78, 52))
            canvas.paste(soil, (round(pos['x']/3), round(pos['y']/3)))
            renderer._plants(canvas, scene, RenderOptions())
            tile = canvas.image.crop((390, 100, 600, 310))
            x, y = stage*250+10, row*270+45
            sheet.paste(tile.convert('RGB'), (x, y))
            draw.text((x+10, y+190), f'阶段 {stage}', font=font,
                      fill='#513819')
    sheet.save(args.output / 'six-crops-stages.jpg', quality=90)
    print('Crop mapping previews generated')


if __name__ == '__main__':
    main()
