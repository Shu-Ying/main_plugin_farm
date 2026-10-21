"""可复现复制旧绘图素材；不修改图片、不包含字体或玩家数据。"""

import argparse
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from PIL import Image


def fit_grid(source, target):
    if len(source) != 30 or len(target) != 30:
        raise ValueError('Expected all 30 reference land centers')
    design = [[x, y, 1] for x, y in source]
    normal = [[sum(row[i]*row[j] for row in design)
               for j in range(3)] for i in range(3)]

    def solve(values):
        matrix = [row[:] + [value] for row, value in zip(normal, values)]
        for i in range(3):
            pivot = max(range(i, 3), key=lambda k: abs(matrix[k][i]))
            matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
            divisor = matrix[i][i]
            if abs(divisor) < 1e-8:
                raise ValueError('Reference grid is degenerate')
            matrix[i] = [v/divisor for v in matrix[i]]
            for j in range(3):
                if i != j:
                    factor = matrix[j][i]
                    matrix[j] = [v-factor*w for v, w in zip(
                        matrix[j], matrix[i],
                    )]
        return [row[-1] for row in matrix]

    affine = [solve([sum(row[i]*point[k]
                        for row, point in zip(design, target))
                     for i in range(3)]) for k in range(2)]
    errors = [math.hypot(*[
        sum(a*b for a, b in zip(row, point))-value
        for row, value in zip(affine, dest)
    ]) for point, dest in zip(design, target)]
    if max(errors) > 10:
        raise ValueError('Local grid no longer matches reference geometry')
    return [row[:2] for row in affine], {
        'rms': math.sqrt(sum(e*e for e in errors)/len(errors)),
        'maximum': max(errors), 'points': len(errors),
    }


def apply_positions(root, metadata):
    document = json.loads((
        root / "src/farm_render/data/crop_positions.json"
    ).read_bytes())
    if document.get("schema") != 4:
        raise ValueError("Unsupported crop position schema")
    if document.get("mode") != "visible_contact_center":
        raise ValueError("Unsupported crop placement mode")
    w, h = metadata['soil_size']
    target = [[p['x']+w/2, p['y']+h/2] for p in metadata['positions']]
    transform, errors = fit_grid(document['source_land_centers'], target)
    document['scene_transform'] = transform
    document['grid_fit'] = errors
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
    entries['webgl/shop-board.png'] = webgl_source / 'webgl/shop-board.png'
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
    # 与已发布的地块编号一致：前两行交错排列，初始六块组成 2×3。
    # 标定仍使用上面的旧资源顺序；这里只调整最终运行时的编号位置。
    positions = metadata["positions"]
    metadata["positions"] = [positions[index] for index in (
        0, 6, 1, 7, 2, 8, 3, 9, 4, 10, 5, 11,
    )] + positions[12:]
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
