"""预览与CI复用 service 字体缓存，不将大字体打入插件。"""

import os
from pathlib import Path
import sys
import tempfile


def choose_font():
    configured = os.environ.get("FARM_TEST_FONT")
    if configured:
        if not Path(configured).is_file():
            raise RuntimeError("FARM_TEST_FONT does not exist")
        return configured
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from farm_render.font_bundle import FILES, _valid, ensure_font
    local = root.parent / "farm_service/fonts/Xiaolai-Regular.ttf"
    if _valid(local, *FILES[local.name]):
        return str(local)
    cache = Path(tempfile.gettempdir()) / "farm-preview-resources"
    return str(ensure_font(cache))


if __name__ == "__main__":
    path = choose_font()
    environment_file = os.environ.get("GITHUB_ENV")
    if environment_file:
        with open(environment_file, "a", encoding="utf-8") as output:
            output.write(f"FARM_TEST_FONT={path}\n")
    print(path)
