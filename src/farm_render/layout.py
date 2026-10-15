"""从一次快照与统一时间构造可缓存场景；不访问存储。"""

import hashlib

from farm_core.domain import Identity, Snapshot, integer

from .models import PlotView, Scene


def scene_from_snapshot(identity, snapshot, now, metadata):
    if not isinstance(identity, Identity) or not isinstance(snapshot, Snapshot):
        raise ValueError("Identity and snapshot are required")
    integer(now)
    slots = [p.slot for p in snapshot.plots]
    if len(set(slots)) != len(slots) or any(
        type(slot) is not int or not 1 <= slot <= 30 for slot in slots
    ):
        raise ValueError("Invalid plot slots")
    views = []
    for plot in sorted(snapshot.plots, key=lambda p: p.slot):
        if plot.plant is None:
            views.append(PlotView(plot.slot, "empty"))
            continue
        if plot.withered:
            views.append(PlotView(
                plot.slot, "withered", "plant/basic/9.png", size=(150, 212),
            ))
            continue
        integer(plot.mature_at)
        name = plot.plant.name
        info = metadata["plants"].get(name)
        if info is None:
            views.append(PlotView(plot.slot, "growing", "missing"))
            continue
        phases = tuple(dict.fromkeys(int(p) for p in info["phase"].split(",")))
        duration = (plot.plant.growth_seconds if plot.harvest_count == 0
                    else plot.plant.regrowth_seconds)
        elapsed = max(0, now - (plot.mature_at - duration))
        ripe = now >= plot.mature_at
        stage = len(phases) if ripe else sum(
            elapsed * phases[-1] >= threshold * duration
            for threshold in phases
        )
        sprite = f"plant/{name}/{stage}.png"
        size = None
        if stage == 0:
            if info["general"]:
                sprite = "plant/basic/0.png"
            size = (max(1, 35 + info["offsetW"]),
                    max(1, 58 + info["offsetH"]))
        views.append(PlotView(
            plot.slot, "ripe" if ripe else "growing", sprite, stage,
            (info["offsetX"], info["offsetY"]), size,
        ))
    return Scene(
        hashlib.sha256(identity.key.encode()).hexdigest(),
        snapshot.account, tuple(views),
    )
