"""从当前命令注册表离线生成帮助菜单图片，不访问玩家数据库。"""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ci_font import choose_font
from farm_core.commands import command_specs
from farm_render import FarmRenderer
from farm_render.help import render_help


PLATFORMS = ('zhenxun', 'nonebot', 'astrbot')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--platform', choices=(*PLATFORMS, 'all'), default='all',
        help='目标平台；默认一次生成三个平台的菜单。',
    )
    parser.add_argument(
        '--output', type=Path, default=ROOT / 'images',
        help='图片输出目录；默认主仓库 images。',
    )
    parser.add_argument('--font', type=Path, help='中文字体文件路径。')
    parser.add_argument(
        '--format', choices=('PNG', 'JPEG', 'WEBP'), default='PNG',
        type=str.upper, help='默认PNG无损图片。',
    )
    parser.add_argument('--quality', type=int, default=75,
                        help='JPEG/WebP质量，1～95；PNG不受影响。')
    args = parser.parse_args(argv)
    if not 1 <= args.quality <= 95:
        parser.error('--quality 必须为1～95的整数')
    try:
        renderer = FarmRenderer(str(args.font) if args.font else choose_font())
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(f'无法加载字体或素材，请用 --font 指定中文字体：{error}')
    platforms = PLATFORMS if args.platform == 'all' else (args.platform,)
    extension = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}[args.format]
    args.output.mkdir(parents=True, exist_ok=True)
    for platform in platforms:
        picture = render_help(
            renderer, command_specs(platform), platform,
            image_format=args.format, quality=args.quality,
        )
        target = args.output / f'help-{platform}.{extension}'
        target.write_bytes(picture)
        print(f'{target.resolve()} ({len(picture)} bytes)')


if __name__ == '__main__':
    main()
