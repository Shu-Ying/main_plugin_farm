"""CI只核对插件初始版本自身，不访问远端或相邻Service开发仓库。"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from farm_core.catalogue_release import parse_manifest
from farm_render.catalogue_bundle import _validate


def check(root=ROOT):
    root = Path(root)
    core = root / 'src/farm_core/data'
    render = root / 'src/farm_render/data'
    manifest = parse_manifest((core / 'catalogue-manifest.json').read_bytes())
    content = {'plants.json': (core / 'plants.json').read_bytes(),
               **{name: (render / name).read_bytes() for name in (
                   'metadata.json', 'assets.zip', 'land-soils.zip',
               )}}
    _validate(content, manifest, None, ())
    print('Verified independent catalogue bootstrap ' + manifest['release'])


if __name__ == '__main__':
    check()
