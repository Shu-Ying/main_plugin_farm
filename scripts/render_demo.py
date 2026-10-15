"""离线样例与本机测量，不访问真实玩家库或平台。"""

import argparse
from dataclasses import replace
import json
import logging
from pathlib import Path
import platform
import sys
from time import perf_counter

from PIL import __version__ as pillow_version, features

from farm_core import Catalogue, Identity
from farm_core.domain import Account, Plot, Snapshot
from farm_render import FarmRenderer, RenderOptions


def demonstration():
    catalogue = Catalogue.bundled()
    plants = [p for p in catalogue if not p.name.startswith((
        "一星", "二星", "三星", "四星", "五星",
    ))]
    now = 36000
    plots = []
    for index in range(1, 19):
        plant = plants[(index - 1) % min(len(plants), 20)]
        if index % 6 == 0:
            plots.append(Plot(index))
            continue
        mature_at = now - 10 if index % 3 == 0 else (
            now + plant.growth_seconds // 3
        )
        plot = Plot(index, plant, mature_at)
        if index == 11:
            plot = replace(plot, harvest_count=plant.crop)
        plots.append(plot)
    return Snapshot(
        Account("舒影的四季农场", 12580, 36, 3420), (), tuple(plots),
    ), now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("runtime/render-demo"),
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=args.output / "render.log", encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    who = Identity("demo", "local", "local", "synthetic-farmer")
    snapshot, now = demonstration()
    rows = []
    for width, quality in ((1024, 75), (1536, 85)):
        for codec in ("WEBP", "JPEG", "PNG"):
            if codec == "WEBP" and not features.check("webp"):
                continue
            renderer = FarmRenderer(args.font)
            options = RenderOptions(
                width=width, quality=quality, format=codec, theme="spring",
            )
            started = perf_counter()
            result = renderer.render(who, snapshot, now, options)
            cold_ms = (perf_counter() - started) * 1000
            started = perf_counter()
            warm = renderer.render(who, snapshot, now, options)
            warm_ms = (perf_counter() - started) * 1000
            suffix = {"WEBP":"webp", "JPEG":"jpg", "PNG":"png"}[codec]
            output = args.output / f"farm-{width}.{suffix}"
            output.write_bytes(result.content)
            rows.append({
                "width": width, "height": result.height, "codec": codec,
                "quality": quality, "method": options.method,
                "bytes": len(result.content), "cold_ms": round(cold_ms, 3),
                "compose_ms": round(result.compose_ms, 3),
                "encode_ms": round(result.encode_ms, 3),
                "warm_ms": round(warm_ms, 3), "warm_cache_hit": warm.cache_hit,
                "asset_cache_bytes": renderer.assets.cache.used_bytes,
                "result_cache_bytes": renderer.results.used_bytes,
            })
    metadata = renderer.assets.metadata
    missing = sum(
        f"plant/{name}/{stage}.png" not in metadata["images"]
        for name, info in metadata["plants"].items()
        for stage in range(1, len(dict.fromkeys(info["phase"].split(",")))+1)
    )
    report = {
        "python": platform.python_version(), "os": platform.system(),
        "pillow": pillow_version, "synthetic_data": True,
        "scope": "本机单次样例；非旧版对照，未测上传或低配服务器",
        "asset_count": len(metadata["images"]),
        "legacy_missing_stage_references": missing, "measurements": rows,
    }
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (args.report or args.output / "benchmark.json").write_text(
        content, encoding="utf-8",
    )
    print(content)


if __name__ == "__main__":
    main()
