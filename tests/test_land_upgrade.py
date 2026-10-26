import asyncio
import json
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from farm_core import Asset, Catalogue, FarmService, Identity, SQLiteStore
from farm_core.domain import FarmError, Plot
from farm_core.repository import SQLiteRepository


class UpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'farm.sqlite3'
        self.store = SQLiteStore(self.path)
        await self.store.initialize()
        self.now = 1000
        self.service = FarmService(self.store, Catalogue.bundled(),
                                   lambda: self.now)
        self.who = Identity('test', 'bot', 'qq', 'upgrade')
        await self.service.register(self.who, '农场', 'register')

    async def asyncTearDown(self):
        await self.store.close()
        self.temp.cleanup()

    async def fund(self, coins=100000000, exp=10000000):
        def operation(repo):
            account = repo.account()
            repo.asset(Asset.POINT, coins - account.point)
            repo.asset(Asset.EXPERIENCE, exp - account.experience)
            return {}
        await self.store.transact(self.who, f'fund:{coins}:{exp}',
                                  'fixture', {}, self.now, operation)

    async def test_tiers_cost_ordinal_replay_and_restart(self):
        await self.fund()
        self.assertEqual((await self.service.upgrade_conditions(
            self.who, 1,
        ))['coin_cost'], 200000)
        first = await self.service.upgrade(self.who, 1, 'red')
        self.assertEqual(first.data['land_name'], '红土地')
        self.assertEqual(await self.service.upgrade(self.who, 1, 'red'), first)
        for operation in ('black', 'gold'):
            await self.service.upgrade(self.who, 1, operation)
        plot = (await self.service.snapshot(self.who)).plots[0]
        self.assertEqual((plot.land_level, plot.yield_bonus,
                          plot.experience_bonus), (3, 28, 28))
        condition = await self.service.upgrade_conditions(self.who, 2)
        self.assertEqual((condition['ordinal'], condition['coin_cost']),
                         (2, 220000))
        before = await self.store.snapshot(self.who)
        with self.assertRaisesRegex(FarmError, 'land_max_level'):
            await self.service.upgrade(self.who, 1, 'fourth')
        with self.assertRaisesRegex(FarmError, 'operation_conflict'):
            await self.service.upgrade(self.who, 2, 'red')
        self.assertEqual(await self.store.snapshot(self.who), before)
        await self.store.close()
        await self.store.initialize()
        self.assertEqual((await self.service.snapshot(self.who)).plots[0], plot)

    async def test_current_season_matures_only_once_and_next_season_grows(self):
        await self.fund()
        plant = next(p for p in self.service.catalogue if p.crop > 1)
        await self.service.buy(self.who, f'#{plant.plant_id}', 1, 'buy')
        await self.service.sow(self.who, f'#{plant.plant_id}', 1, 'sow')
        await self.service.upgrade(self.who, 1, 'red')
        plot = (await self.service.snapshot(self.who)).plots[0]
        self.assertEqual((plot.mature_at, plot.harvest_count), (self.now, 0))
        await self.service.harvest(self.who, 'harvest')
        plot = (await self.service.snapshot(self.who)).plots[0]
        self.assertEqual(plot.harvest_count, 1)
        self.assertGreater(plot.mature_at, self.now)
        await self.service.upgrade(self.who, 1, 'black')
        plot = (await self.service.snapshot(self.who)).plots[0]
        self.assertEqual((plot.harvest_count, plot.mature_at), (1, self.now))
        if plant.crop > 2:
            await self.service.harvest(self.who, 'harvest2')
            next_plot = (await self.service.snapshot(self.who)).plots[0]
            self.assertEqual(next_plot.growth_remaining,
                             (plant.regrowth_seconds * 80 + 99) // 100 * 100)

    async def test_level_balance_invalid_slot_and_rollback(self):
        for slot in (0, -1, True, 1.5, 31):
            with self.assertRaises(FarmError):
                await self.service.upgrade(self.who, slot, 'invalid')
        with self.assertRaisesRegex(FarmError, 'unknown_plot'):
            await self.service.upgrade(self.who, 7, 'missing')
        with self.assertRaisesRegex(FarmError, 'level_required'):
            await self.service.upgrade(self.who, 1, 'level')
        await self.fund(coins=199999)
        before = await self.store.snapshot(self.who)
        with self.assertRaisesRegex(FarmError, 'insufficient_funds'):
            await self.service.upgrade(self.who, 1, 'poor')
        self.assertEqual(await self.store.snapshot(self.who), before)
        await self.fund()
        before = await self.store.snapshot(self.who)
        with patch.object(SQLiteRepository, 'save_plot',
                          side_effect=RuntimeError('fault')):
            with self.assertRaisesRegex(RuntimeError, 'fault'):
                await self.service.upgrade(self.who, 1, 'rollback')
        self.assertEqual(await self.store.snapshot(self.who), before)

    async def test_concurrent_same_message_single_charge(self):
        await self.fund()
        before = await self.store.snapshot(self.who)
        results = await asyncio.gather(*(
            self.service.upgrade(self.who, 1, 'same') for _ in range(12)
        ))
        self.assertTrue(all(r == results[0] for r in results))
        after = await self.store.snapshot(self.who)
        self.assertEqual(after.plots[0].land_level, 1)
        self.assertEqual(before.account.point - after.account.point, 200000)

    async def test_upgrade_preserves_pests_theft_and_withered_state(self):
        await self.fund()
        plant = next(p for p in self.service.catalogue if p.crop > 1)
        original = Plot(1, plant, self.now - 1, pest_count=1, pest_spawned=2,
                        maturity_pests=2, stolen_count=1)
        def operation(repo):
            repo.save_plot(original)
            repo.save_plot(Plot(2, plant, None, plant.crop))
            return {}
        await self.store.transact(self.who, 'setup', 'fixture', {}, self.now,
                                  operation)
        await self.service.upgrade(self.who, 1, 'ripe')
        await self.service.upgrade(self.who, 2, 'withered')
        plots = (await self.service.snapshot(self.who)).plots
        self.assertEqual((plots[0].maturity_pests, plots[0].stolen_count),
                         (2, 1))
        self.assertTrue(plots[1].withered)

    async def test_v4_migration_and_original_legacy_land_levels(self):
        await self.store.close()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('ALTER TABLE plots DROP COLUMN land_level')
            db.execute('PRAGMA user_version=4')
            db.execute('INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?)', (
                self.who.key, 'legacy-fixture', 'legacy_import', 'fixture',
                json.dumps({'legacy_rows': {'userSoil': [
                    {'soilIndex': 2, 'soilLevel': 3},
                    {'soilIndex': 3, 'soilLevel': 1},
                ]}}), self.now,
            ))
        await self.store.initialize()
        plots = (await self.store.snapshot(self.who)).plots
        self.assertEqual([p.land_level for p in plots], [0, 3, 1, 0, 0, 0])
        # 只恢复明确等级，不重写旧版已经保存的资产和加成。
        self.assertEqual(plots[1].yield_bonus, 0)

    async def test_growing_pests_freeze_at_forced_maturity(self):
        await self.fund()
        plant = self.service.catalogue.get('白萝卜')
        from farm_core.pests import start_growth
        plot = start_growth(Plot(1, plant), self.now)
        await self.store.transact(
            self.who, 'plant', 'fixture', {}, self.now,
            lambda repo: repo.save_plot(plot) or {},
        )
        self.now += max(7200, (plant.growth_seconds + 1) // 2) + 1
        await self.service.upgrade(self.who, 1, 'upgrade-pests')
        mature = (await self.service.snapshot(self.who)).plots[0]
        self.assertEqual((mature.mature_at, mature.growth_remaining,
                          mature.maturity_pests), (self.now, 0, 1))
        self.assertIsNone(mature.next_pest_at)
        self.now += 999999
        later = (await self.service.snapshot(self.who)).plots[0]
        self.assertEqual(later.pest_count, 1)

    async def test_ordinal_above_configured_table_is_rejected(self):
        await self.fund()
        def operation(repo):
            for slot in range(1, 25):
                if slot > 6:
                    repo.add_plot(slot)
                repo.save_plot(Plot(slot, land_level=1))
            repo.add_plot(25)
            return {}
        await self.store.transact(self.who, '24-red', 'fixture', {}, self.now,
                                  operation)
        before = await self.store.snapshot(self.who)
        with self.assertRaisesRegex(FarmError, 'land_rule_unavailable'):
            await self.service.upgrade(self.who, 25, '25th-red')
        self.assertEqual(await self.store.snapshot(self.who), before)
