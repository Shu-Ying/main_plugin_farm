"""白名单生成AstrBot可安装包，复用已校验的共享模块打包路径。"""

import argparse
import ast
import hashlib
import json
import runpy
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from build_zhenxun import build as build_shared, read_version, source_identity
from verify_astrbot import MANIFEST, ROOT_NAME, verify_files, verify_package
from verify_zhenxun import read_package as read_shared


def render_readme(root):
    template = (root / 'readme/astrbot.md').read_text(encoding='utf-8')
    marker = '<!-- FARM_COMMANDS -->'
    if template.count(marker) != 1:
        raise ValueError('AstrBot README requires one command marker')
    definitions = runpy.run_path(str(root / 'src/farm_core/commands.py'))
    lines = ['| 分类 | 指令 | 说明 |', '| --- | --- | --- |']
    specs = definitions['command_specs']('astrbot')
    for group, rows in definitions['help_groups'](specs):
        for usage, description in rows:
            values = (group, f'`/{usage}`', description)
            lines.append('| ' + ' | '.join(
                value.replace('|', r'\|').replace('\n', ' ')
                for value in values
            ) + ' |')
    return template.replace(marker, '\n'.join(lines)).encode('utf-8')


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
    for name in ('main.py', 'avatars.py', '_conf_schema.json',
                 'requirements.txt', 'CHANGELOG.md'):
        files[name] = (source / name).read_bytes()
    # AstrBot识别固定文件名logo.png；README单独使用高清原图。
    files['logo.png'] = (root / 'logo-astrbot.png').read_bytes()
    files['logo-readme.png'] = (root / 'logo.png').read_bytes()
    files['images/farm-preview.png'] = shared['images/farm-preview.png']
    files['README.md'] = render_readme(root)
    files['runtime.py'] = (
        root / 'integrations/shared/runtime.py'
    ).read_bytes()
    files['verify_package.py'] = (
        root / 'scripts/verify_astrbot.py'
    ).read_bytes()
    # JSON是YAML的子集；标准库即可生成AstrBot可读的metadata.yaml。
    files['metadata.yaml'] = (json.dumps({
        'name': ROOT_NAME, 'display_name': '农场',
        'short_desc': '开通农场，体验种植、收获、偷菜与土地开垦。',
        'desc': '农场种植小游戏，支持种子商店、分类仓库、作物交易、'
                '除虫、偷菜、土地开垦和动态图片帮助；使用本地存档。',
        'version': version, 'author': 'Shu-Ying',
        'repo': 'https://github.com/Shu-Ying/astrbot_plugin_farm',
        'social_link': 'https://github.com/Shu-Ying',
        'tags': ['农场', '种植', '小游戏'],
        'support_platforms': ['aiocqhttp'],
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
