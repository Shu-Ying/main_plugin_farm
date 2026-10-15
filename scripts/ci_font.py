"""为CI选择现有字体；部署仍须显式配置中文字体。"""

import os
from pathlib import Path


def choose_font():
    configured = os.environ.get("FARM_TEST_FONT")
    candidates = ([configured] if configured else []) + [
        "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for name in candidates:
        if Path(name).is_file():
            return name
    raise RuntimeError("Set FARM_TEST_FONT to an existing font")


if __name__ == "__main__":
    path = choose_font()
    environment_file = os.environ.get("GITHUB_ENV")
    if environment_file:
        with open(environment_file, "a", encoding="utf-8") as output:
            output.write(f"FARM_TEST_FONT={path}\n")
    print(path)
