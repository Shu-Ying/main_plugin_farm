import asyncio
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from farm_core import Catalogue, FarmService, Identity, SQLiteStore
from farm_core.domain import FarmError, Plant
from farm_core.repository import SQLiteRepository
from farm_core.pests import advance_plot


class PestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "farm.db"
        self.store = SQLiteStore(self.path)
        await self.store.initialize()
        self.now = 1000
        self.plant = Plant(1, "虫害测试菜", 0, 1, False, 0, 20, 100,
                           1, 14400, 2, 14400)
        self.service = FarmService(self.store, Catalogue([self.plant]),
                                   lambda: self.now)
        self.who = Identity("test", "local", "qq", "pests")
        await self.service.register(self.who, "测试农场", "register")
        await self.service.buy(self.who, "虫害测试菜", 1, "buy")
        await self.service.sow(self.who, "虫害测试菜", 1, "sow")

    async def asyncTearDown(self):
        await self.store.close()
        self.temp.cleanup()

    async def plot(self):
        return (await self.service.snapshot(self.who)).plots[0]

    async def test_speed_integrates_each_pest_interval_and_offline_maturity(self):
        self.now = 4600
        first = await self.plot()
        self.assertEqual(first.pest_count, 1)
        self.assertEqual(first.growth_remaining, 1080000)
        self.now = 8200
        second = await self.plot()
        self.assertEqual(second.pest_count, 2)
        self.assertEqual(second.growth_remaining, 738000)
        self.now = 11800
        third = await self.plot()
        self.assertEqual(third.pest_count, 3)
        self.assertEqual(third.growth_remaining, 414000)
        self.now = 16670
        self.assertGreater((await self.plot()).growth_remaining, 0)
        self.now = 16671
        mature = await self.plot()
        self.assertEqual(mature.mature_at, 16671)
        self.assertEqual(mature.maturity_pests, 3)
        receipt = await self.service.harvest(self.who, "harvest")
        self.assertEqual(receipt.data["quantity"], 85)
        self.assertEqual(receipt.data["experience"], 20)
        self.assertEqual(receipt.data["harvested"][0]["pests"], 3)
        again = await self.plot()
        self.assertEqual(again.pest_count, 0)
        self.assertEqual(again.maturity_pests, 0)

    async def test_clear_before_maturity_restores_rate_but_not_lost_time(self):
        self.now = 6400
        receipt = await self.service.clear_pests(self.who, "clear")
        self.assertEqual(receipt.data["quantity"], 1)
        cleared = await self.plot()
        self.assertEqual(cleared.pest_count, 0)
        self.assertEqual(cleared.growth_remaining, 909000)
        self.assertEqual(cleared.pest_spawned, 1)
        self.now = 8200
        self.assertEqual((await self.plot()).pest_count, 1)
        repeated = await self.service.clear_pests(self.who, "clear")
        self.assertEqual(repeated, receipt)
        self.assertEqual((await self.plot()).pest_count, 1)

    async def test_clear_after_maturity_cannot_erase_season_penalty(self):
        self.now = 20000
        await self.service.clear_pests(self.who, "late-clear")
        mature = await self.plot()
        self.assertEqual(mature.pest_count, 0)
        self.assertEqual(mature.maturity_pests, 3)
        receipt = await self.service.harvest(self.who, "harvest")
        self.assertEqual(receipt.data["quantity"], 85)

    async def test_reopen_preserves_cleared_progress_and_concurrent_clear(self):
        self.now = 6400
        results = await asyncio.gather(
            self.service.clear_pests(self.who, "clear-1"),
            self.service.clear_pests(self.who, "clear-2"),
            return_exceptions=True,
        )
        self.assertEqual(sum(not isinstance(r, Exception) for r in results), 1)
        self.assertTrue(any(isinstance(r, FarmError) for r in results))
        before = await self.plot()
        await self.store.close()
        await self.store.initialize()
        self.assertEqual(await self.plot(), before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute(
                "SELECT pest_count, pest_spawned FROM plots WHERE slot=1"
            ).fetchone(), (0, 1))

    async def test_failed_clear_rolls_back_all_plot_updates(self):
        self.now = 6400
        before = await self.store.snapshot(self.who)
        original = SQLiteRepository.save_plot

        def fail(repository, plot):
            original(repository, plot)
            raise RuntimeError("fixture failure")

        with patch.object(SQLiteRepository, "save_plot", fail):
            with self.assertRaises(RuntimeError):
                await self.service.clear_pests(self.who, "failed-clear")
        self.assertEqual(await self.store.snapshot(self.who), before)

    async def test_empty_clear_and_ripe_clear_reward_no_assets(self):
        with self.assertRaisesRegex(FarmError, "nothing_to_clear"):
            await self.service.clear_pests(self.who, "empty-clear")
        self.now = 4600
        before = await self.service.snapshot(self.who)
        await self.service.clear_pests(self.who, "clear")
        after = await self.service.snapshot(self.who)
        self.assertEqual(before.account, after.account)

    async def test_projection_is_independent_of_query_frequency(self):
        initial = (await self.store.snapshot(self.who)).plots[0]
        direct = advance_plot(initial, 20000)
        split = initial
        for instant in (1001, 4599, 4600, 7000, 11800, 16671, 20000):
            split = advance_plot(split, instant)
        self.assertEqual(split, direct)
        self.assertEqual(direct.maturity_pests, 3)

    async def test_growth_stage_uses_work_not_predicted_finish_time(self):
        import sys
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "scripts"))
        from ci_font import choose_font
        from farm_render import FarmRenderer

        renderer = FarmRenderer(choose_font())
        self.plant = replace(self.plant, name="草莓")
        self.service.catalogue = Catalogue([self.plant])
        stored = (await self.store.snapshot(self.who)).plots[0]
        self.now = 8200
        projected = advance_plot(replace(stored, plant=self.plant), self.now)
        snapshot = replace(await self.service.snapshot(self.who),
                           plots=(projected,))
        view = renderer.scene(self.who, snapshot, self.now).plots[0]
        self.assertEqual(view.stage, 2)
        self.assertEqual(view.pest_count, 2)
