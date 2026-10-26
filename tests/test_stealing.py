import asyncio
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from farm_core import Catalogue, FarmService, Identity, SQLiteStore
from farm_core.domain import FarmError, Plant, Plot
from farm_core.repository import SQLiteRepository
from farm_core.yield_rules import remaining_yield


class StealingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.temp.name) / 'farm.db')
        await self.store.initialize()
        self.now = 100000
        self.plant = Plant(1, '测试菜', 0, 1, False, 0, 2, 10,
                           1, 100, 2, 100)
        self.service = FarmService(self.store, Catalogue([self.plant]),
                                   lambda: self.now)
        self.owner = Identity('test', 'local', 'qq', '1')
        self.thief = replace(self.owner, user_id='2')
        for who in (self.owner, self.thief):
            await self.service.register(who, who.user_id, 'register')
        self.fixture = 0

    async def asyncTearDown(self):
        await self.store.close()
        self.temp.cleanup()

    async def prepare(self, plots, owner=None):
        self.fixture += 1
        await self.store.transact(
            owner or self.owner, f'fixture-{self.fixture}', 'fixture', {},
            self.now, lambda repo: [repo.save_plot(p) for p in plots],
        )

    async def test_each_target_plot_random_bounds_replay_and_repeat(self):
        await self.prepare([Plot(i, self.plant, self.now) for i in range(1, 7)])
        with patch('farm_core.application.secrets.randbelow',
                   side_effect=[0, 2, 0, 2, 0, 2]):
            result = await self.service.steal(self.thief, self.owner, 'first')
        self.assertEqual([i['quantity'] for i in result.data['items']],
                         [1, 3, 1, 3, 1, 3])
        self.assertEqual(result.data['remaining_attempts'], 4)
        self.assertEqual(await self.service.steal(
            self.thief, self.owner, 'first'), result)
        repeated = await self.service.steal(self.thief, self.owner, 'again')
        self.assertEqual(repeated.data['quantity'], 0)
        self.assertEqual(repeated.data['skipped']['already_stolen'], 6)
        self.assertEqual(repeated.data['remaining_attempts'], 4)
        self.assertEqual((await self.service.snapshot(self.thief))
                         .inventory[0].crops, 12)

    async def test_protection_odd_yield_pests_and_bonus(self):
        odd = replace(self.plant, harvest=9)
        await self.prepare([
            Plot(1, odd, self.now, stolen_count=3),
            Plot(2, self.plant, self.now, stolen_count=5),
            Plot(3, self.plant, self.now, yield_bonus=20,
                 maturity_pests=3, stolen_count=4),
        ])
        with patch('farm_core.application.secrets.randbelow', return_value=2):
            result = await self.service.steal(self.thief, self.owner, 'steal')
        self.assertEqual([i['quantity'] for i in result.data['items']], [1, 1])
        self.assertEqual(result.data['skipped']['protected'], 1)
        plots = (await self.service.snapshot(self.owner)).plots
        self.assertEqual([remaining_yield(p) for p in plots[:3]], [5, 5, 5])

    async def test_harvest_preserves_remaining_and_resets_next_season(self):
        await self.prepare([Plot(1, self.plant, self.now)])
        with patch('farm_core.application.secrets.randbelow', return_value=2):
            await self.service.steal(self.thief, self.owner, 'first')
        receipt = await self.service.harvest(self.owner, 'harvest')
        self.assertEqual(receipt.data['quantity'], 7)
        self.assertEqual((await self.service.snapshot(self.owner))
                         .plots[0].stolen_count, 0)
        self.now += 1000
        again = await self.service.steal(self.thief, self.owner, 'next')
        self.assertGreater(again.data['quantity'], 0)

    async def test_concurrent_thieves_never_cross_protected_half(self):
        await self.prepare([Plot(1, self.plant, self.now)])
        thieves = [replace(self.thief, user_id=str(i)) for i in range(3, 13)]
        for who in thieves:
            await self.service.register(who, who.user_id, 'register')
        with patch('farm_core.application.secrets.randbelow', return_value=2):
            results = await asyncio.gather(*[
                self.service.steal(who, self.owner, 'steal') for who in thieves
            ])
        self.assertEqual(sum(r.data['quantity'] for r in results), 5)
        self.assertEqual(remaining_yield(
            (await self.service.snapshot(self.owner)).plots[0]), 5)

    async def test_daily_quota_failed_visits_free_persistent_and_midnight(self):
        self.now = 86400-28800-1
        empty = await self.service.steal(self.thief, self.owner, 'empty')
        self.assertEqual(empty.data['remaining_attempts'], 5)
        for i in range(5):
            owner = replace(self.owner, user_id=str(i+20))
            await self.service.register(owner, str(i), 'register')
            await self.prepare([Plot(1, self.plant, self.now)], owner)
            await self.service.steal(self.thief, owner, f'steal-{i}')
        await self.store.close()
        await self.store.initialize()
        with self.assertRaisesRegex(FarmError, 'steal_daily_limit'):
            await self.service.steal(self.thief, self.owner, 'limit')
        self.now += 1
        await self.prepare([Plot(1, self.plant, self.now)])
        receipt = await self.service.steal(self.thief, self.owner, 'new-day')
        self.assertEqual(receipt.data['remaining_attempts'], 4)

    async def test_denied_targets_and_atomic_rollback(self):
        for target, code in (
            (self.thief, 'cannot_steal_self'),
            (replace(self.owner, realm='other'), 'different_farm_scope'),
            (replace(self.owner, user_id='missing'), 'target_not_registered'),
        ):
            with self.assertRaisesRegex(FarmError, code):
                await self.service.steal(self.thief, target, code)
        await self.prepare([Plot(1, self.plant, self.now)])
        before = [await self.service.snapshot(w)
                  for w in (self.owner, self.thief)]
        with patch.object(SQLiteRepository, 'record_theft',
                          side_effect=sqlite3.OperationalError('fixture')):
            with self.assertRaises(Exception):
                await self.service.steal(self.thief, self.owner, 'rollback')
        self.assertEqual([await self.service.snapshot(w)
                          for w in (self.owner, self.thief)], before)
        receipt = await self.service.steal(self.thief, self.owner, 'rollback')
        self.assertGreater(receipt.data['quantity'], 0)

    async def test_v3_migration_preserves_plots_and_initializes_theft_state(self):
        await self.prepare([Plot(1, self.plant, self.now)])
        before = await self.service.snapshot(self.owner)
        await self.store.close()
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute('DROP TABLE thefts')
            db.execute('ALTER TABLE plots DROP COLUMN stolen_count')
            db.execute('ALTER TABLE plots DROP COLUMN land_level')
            db.execute('PRAGMA user_version=3')
        await self.store.initialize()
        self.assertEqual(await self.service.snapshot(self.owner), before)
        await self.service.steal(self.thief, self.owner, 'after-migration')

    async def test_concurrent_harvest_and_steal_conserve_yield(self):
        await self.prepare([Plot(1, self.plant, self.now)])
        results = await asyncio.gather(
            self.service.harvest(self.owner, 'harvest'),
            self.service.steal(self.thief, self.owner, 'steal'),
        )
        self.assertEqual(sum(r.data['quantity'] for r in results), 10)
