"""构建期间调用独立帮助菜单脚本；不改变开发源或源码身份。"""

from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile


def build_help_image(root, platform, prepared=None):
    if platform not in ('zhenxun', 'nonebot', 'astrbot'):
        raise ValueError('Unknown help platform')
    if prepared is None:
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run([
                sys.executable, str(Path(root) / 'scripts/preview_help.py'),
                '--platform', platform, '--output', temporary,
            ], check=True, stdout=subprocess.PIPE, timeout=60)
            content = (Path(temporary) / f'help-{platform}.png').read_bytes()
    else:
        path = Path(prepared)
        if path.name != f'help-{platform}.png':
            raise ValueError('Help image belongs to a different platform')
        content = path.read_bytes()
    from PIL import Image
    with Image.open(BytesIO(content)) as image:
        if image.format != 'PNG' or image.width != 1200:
            raise ValueError('Expected generated PNG help menu at width 1200')
        image.verify()
    return content
