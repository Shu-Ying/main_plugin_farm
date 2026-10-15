"""可复现复制旧绘图素材；不修改图片、不包含字体或玩家数据。"""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from PIL import Image


def export(root):
    legacy = root / "legacy/zhenxun_plugin_farm"
    source = legacy / "resource"
    paths = list((source / "plant").rglob("*.png"))
    paths += [source / f"soil/{name}.png" for name in (
        "草土地", "普通土地",
    )]
    paths += [source / "background/expansion.png"]
    paths += [source / "background/ripe.png"]
    paths += [source / (
        f"background/decorateIcon/decorate_{theme}_1.jpg"
    ) for theme in ("default", "spring", "summer", "autumn", "winter")]
    layout = json.loads((legacy / "config/soil.json").read_bytes())
    catalogue = json.loads((
        root / "src/farm_core/data/plants.json"
    ).read_bytes())
    metadata = {
        "schema": 1, "canvas": [3072, 1872], "soil_size": layout["size"],
        "positions": [layout["soil"][str(i)] for i in range(1, 31)],
        "plants": {row["name"]: {
            key: row[key] for key in (
                "phase", "general", "offsetX", "offsetY", "offsetW", "offsetH",
            )
        } for row in catalogue["plants"]}, "images": {},
    }
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED) as bundle:
        for path in sorted(paths):
            name = path.relative_to(source).as_posix()
            content = path.read_bytes()
            with Image.open(BytesIO(content)) as image:
                size = image.size
            metadata["images"][name] = {
                "size": size, "sha256": hashlib.sha256(content).hexdigest(),
            }
            bundle.writestr(ZipInfo(name, (2020, 1, 1, 0, 0, 0)), content)
    return output.getvalue(), (
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = zip(("assets.zip", "metadata.json"), export(root))
    destination = root / "src/farm_render/data"
    for name, content in files:
        path = destination / name
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"Render asset differs: {name}")
        else:
            destination.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print("Render assets checked" if args.check else "Render assets exported")


if __name__ == "__main__":
    main()
