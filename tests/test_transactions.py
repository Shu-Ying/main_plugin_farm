import asyncio
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from farm_core import Asset, Catalogue, FarmError, FarmService, Identity
from farm_core import SQLiteStore
from farm_core.domain import MAX_QUANTITY, Plant, SchemaError, StorageError
from farm_core.presentation import receipt_text, snapshot_text
from farm_core.repository import SQLiteRepository


def catalogue():
    return Catalogue([
        Plant(1, "萝卜", 0, 10, False, 0, 20, 2, 10, 2, 1, 1),
        Plant(2, "番茄", 0, 5, False, 0, 30, 3, 7, 3, 2, 2),
        Plant(3, "点券菜", 0, 999, True, 4, 8, 2, 3, 2, 1, 1),
        Plant(4, "高级菜", 2, 10, False, 0, 20, 2, 10, 2, 1, 1),
    ])


class TransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farm-core-test-")
        self.path = Path(self.temporary.name) / "farm.sqlite3"
        self.store = SQLiteStore(self.path)
        await self.store.initialize()
        self.now = 1000
        self.service = FarmService(
            self.store, catalogue(), lambda: self.now,
        )
        self.identity = Identity("deployment", "realm", "qq", "user")
        await self.service.register(self.identity, "测试农场", "register")

    async def asyncTearDown(self):
        await self.store.close()
        temporary_path = Path(self.temporary.name).resolve()
        self.assertTrue(temporary_path.is_relative_to(
            Path(tempfile.gettempdir()).resolve()
        ))
        self.temporary.cleanup()

    async def seed(self, action, callback):
        return await self.store.transact(
            self.identity, action, "test-fixture", {}, self.now, callback,
        )

    async def mature_radish(self, count=1):
        await self.service.buy(self.identity, "萝卜", count, "buy")
        await self.service.sow(self.identity, "萝卜", count, "sow")
        self.now += 2
        return await self.service.harvest(self.identity, "harvest")

    async def test_registration_is_immediately_visible_and_not_repeated(self):
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.account.point, 500)
        self.assertEqual(snapshot.account.vip_point, 0)
        self.assertEqual(snapshot.account.experience, 0)
        self.assertEqual(len(snapshot.plots), 3)
        self.assertTrue(all(p.plant is None for p in snapshot.plots))
        repeated = await self.service.register(
            self.identity, "另一个名称", "register-again",
        )
        self.assertFalse(repeated.data["created"])
        self.assertEqual(repeated.data["account"]["point"], 500)
        self.assertEqual(len(await self.store.ledger(self.identity)), 1)

    async def test_scopes_are_independent(self):
        other = replace(self.identity, realm="different")
        with self.assertRaisesRegex(FarmError, "not_registered"):
            await self.service.snapshot(other)
        await self.service.register(other, "另一农场", "register")
        await self.service.buy(self.identity, "萝卜", 1, "buy")
        self.assertEqual(
            (await self.service.snapshot(other)).account.point, 500,
        )

    async def test_full_purchase_to_sale_round_trip(self):
        harvest = await self.mature_radish()
        self.assertEqual(harvest.data["experience"], 20)
        sale = await self.service.sell(self.identity, None, None, "sell")
        self.assertEqual(sale.data["proceeds"], 20)
        self.assertEqual(sale.data["account"]["point"], 510)
        self.assertEqual(sale.data["account"]["experience"], 20)
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.inventory[0].seeds, 0)
        self.assertEqual(snapshot.inventory[0].crops, 0)
        self.assertTrue(snapshot.plots[0].withered)
        self.assertIn("本次收入：20", receipt_text(sale))
        self.assertIn("等级：", snapshot_text(snapshot))
        await self.service.eradicate(self.identity, "eradicate")
        self.assertTrue(all(
            p.plant is None
            for p in (await self.service.snapshot(self.identity)).plots
        ))

    async def test_existing_balance_and_experience_are_not_added_twice(self):
        await self.seed("existing-exp", lambda repo: (
            repo.asset(Asset.EXPERIENCE, 100) or {}
        ))
        await self.mature_radish()
        self.assertEqual(
            (await self.service.snapshot(self.identity)).account.experience,
            120,
        )
        await self.seed("balance-100", lambda repo: (
            repo.asset(Asset.POINT, -390) or {}
        ))
        sale = await self.service.sell(self.identity, "萝卜", None, "sell")
        self.assertEqual(sale.data["account"]["point"], 120)

    async def test_invalid_inputs_do_not_change_assets(self):
        before = await self.service.snapshot(self.identity)
        for count in (0, -1, True, False, 1.5, MAX_QUANTITY + 1, 10**30):
            with self.subTest(count=count):
                with self.assertRaises(FarmError):
                    await self.service.buy(
                        self.identity, "萝卜", count, "invalid",
                    )
                with self.assertRaises(FarmError):
                    await self.service.sow(
                        self.identity, "萝卜", count, "invalid",
                    )
                with self.assertRaises(FarmError):
                    await self.service.sell(
                        self.identity, "萝卜", count, "invalid",
                    )
        self.assertEqual(await self.service.snapshot(self.identity), before)

    async def test_unaffordable_unknown_and_high_level_purchase_fail(self):
        for name, count, code in (
            ("萝卜", 51, "insufficient_funds"),
            ("高级菜", 1, "level_required"),
            ("不存在", 1, "unknown_plant"),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(FarmError, code):
                    await self.service.buy(
                        self.identity, name, count, "denied",
                    )
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.account.point, 500)
        self.assertEqual(snapshot.inventory, ())

    async def test_vip_purchase_only_uses_vip_currency(self):
        with self.assertRaisesRegex(FarmError, "insufficient_funds"):
            await self.service.buy(self.identity, "点券菜", 1, "vip")
        await self.seed("vip-fixture", lambda repo: (
            repo.asset(Asset.VIP_POINT, 10) or {}
        ))
        result = await self.service.buy(self.identity, "点券菜", 1, "vip")
        self.assertEqual(result.data["account"]["point"], 500)
        self.assertEqual(result.data["account"]["vip_point"], 6)

    async def test_sow_all_and_explicit_overflow(self):
        await self.service.buy(self.identity, "萝卜", 5, "buy")
        before = await self.service.snapshot(self.identity)
        with self.assertRaisesRegex(FarmError, "insufficient_empty_plots"):
            await self.service.sow(self.identity, "萝卜", 4, "too-many")
        self.assertEqual(await self.service.snapshot(self.identity), before)
        result = await self.service.sow(self.identity, "萝卜", None, "all")
        self.assertEqual(result.data["quantity"], 3)
        self.assertEqual(result.data["seeds"], 2)

    async def test_maturity_boundary_and_multi_crop_lifecycle(self):
        await self.service.buy(self.identity, "番茄", 1, "buy")
        await self.service.sow(self.identity, "番茄", 1, "sow")
        self.now += 2
        with self.assertRaisesRegex(FarmError, "nothing_to_harvest"):
            await self.service.harvest(self.identity, "early")
        with self.assertRaisesRegex(FarmError, "nothing_to_eradicate"):
            await self.service.eradicate(self.identity, "early-clear")
        self.now += 1
        await self.service.harvest(self.identity, "first")
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.plots[0].mature_at, self.now + 2)
        self.assertFalse(snapshot.plots[0].withered)
        self.now += 2
        await self.service.harvest(self.identity, "second")
        snapshot = await self.service.snapshot(self.identity)
        self.assertTrue(snapshot.plots[0].withered)
        self.assertEqual(snapshot.inventory[0].crops, 6)
        self.assertEqual(snapshot.account.experience, 60)
        with self.assertRaisesRegex(FarmError, "nothing_to_harvest"):
            await self.service.harvest(self.identity, "third")

    async def test_planted_rules_are_frozen(self):
        await self.service.buy(self.identity, "萝卜", 1, "buy")
        await self.service.sow(self.identity, "萝卜", 1, "sow")
        changed = replace(
            self.service.catalogue.get("萝卜"), harvest=999, experience=999,
            growth_seconds=100, crop=5,
        )
        self.service.catalogue = Catalogue([changed])
        self.now += 2
        result = await self.service.harvest(self.identity, "harvest")
        self.assertEqual(result.data["quantity"], 2)
        self.assertEqual(result.data["experience"], 20)
        self.assertTrue(
            (await self.service.snapshot(self.identity)).plots[0].withered
        )

    async def test_per_plot_bonuses_are_independent_of_iteration_order(self):
        await self.service.buy(self.identity, "萝卜", 2, "buy")
        await self.service.sow(self.identity, "萝卜", 2, "sow")

        def bonuses(repo):
            plots = repo.plots()
            repo.save_plot(replace(plots[0], experience_bonus=100))
            repo.save_plot(replace(plots[1], experience_bonus=50))
            return {}

        await self.seed("bonuses", bonuses)
        self.now += 2
        original = SQLiteRepository.plots
        with patch.object(
            SQLiteRepository, "plots",
            lambda repo: tuple(reversed(original(repo))),
        ):
            result = await self.service.harvest(self.identity, "harvest")
        self.assertEqual(result.data["experience"], 70)

    async def test_locks_protect_both_sale_paths_and_survive_restart(self):
        await self.mature_radish()
        await self.service.lock(self.identity, "萝卜", True, "lock")
        for name, code in (
            ("萝卜", "plant_locked"), (None, "nothing_to_sell"),
        ):
            with self.assertRaisesRegex(FarmError, code):
                await self.service.sell(self.identity, name, None, "locked")
        await self.store.close()
        await self.store.initialize()
        self.assertTrue(
            (await self.service.snapshot(self.identity)).inventory[0].locked
        )
        await self.service.lock(self.identity, "萝卜", False, "unlock")
        result = await self.service.sell(self.identity, None, None, "sale")
        self.assertEqual(result.data["proceeds"], 20)

    async def test_failed_purchase_rolls_back_money_stock_and_ledger(self):
        before = await self.service.snapshot(self.identity)
        ledger = await self.store.ledger(self.identity)
        with patch.object(
            SQLiteRepository, "stock",
            side_effect=sqlite3.OperationalError("injected"),
        ):
            with self.assertRaises(StorageError):
                await self.service.buy(self.identity, "萝卜", 1, "buy")
        self.assertEqual(await self.service.snapshot(self.identity), before)
        self.assertEqual(await self.store.ledger(self.identity), ledger)
        await self.service.buy(self.identity, "萝卜", 1, "buy")
        self.assertEqual(
            (await self.service.snapshot(self.identity)).account.point, 490,
        )

    async def test_failed_harvest_rolls_back_crop_and_plot(self):
        await self.service.buy(self.identity, "萝卜", 1, "buy")
        await self.service.sow(self.identity, "萝卜", 1, "sow")
        self.now += 2
        before = await self.service.snapshot(self.identity)
        original = SQLiteRepository.asset

        def fail_exp(repo, asset, delta):
            if asset == Asset.EXPERIENCE:
                raise sqlite3.OperationalError("injected")
            original(repo, asset, delta)

        with patch.object(SQLiteRepository, "asset", fail_exp):
            with self.assertRaises(StorageError):
                await self.service.harvest(self.identity, "harvest")
        self.assertEqual(await self.service.snapshot(self.identity), before)
        result = await self.service.harvest(self.identity, "harvest")
        self.assertEqual(result.data["quantity"], 2)

    async def test_failed_sale_rolls_back_inventory(self):
        await self.mature_radish()
        before = await self.service.snapshot(self.identity)
        with patch.object(
            SQLiteRepository, "asset",
            side_effect=sqlite3.OperationalError("injected"),
        ):
            with self.assertRaises(StorageError):
                await self.service.sell(self.identity, None, None, "sale")
        self.assertEqual(await self.service.snapshot(self.identity), before)

    async def test_replay_and_parameter_conflict(self):
        first = await self.service.buy(self.identity, "萝卜", 1, "buy")
        self.now += 100
        second = await self.service.buy(self.identity, "萝卜", 1, "buy")
        self.assertEqual(first, second)
        with self.assertRaisesRegex(FarmError, "operation_conflict"):
            await self.service.buy(self.identity, "萝卜", 2, "buy")
        with self.assertRaisesRegex(FarmError, "operation_conflict"):
            await self.service.sow(self.identity, "萝卜", 1, "buy")
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.account.point, 490)
        self.assertEqual(snapshot.inventory[0].seeds, 1)

    async def test_same_operation_concurrently_commits_once(self):
        results = await asyncio.gather(*(
            self.service.buy(self.identity, "萝卜", 1, "same")
            for _ in range(20)
        ))
        self.assertTrue(all(result == results[0] for result in results))
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.account.point, 490)
        self.assertEqual(snapshot.inventory[0].seeds, 1)
        self.assertEqual(len(await self.store.ledger(self.identity)), 2)

    async def test_concurrent_buyers_cannot_overspend(self):
        results = await asyncio.gather(*(
            self.service.buy(self.identity, "萝卜", 1, f"buy-{index}")
            for index in range(60)
        ), return_exceptions=True)
        self.assertEqual(sum(not isinstance(r, Exception) for r in results), 50)
        failures = [r for r in results if isinstance(r, Exception)]
        self.assertTrue(all(
            isinstance(r, FarmError) and r.code == "insufficient_funds"
            for r in failures
        ))
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.account.point, 0)
        self.assertEqual(snapshot.inventory[0].seeds, 50)

    async def test_concurrent_harvest_cannot_claim_same_season_twice(self):
        await self.service.buy(self.identity, "萝卜", 1, "buy")
        await self.service.sow(self.identity, "萝卜", 1, "sow")
        self.now += 2
        results = await asyncio.gather(*(
            self.service.harvest(self.identity, f"harvest-{index}")
            for index in range(10)
        ), return_exceptions=True)
        self.assertEqual(sum(not isinstance(r, Exception) for r in results), 1)
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.inventory[0].crops, 2)
        self.assertEqual(snapshot.account.experience, 20)

    async def test_restart_and_cancelled_request_can_replay_result(self):
        entered = threading.Event()
        release = threading.Event()
        original = SQLiteRepository.stock

        def blocked(repo, *args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test worker was not released")
            original(repo, *args, **kwargs)

        with patch.object(SQLiteRepository, "stock", blocked):
            task = asyncio.create_task(
                self.service.buy(self.identity, "萝卜", 1, "cancelled-buy")
            )
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
                await self.store.close()
        with self.assertRaises(StorageError):
            await self.service.snapshot(self.identity)
        await self.store.initialize()
        result = await self.service.buy(
            self.identity, "萝卜", 1, "cancelled-buy",
        )
        self.assertEqual(result.data["account"]["point"], 490)
        self.assertEqual(
            (await self.service.snapshot(self.identity)).inventory[0].seeds, 1,
        )

    async def test_schema_version_is_not_silently_adopted(self):
        await self.store.close()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA user_version=99")
        with self.assertRaises(SchemaError):
            await self.store.initialize()

    async def test_foreign_database_is_rejected_without_conversion(self):
        path = Path(self.temporary.name) / "old.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE user(uid TEXT)")
        other = SQLiteStore(path)
        with self.assertRaises(SchemaError):
            await other.initialize()
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall(), [("user",)],
            )


if __name__ == "__main__":
    unittest.main()
