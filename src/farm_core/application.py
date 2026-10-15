"""应用用例：一次业务动作对应一次完整存储事务。"""

from dataclasses import asdict, replace
import time

from .catalogue import Catalogue
from .domain import (
    Asset, FarmError, Identity, Plot, boosted, integer, quantity, text,
)
from .ports import Store


class FarmService:
    def __init__(self, store: Store, catalogue: Catalogue, clock=None):
        self.store = store
        self.catalogue = catalogue
        self.clock = clock if clock is not None else lambda: int(time.time())

    @staticmethod
    def _identity(identity):
        if not isinstance(identity, Identity):
            raise FarmError("invalid_identity")

    async def _execute(
        self, identity, operation_id, action, parameters, operation,
    ):
        self._identity(identity)
        text(operation_id)
        now = integer(self.clock())
        return await self.store.transact(
            identity, operation_id, action, parameters, now,
            lambda repository: operation(repository, now),
        )

    @staticmethod
    def _result(repository, **details):
        account = repository.account()
        return {
            **details, "account": asdict(account), "level": account.level,
        }

    async def snapshot(self, identity: Identity):
        self._identity(identity)
        return await self.store.snapshot(identity)

    async def register(
        self, identity: Identity, name: str, operation_id: str,
    ):
        text(name, 64)

        def operation(repository, now):
            created = repository.register(name)
            return self._result(repository, created=created)

        return await self._execute(
            identity, operation_id, "register", {"name": name}, operation,
        )

    async def buy(
        self, identity: Identity, name: str, count: int, operation_id: str,
    ):
        text(name)
        quantity(count)

        def operation(repository, now):
            plant = self.catalogue.get(name)
            if repository.account().level < plant.level:
                raise FarmError("level_required")
            cost = integer(plant.cost * count)
            repository.asset(plant.asset, -cost)
            repository.stock(name, seeds=count)
            return self._result(
                repository, name=name, quantity=count, cost=cost,
                asset=plant.asset.value,
                seeds=repository.item(name).seeds,
            )

        return await self._execute(
            identity, operation_id, "buy",
            {"name": name, "count": count}, operation,
        )

    async def sow(
        self, identity: Identity, name: str, count: int | None,
        operation_id: str,
    ):
        text(name)
        if count is not None:
            quantity(count)

        def operation(repository, now):
            repository.account()
            plant = self.catalogue.get(name)
            available = repository.item(name).seeds
            empty = [p for p in repository.plots() if p.plant is None]
            amount = min(available, len(empty)) if count is None else count
            if amount == 0 or amount > available:
                raise FarmError("insufficient_stock")
            if amount > len(empty):
                raise FarmError("insufficient_empty_plots")
            mature_at = integer(now + plant.growth_seconds)
            repository.stock(name, seeds=-amount)
            for plot in empty[:amount]:
                repository.save_plot(replace(
                    plot, plant=plant, mature_at=mature_at, harvest_count=0,
                ))
            return self._result(
                repository, name=name, quantity=amount,
                slots=[p.slot for p in empty[:amount]],
                seeds=repository.item(name).seeds,
            )

        return await self._execute(
            identity, operation_id, "sow",
            {"name": name, "count": count}, operation,
        )

    async def harvest(self, identity: Identity, operation_id: str):
        def operation(repository, now):
            repository.account()
            harvested = []
            total_experience = 0
            for plot in repository.plots():
                plant = plot.plant
                if (
                    plant is None or plot.withered or plot.mature_at is None
                    or plot.mature_at > now
                ):
                    continue
                amount = boosted(plant.harvest, plot.yield_bonus)
                experience = boosted(
                    plant.experience, plot.experience_bonus,
                )
                repository.stock(plant.name, crops=amount)
                total_experience = integer(total_experience + experience)
                count = plot.harvest_count + 1
                mature_at = (
                    integer(now + plant.regrowth_seconds)
                    if count < plant.crop else None
                )
                repository.save_plot(replace(
                    plot, mature_at=mature_at, harvest_count=count,
                ))
                harvested.append({
                    "slot": plot.slot, "name": plant.name,
                    "quantity": amount, "experience": experience,
                })
            if not harvested:
                raise FarmError("nothing_to_harvest")
            repository.asset(Asset.EXPERIENCE, total_experience)
            return self._result(
                repository, harvested=harvested,
                experience=total_experience,
                quantity=sum(item["quantity"] for item in harvested),
            )

        return await self._execute(
            identity, operation_id, "harvest", {}, operation,
        )

    async def eradicate(self, identity: Identity, operation_id: str):
        def operation(repository, now):
            repository.account()
            withered = [p for p in repository.plots() if p.withered]
            if not withered:
                raise FarmError("nothing_to_eradicate")
            for plot in withered:
                repository.save_plot(replace(
                    plot, plant=None, mature_at=None, harvest_count=0,
                ))
            return self._result(
                repository, slots=[p.slot for p in withered],
            )

        return await self._execute(
            identity, operation_id, "eradicate", {}, operation,
        )

    async def lock(
        self, identity: Identity, name: str, locked: bool,
        operation_id: str,
    ):
        text(name)
        if type(locked) is not bool:
            raise FarmError("invalid_lock")

        def operation(repository, now):
            repository.account()
            self.catalogue.get(name)
            repository.lock(name, locked)
            return self._result(repository, name=name, locked=locked)

        return await self._execute(
            identity, operation_id, "lock",
            {"name": name, "locked": locked}, operation,
        )

    async def sell(
        self, identity: Identity, name: str | None, count: int | None,
        operation_id: str,
    ):
        if name is not None:
            text(name)
        if count is not None:
            quantity(count)
            if name is None:
                raise FarmError("name_required_for_quantity")

        def operation(repository, now):
            repository.account()
            if name is not None:
                item = repository.item(name)
                if item.locked:
                    raise FarmError("plant_locked")
                amount = item.crops if count is None else count
                if amount <= 0 or amount > item.crops:
                    raise FarmError("insufficient_stock")
                items = [(name, amount)]
            else:
                items = [
                    (item.name, item.crops)
                    for item in repository.items()
                    if not item.locked and item.crops > 0
                ]
                if not items:
                    raise FarmError("nothing_to_sell")
            proceeds = 0
            sold = []
            for plant_name, amount in items:
                plant = self.catalogue.get(plant_name)
                proceeds = integer(proceeds + plant.price * amount)
                repository.stock(plant_name, crops=-amount)
                sold.append({"name": plant_name, "quantity": amount})
            repository.asset(Asset.POINT, proceeds)
            return self._result(
                repository, sold=sold, proceeds=proceeds,
                quantity=sum(item["quantity"] for item in sold),
            )

        return await self._execute(
            identity, operation_id, "sell",
            {"name": name, "count": count}, operation,
        )
