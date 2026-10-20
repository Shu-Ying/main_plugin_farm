"""用实际目录和离线示例账户生成种子商店预览。"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ci_font import choose_font
from farm_core import Catalogue
from farm_core.domain import Account
from farm_render import FarmRenderer
from farm_render.shop import render_shop, shop_page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    renderer = FarmRenderer(choose_font())
    catalogue = Catalogue.bundled()
    account = Account('演示农场', 12580, 36, 3420)
    _, pages = shop_page(catalogue, 1)
    for page in dict.fromkeys((1, min(2, pages), pages)):
        plants, _ = shop_page(catalogue, page)
        (args.output / f'shop-page-{page}.png').write_bytes(render_shop(
            renderer, plants, account, page, pages,
        ))
    plants, _ = shop_page(catalogue, 1)
    (args.output / 'shop-unregistered.png').write_bytes(render_shop(
        renderer, plants, None, 1, pages,
    ))
    print(f'Shop previews: {args.output}')


if __name__ == '__main__':
    main()
