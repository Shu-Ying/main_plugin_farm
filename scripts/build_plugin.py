"""三平台本地打包入口；每次使用独立新目录，不执行发布或安装。"""

import argparse
from datetime import datetime, timezone
import importlib
from pathlib import Path
import uuid


PLATFORMS = ('nonebot', 'zhenxun', 'astrbot')


def build_plugin(platform, output=None, *, root=None):
    if platform not in PLATFORMS:
        raise ValueError('Unsupported platform')
    source = Path(__file__).resolve().parents[1]
    if output is None:
        parent = Path(root) if root else source / 'dist'
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        output = parent / f'{platform}-{timestamp}-{uuid.uuid4().hex[:8]}'
    module = importlib.import_module('build_' + platform)
    return module.build(source, Path(output).resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=PLATFORMS)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    archive = build_plugin(args.platform, args.output)
    print(f'Package: {archive}')
    print(f'Checksum: {archive.with_suffix(".zip.sha256")}')


if __name__ == '__main__':
    main()
