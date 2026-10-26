"""显式从已验证Service发布目录刷新插件初始版本，不联网。"""

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from farm_core import Catalogue
from farm_core.catalogue_release import canonical, parse_manifest
from farm_render.catalogue_bundle import ROOTS, _snapshot


def sync(source, root=ROOT):
    source, root = Path(source), Path(root)
    manifest = parse_manifest((source / 'manifest.json').read_bytes())
    release = source / 'releases' / manifest['release']
    snapshot = _snapshot(release, manifest, Catalogue.bundled())
    destinations = {
        'plants.json': root / 'src/farm_core/data/plants.json',
        **{name: root / 'src/farm_render/data' / name for name in (
            'metadata.json', 'assets.zip', 'land-soils.zip',
        )},
    }
    for name, path in destinations.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(release / name, path)
    data = root / 'src/farm_core/data'
    (data / 'catalogue-manifest.json').write_bytes(canonical(manifest) + b'\n')
    asset = {
        'schema': 1, 'version': manifest['version'],
        'sha256': manifest['files']['assets.zip']['sha256'],
        'size_bytes': manifest['files']['assets.zip']['size_bytes'],
        'catalogue_release': manifest['release'],
        'sources': {
            name.lower(): base + '/releases/' + manifest['release']
            + '/assets.zip' for name, base in ROOTS.items()
        },
    }
    asset['sources']['farm_service'] = (
        'https://farm.example/v1/catalogue/releases/'
        + manifest['release'] + '/assets.zip'
    )
    (root / 'src/farm_render/data/asset-manifest.json').write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    return snapshot.manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True,
                        help='Service catalogue发布目录，不是可编辑source目录')
    args = parser.parse_args()
    print('Bootstrap synced release=' + sync(args.source)['release'])
