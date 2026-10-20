"""离线生成带全景与地块表格的农场详述预览。"""

import argparse
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ci_font import choose_font
from farm_core import Identity
from farm_core.pests import start_growth
from farm_render import FarmRenderer
from farm_render.details import render_details
from render_demo import demonstration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    snapshot, now = demonstration()
    plots = list(snapshot.plots)
    plots[0] = replace(plots[0], pest_count=2, pest_spawned=2)
    plots[2] = replace(plots[2], pest_count=0, pest_spawned=3,
                       maturity_pests=3)
    plots[3] = start_growth(plots[3], now-14400)
    snapshot = replace(snapshot, plots=tuple(plots))
    renderer = FarmRenderer(choose_font())
    who = Identity('demo', 'local', 'qq', 'details')
    for page in (1, 2):
        (args.output / f'farm-details-{page}.png').write_bytes(render_details(
            renderer, who, snapshot, now, page, 'autumn', 'PNG',
        ))
    print(f'Detail previews: {args.output}')


if __name__ == '__main__':
    main()
