"""从已下载的公开 Unity 场景包提取图片；不执行游戏脚本。"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def panel_layout(environment):
    prefab = next(
        entry.asset for obj in environment.objects
        if obj.type.name == 'AssetBundle'
        for path, entry in obj.read().m_Container
        if path.endswith('/webglpersioninfo.prefab')
    )
    nodes = {}

    def visit(pointer, parent=None):
        game_object = pointer.read()
        components = [c.component for c in game_object.m_Component]
        transform = next(c.read() for c in components
                         if c.type.name == 'RectTransform')
        rect = [0, 0, 100, 100]
        if parent is not None:
            lo, hi = transform.m_AnchorMin, transform.m_AnchorMax
            pivot, pos = transform.m_Pivot, transform.m_AnchoredPosition
            w = parent[2] * (hi.x - lo.x) + transform.m_SizeDelta.x
            h = parent[3] * (hi.y - lo.y) + transform.m_SizeDelta.y
            rect = [
                parent[0] + parent[2] * (lo.x + (hi.x-lo.x)*pivot.x)
                + pos.x - w*pivot.x,
                parent[1] + parent[3] * (1-lo.y-(hi.y-lo.y)*pivot.y)
                - pos.y - h*(1-pivot.y), w, h,
            ]
        for component in components:
            if component.type.name != 'MonoBehaviour':
                continue
            data = component.read_typetree()
            if 'm_Sprite' in data or 'm_Text' in data:
                nodes[game_object.m_Name] = {
                    'rect': rect, 'data': data,
                }
        for child in transform.m_Children:
            visit(child.read().m_GameObject, rect)

    visit(prefab)
    sprites = []
    sprite_ids = {}
    for name in ('PersionInfoBG', 'HeadFrame', 'ExpBar', 'ExpProgress',
                 'GoldIcon', 'CouponIcon'):
        node = nodes[name]
        sprite_id = node['data']['m_Sprite']['m_PathID']
        path = f'webgl/panel/{name}.png'
        sprite_ids[sprite_id] = path
        sprites.append({'name': name, 'sprite': path, 'rect': node['rect']})
    fields = []
    for node_name, field in (('NameT', 'name'), ('text', 'experience'),
                             ('LevelT', 'level'), ('GoldT', 'point'),
                             ('CouponT', 'vip_point')):
        node = nodes[node_name]
        color = node['data']['m_Color']
        fields.append({
            'field': field, 'rect': node['rect'],
            'alignment': node['data']['m_FontData']['m_Alignment'],
            'color': [round(color[c]*255) for c in ('r', 'g', 'b')],
        })
    return {
        'reference_canvas': [1920, 1080],
        'source_prefab': 'mainscene#WebGLPersionInfo',
        'anchor': 'top_left', 'sprites': sprites,
        'avatar': nodes['HeadIcon']['rect'], 'fields': fields,
    }, sprite_ids


def extract(bundle, destination):
    import UnityPy
    from PIL import Image

    environment = UnityPy.load(str(bundle))
    panel, panel_ids = panel_layout(environment)
    destination.mkdir(parents=True, exist_ok=True)
    images = {}
    for obj in environment.objects:
        if obj.type.name != "Sprite":
            continue
        sprite = obj.read()
        name = sprite.m_Name
        if obj.path_id in panel_ids:
            path = panel_ids[obj.path_id]
        elif re.fullmatch(r"pest\d+", name):
            path = f"pest/{name}.png"
        elif name in ("Icon_PlantSeed", "Icon_PlantWither"):
            path = "webgl/" + (
                "seed.png" if name == "Icon_PlantSeed" else "wither.png"
            )
        else:
            continue
        image = sprite.image
        full_size = (round(sprite.m_Rect.width), round(sprite.m_Rect.height))
        if obj.path_id in panel_ids and image.size != full_size:
            offset = sprite.m_RD.textureRectOffset
            position = (round(offset.x),
                        full_size[1] - round(offset.y) - image.height)
            if (min(position) < 0 or position[0]+image.width > full_size[0]
                    or position[1]+image.height > full_size[1]):
                raise ValueError('Panel sprite exceeds its original canvas')
            full = Image.new('RGBA', full_size)
            full.paste(image, position)
            image = full
        if image.size != (round(sprite.m_Rect.width),
                          round(sprite.m_Rect.height)):
            raise ValueError(
                f'Sprite extraction lost its full canvas: {name} '
                f'{image.size} vs {sprite.m_Rect}'
            )
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target)
        images[path] = {
            "size": list(image.size),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    if len(images) != 46:
        raise ValueError("Expected 38 pests, two crop and six panel sprites")
    manifest = {
        "schema": 1,
        "source_url": (
            "https://game.qqnc.qq.com/happyfarm/unity/Assets/AssetBundles/"
            "WebGL/mainscene_053483f584f07436ac0569e2f4f7ed01"
        ),
        "source_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "extractor": "UnityPy 1.25.4 Sprite.image; full sprite rect checked",
        "images": images,
        "panel": panel,
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
