"""只读、离线作物目录加载。"""

from importlib import resources
import json
from types import MappingProxyType

from .domain import FarmError, Plant, text


class Catalogue:
    def __init__(self, plants):
        items = tuple(plants)
        if not items or any(not isinstance(p, Plant) for p in items):
            raise FarmError("invalid_catalogue")
        names = {plant.name: plant for plant in items}
        if len(names) != len(items):
            raise FarmError("duplicate_plant")
        if len({p.plant_id for p in items}) != len(items):
            raise FarmError("duplicate_plant")
        self._plants = MappingProxyType(names)

    def get(self, name: str) -> Plant:
        text(name)
        try:
            return self._plants[name]
        except KeyError as exc:
            raise FarmError("unknown_plant") from exc

    def __iter__(self):
        return iter(self._plants.values())

    def __len__(self):
        return len(self._plants)

    @classmethod
    def loads(cls, content: str | bytes) -> "Catalogue":
        try:
            data = json.loads(content)
            if type(data["schema"]) is not int or data["schema"] != 1:
                raise FarmError("invalid_catalogue")
            if not isinstance(data["plants"], list):
                raise FarmError("invalid_catalogue")
            return cls(Plant.from_legacy(row) for row in data["plants"])
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise FarmError("invalid_catalogue") from exc

    @classmethod
    def bundled(cls) -> "Catalogue":
        content = resources.files(__package__).joinpath(
            "data", "plants.json"
        ).read_bytes()
        return cls.loads(content)
