"""可复现复制旧绘图素材；不修改图片、不包含字体或玩家数据。"""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from PIL import Image


def apply_positions(root, metadata):
    document = json.loads((
        root / "src/farm_render/data/crop_positions.json"
    ).read_bytes())
    if document.get("schema") != 2:
        raise ValueError("Unsupported crop position schema")
    if document.get("mode") != "full_canvas_bottom_center":
        raise ValueError("Unsupported crop placement mode")
    metadata["placement"] = document


def apply_decorations(root, metadata):
    document = json.loads((
        root / "src/farm_render/data/background_layout.json"
    ).read_bytes())
    if (document["schema"] != 1 or document["canvas"] != metadata["canvas"]
            or document["anchor"] != "full_canvas_bottom_center"):
        raise ValueError("Unsupported background layout")
    prefix = "background/decorateIcon/"
    layouts = {}
    for theme in ("default", "spring", "summer", "autumn", "winter", "bee"):
        entries = []
        for definition in document["buildings"]:
            default = prefix + definition["sprite"]
            sprite = default.replace("decorate_default_", f"decorate_{theme}_")
            source_theme = theme
            if sprite not in metadata["images"]:
                sprite, source_theme = default, "default"
            image = metadata["images"][sprite]
            x, y, w, h = definition["rect"]
            if w <= 0 or h <= 0:
                raise ValueError("Invalid background rectangle")
            height = w * image["size"][1] / image["size"][0]
            if definition["layer"] not in ("background", "foreground"):
                raise ValueError("Invalid decoration layer")
            entries.append({
                "name": definition["name"], "sprite": sprite,
                "position": [x, y + h - height], "size": [w, height],
                "layer": definition["layer"], "source_theme": source_theme,
                "fallback": source_theme != theme,
                "basis": definition["basis"],
            })
        layouts[theme] = entries
    metadata["decorations"] = layouts


def export(root):
    legacy = root / "legacy/zhenxun_plugin_farm"
    source = legacy / "resource"
    paths = list((source / "plant").rglob("*.png"))
    paths += [source / f"soil/{name}.png" for name in (
        "草土地", "普通土地",
    )]
    paths += [source / "background/expansion.png"]
    paths += [source / "background/ripe.png"]
    paths += [source / "background/userInfo.png"]
    paths += [source / "background/frame/frame.png"]
    paths += [source / (
        f"background/decorateIcon/decorate_{theme}_1.jpg"
    ) for theme in ("default", "spring", "summer", "autumn", "winter", "bee")]
    paths += list((source / "background/decorateIcon").glob("decorate_*.png"))
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
    webgl_source = root / "src/farm_render/source_assets"
    manifest = json.loads((webgl_source / "manifest.json").read_bytes())
    metadata["pest"] = manifest["pest"]
    metadata["panel"] = manifest["panel"]
    entries = {path.relative_to(source).as_posix(): path for path in paths}
    entries.update({name: webgl_source / name for name in manifest["images"]})
    with ZipFile(output, "w", compression=ZIP_STORED) as bundle:
        for name, path in sorted(entries.items()):
            content = path.read_bytes()
            with Image.open(BytesIO(content)) as image:
                size = image.size
            metadata["images"][name] = {
                "size": size, "sha256": hashlib.sha256(content).hexdigest(),
            }
            if name in manifest["images"]:
                expected = manifest["images"][name]
                if (list(size) != expected["size"] or
                        metadata["images"][name]["sha256"] != expected["sha256"]):
                    raise ValueError("Captured WebGL sprite changed")
            item = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            bundle.writestr(item, content)
    apply_positions(root, metadata)
    apply_decorations(root, metadata)
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
