"""从已下载的公开 Unity 场景包提取图片；不执行游戏脚本。"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def extract(bundle, destination):
    import UnityPy

    environment = UnityPy.load(str(bundle))
    destination.mkdir(parents=True, exist_ok=True)
    images = {}
    for obj in environment.objects:
        if obj.type.name != "Sprite":
            continue
        sprite = obj.read()
        name = sprite.m_Name
        if re.fullmatch(r"pest\d+", name):
            path = f"pest/{name}.png"
        elif name in ("Icon_PlantSeed", "Icon_PlantWither"):
            path = "webgl/" + (
                "seed.png" if name == "Icon_PlantSeed" else "wither.png"
            )
        else:
            continue
        image = sprite.image
        if image.size != (round(sprite.m_Rect.width),
                          round(sprite.m_Rect.height)):
            raise ValueError("Sprite extraction lost its full canvas")
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target)
        images[path] = {
            "size": list(image.size),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    if len(images) != 40:
        raise ValueError("Expected 38 pest frames and two common crop sprites")
    manifest = {
        "schema": 1,
        "source_url": (
            "https://game.qqnc.qq.com/happyfarm/unity/Assets/AssetBundles/"
            "WebGL/mainscene_053483f584f07436ac0569e2f4f7ed01"
        ),
        "source_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "extractor": "UnityPy 1.25.4 Sprite.image; full sprite rect checked",
        "images": images,
        "pest": {
            "frames": [f"pest/pest{i}.png" for i in range(1, 76, 2)],
            "sample_rate": 24,
            "loop": True,
            "display_size": [22, 30],
            "pivot": [0.5, 0.5],
            "positions": [[-26, 13], [-5, 42], [24, 24]],
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Extracted {len(images)} images")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--dependencies", type=Path)
    parser.add_argument("--output", type=Path, default=(
        Path(__file__).resolve().parents[1]
        / "src/farm_render/source_assets"
    ))
    args = parser.parse_args()
    if args.dependencies:
        sys.path.insert(0, str(args.dependencies))
    extract(args.bundle, args.output)


if __name__ == "__main__":
    main()
