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
from farm_core.pests import advance_plot, start_growth


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
        self.now = 8199
        self.assertEqual((await self.plot()).pest_count, 0)
        self.now = 8200
        first = await self.plot()
        self.assertEqual(first.pest_count, 1)
        self.assertEqual(first.growth_remaining, 720000)
        self.now = 15400
        second = await self.plot()
        self.assertEqual(second.pest_count, 2)
        self.assertEqual(second.growth_remaining, 36000)
        self.now = 15799
        self.assertGreater((await self.plot()).growth_remaining, 0)
        self.now = 15800
        mature = await self.plot()
        self.assertEqual(mature.mature_at, 15800)
        self.assertEqual(mature.maturity_pests, 2)
        receipt = await self.service.harvest(self.who, "harvest")
        self.assertEqual(receipt.data["quantity"], 90)
        self.assertEqual(receipt.data["experience"], 20)
        self.assertEqual(receipt.data["harvested"][0]["pests"], 2)
        again = await self.plot()
        self.assertEqual(again.pest_count, 0)
        self.assertEqual(again.maturity_pests, 0)

    async def test_clear_before_maturity_restores_rate_but_not_lost_time(self):
        self.now = 10000
        receipt = await self.service.clear_pests(self.who, "clear")
        self.assertEqual(receipt.data["quantity"], 1)
        cleared = await self.plot()
        self.assertEqual(cleared.pest_count, 0)
        self.assertEqual(cleared.growth_remaining, 549000)
        self.assertEqual(cleared.pest_spawned, 1)
        self.now = 15400
        self.assertEqual((await self.plot()).pest_count, 1)
        repeated = await self.service.clear_pests(self.who, "clear")
        self.assertEqual(repeated, receipt)
        self.assertEqual((await self.plot()).pest_count, 1)

    async def test_clear_after_maturity_cannot_erase_season_penalty(self):
        self.now = 20000
        await self.service.clear_pests(self.who, "late-clear")
        mature = await self.plot()
        self.assertEqual(mature.pest_count, 0)
        self.assertEqual(mature.maturity_pests, 2)
        receipt = await self.service.harvest(self.who, "harvest")
        self.assertEqual(receipt.data["quantity"], 90)

    async def test_reopen_preserves_cleared_progress_and_concurrent_clear(self):
        self.now = 10000
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
        self.now = 10000
        before = await self.store.snapshot(self.who)
        original = SQLiteRepository.save_plot

        def fail(repository, plot):
            original(repository, plot)
            raise RuntimeError("fixture failure")

        with patch.object(SQLiteRepository, "save_plot", fail):
            with self.assertRaises(RuntimeError):
                await self.service.clear_pests(self.who, "failed-clear")
        self.assertEqual(await self.store.snapshot(self.who), before)

    async def test_empty_clear_has_no_reward_and_clear_awards_per_pest(self):
        with self.assertRaisesRegex(FarmError, "nothing_to_clear"):
            await self.service.clear_pests(self.who, "empty-clear")
        self.now = 8200
        before = await self.service.snapshot(self.who)
        await self.service.clear_pests(self.who, "clear")
        after = await self.service.snapshot(self.who)
        self.assertEqual(after.account.experience, before.account.experience+1)
        self.assertEqual(after.account.point, before.account.point)
        self.assertEqual(after.account.vip_point, before.account.vip_point)

    async def test_multi_plot_pest_rewards_replay_and_transaction_rollback(self):
        await self.service.buy(self.who, '虫害测试菜', 1, 'buy-second')
        await self.service.sow(self.who, '虫害测试菜', 1, 'sow-second')
        self.now = 15400
        before = await self.store.snapshot(self.who)
        ledger = await self.store.ledger(self.who)
        with patch.object(SQLiteRepository, 'asset',
                          side_effect=RuntimeError('reward failure')):
            with self.assertRaises(RuntimeError):
                await self.service.clear_pests(self.who, 'clear-four')
        self.assertEqual(await self.store.snapshot(self.who), before)
        self.assertEqual(await self.store.ledger(self.who), ledger)
        receipts = await asyncio.gather(*(
            self.service.clear_pests(self.who, 'clear-four') for _ in range(3)
        ))
        self.assertTrue(all(r == receipts[0] for r in receipts))
        self.assertEqual(receipts[0].data['quantity'], 4)
        self.assertEqual(receipts[0].data['experience'], 4)
        after = await self.service.snapshot(self.who)
        self.assertEqual(after.account.experience, before.account.experience+4)
        with self.assertRaisesRegex(FarmError, 'nothing_to_clear'):
            await self.service.clear_pests(self.who, 'empty-after')
        self.assertEqual((await self.service.snapshot(self.who)).account,
                         after.account)

    async def test_projection_is_independent_of_query_frequency(self):
        initial = (await self.store.snapshot(self.who)).plots[0]
        direct = advance_plot(initial, 20000)
        split = initial
        for instant in (1001, 8199, 8200, 10000, 15400, 15800, 20000):
            split = advance_plot(split, instant)
        self.assertEqual(split, direct)
        self.assertEqual(direct.maturity_pests, 2)

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
        self.assertEqual(view.pest_count, 1)

    async def test_short_crops_mature_without_pests(self):
        stored = (await self.store.snapshot(self.who)).plots[0]
        for duration in (3600, 7200):
            with self.subTest(duration=duration):
                plant = replace(self.plant, growth_seconds=duration)
                plot = start_growth(replace(stored, plant=plant), 1000)
                mature = advance_plot(plot, 1000 + duration)
                self.assertEqual(mature.growth_remaining, 0)
                self.assertEqual(mature.mature_at, 1000 + duration)
                self.assertEqual(mature.pest_count, 0)
                self.assertEqual(mature.maturity_pests, 0)

    async def test_regrowth_uses_its_own_longer_pest_interval(self):
        stored = (await self.store.snapshot(self.who)).plots[0]
        plant = replace(self.plant, regrowth_seconds=36001)
        plot = start_growth(replace(
            stored, plant=plant, harvest_count=1,
        ), 1000)
        self.assertEqual(advance_plot(plot, 19000).pest_count, 0)
        self.assertEqual(advance_plot(plot, 19001).pest_count, 1)

    async def test_pending_pest_is_preserved_then_spacing_increases(self):
        stored = (await self.store.snapshot(self.who)).plots[0]
        old = replace(stored, next_pest_at=4600)
        first = advance_plot(old, 4600)
        self.assertEqual(first.pest_count, 1)
        self.assertEqual(first.next_pest_at, 11800)
        self.assertEqual(advance_plot(first, 11799).pest_count, 1)
        self.assertEqual(advance_plot(first, 11800).pest_count, 2)
