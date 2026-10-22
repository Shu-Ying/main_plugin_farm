"""白名单生成AstrBot可安装包，复用已校验的共享模块打包路径。"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from build_zhenxun import build as build_shared, read_version, source_identity
from verify_astrbot import MANIFEST, ROOT_NAME, verify_files, verify_package
from verify_zhenxun import read_package as read_shared


def build(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    version = read_version(root)
    if output.exists():
        raise FileExistsError('Use a new output directory')
    if output.is_relative_to(root) and not output.is_relative_to(root / 'dist'):
        raise ValueError('In-project output must be inside dist')
    with tempfile.TemporaryDirectory() as temporary:
        shared = read_shared(build_shared(root, Path(temporary) / 'shared'))
    files = {name: content for name, content in shared.items()
             if name.startswith('_vendor/') or name in (
                 '_version.py', 'version.txt', 'LICENSE',
             )}
    source = root / 'integrations/astrbot'
    for name in ('main.py', '_conf_schema.json', 'requirements.txt'):
        files[name] = (source / name).read_bytes()
    files['README.md'] = (source / 'README.md').read_bytes()
    files['runtime.py'] = (root / 'integrations/zhenxun/runtime.py').read_bytes()
    files['verify_package.py'] = (root / 'scripts/verify_astrbot.py').read_bytes()
    # JSON是YAML的子集；标准库即可生成AstrBot可读的metadata.yaml。
    files['metadata.yaml'] = (json.dumps({
        'name': ROOT_NAME, 'display_name': '农场',
        'desc': '种植、收获、仓库、交易与农场图片，复用Farm共享核心。',
        'version': version, 'author': 'Shu-Ying',
        'repo': 'https://github.com/Shu-Ying/astrbot_plugin_farm',
    }, ensure_ascii=False, indent=2) + '\n').encode()
    for name, content in files.items():
        if name.endswith('.py'):
            ast.parse(content, filename=name, feature_version=(3, 10))
    manifest = {
        'schema': 1, 'target': 'astrbot', 'plugin': ROOT_NAME,
        'version': version, 'source': source_identity(root),
        'files': {name: hashlib.sha256(content).hexdigest()
                  for name, content in sorted(files.items())},
    }
    files[MANIFEST] = (json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2,
    ) + '\n').encode()
    verify_files(files)
    output.mkdir(parents=True)
    for name, content in sorted(files.items()):
        target = output / 'repository' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    archive_path = output / f'{ROOT_NAME}-{version}.zip'
    with ZipFile(archive_path, 'w', compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            item = ZipInfo(f'{ROOT_NAME}/{name}', (2020, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.compress_type = ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, content)
    verify_package(archive_path)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix('.zip.sha256').write_text(
        f'{digest}  {archive_path.name}\n', encoding='ascii',
    )
    return archive_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1], args.output))


if __name__ == '__main__':
    main()
