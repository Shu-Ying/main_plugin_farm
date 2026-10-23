"""离线核对发布清单、开发素材及布局；不访问远端。"""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


def check(root):
    data = Path(root) / 'src/farm_render/data'
    manifest = json.loads((data / 'asset-manifest.json').read_bytes())
    metadata = json.loads((data / 'metadata.json').read_bytes())
    bundle = data / 'assets.zip'
    if (manifest['schema'] != 1
            or bundle.stat().st_size != manifest['size_bytes']
            or hashlib.sha256(bundle.read_bytes()).hexdigest()
            != manifest['sha256']):
        raise ValueError('Asset manifest and development ZIP differ')
    with ZipFile(bundle) as archive:
        if set(archive.namelist()) != set(metadata['images']):
            raise ValueError('Asset manifest and layout differ')
    for source, prefix in (
        ('github', 'https://raw.githubusercontent.com/Shu-Ying/'
                   'farm_service/main/assets/assets.zip'),
        ('gitea', 'https://gitea.diuse.work/Diuse/farm_service/'
                  'raw/branch/main/assets/assets.zip'),
    ):
        if manifest['sources'][source] != prefix:
            raise ValueError('Asset source must use service repository')
    print('Verified external asset manifest and development ZIP')


if __name__ == '__main__':
    check(Path(__file__).resolve().parents[1])
