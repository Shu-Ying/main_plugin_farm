import asyncio
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from farm_core import Asset, Catalogue, FarmService, Identity, SQLiteStore
from farm_core.domain import FarmError, Plot
from farm_core.repository import SQLiteRepository


class LandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'farm.sqlite3'
        self.store = SQLiteStore(self.path)
        await self.store.initialize()
        self.service = FarmService(self.store, Catalogue.bundled(), lambda: 1000)
        self.who = Identity('test', 'bot', 'qq', 'land')
        await self.service.register(self.who, '农场', 'register')

    async def asyncTearDown(self):
        await self.store.close()
        self.temp.cleanup()

    def old_account(self, count, missing_count=False):
        with closing(sqlite3.connect(self.path)) as db, db:
            result = json.loads(db.execute(
                "SELECT result FROM operations WHERE action='register'"
            ).fetchone()[0])
            if missing_count:
                result.pop('plot_count', None)
            else:
                result['plot_count'] = 3
            db.execute("UPDATE operations SET result=? WHERE action='register'",
                       (json.dumps(result),))
            db.execute('DELETE FROM plots WHERE slot>?', (count,))
            db.executemany('INSERT OR IGNORE INTO plots(identity, slot) '
                           'VALUES (?, ?)', [(self.who.key, s)
                                            for s in range(1, count + 1)])

    async def funds(self, point=30000, experience=5600):
        def operation(repo):
            account = repo.account()
            repo.asset(Asset.POINT, point - account.point)
            repo.asset(Asset.EXPERIENCE, experience - account.experience)
            return {}
        await self.store.transact(self.who, 'funds', 'fixture', {}, 1000,
                                  operation)

    async def test_new_account_conditions_charge_and_replay(self):
        await self.funds(point=10000, experience=3000)
        conditions = await self.service.reclaim_conditions(self.who)
        self.assertEqual((conditions['slot'], conditions['required_level'],
                          conditions['coin_cost']), (7, 5, 10000))
        receipt = await self.service.reclaim(self.who, 'reclaim')
        self.assertEqual(receipt.data['slot'], 7)
        self.assertEqual(receipt.data['account']['point'], 0)
        self.assertEqual(len((await self.service.snapshot(self.who)).plots), 7)
        self.assertEqual(await self.service.reclaim(self.who, 'reclaim'),
                         receipt)
        self.assertEqual((await self.service.reclaim_conditions(
            self.who,
        ))['coin_cost'], 20000)

    async def test_level_balance_and_unknown_rule_leave_state(self):
        with self.assertRaisesRegex(FarmError, 'not_registered'):
            await self.service.reclaim(replace(self.who, user_id='missing'),
                                        'not-registered')
        with self.assertRaisesRegex(FarmError, 'level_required'):
            await self.service.reclaim(self.who, 'level')
        await self.funds(point=9999, experience=3000)
        before = await self.store.snapshot(self.who)
        with self.assertRaisesRegex(FarmError, 'insufficient_funds'):
            await self.service.reclaim(self.who, 'balance')
        self.assertEqual(await self.store.snapshot(self.who), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany('INSERT INTO plots(identity, slot) VALUES (?, ?)',
                           [(self.who.key, s) for s in range(7, 25)])
        before = await self.store.snapshot(self.who)
        with self.assertRaisesRegex(FarmError, 'land_rule_unavailable'):
            await self.service.reclaim(self.who, 'unconfigured')
        self.assertEqual(await self.store.snapshot(self.who), before)

    async def test_old_paid_land_is_preserved_and_compensation_survives_restart(self):
        self.old_account(8, missing_count=True)
        plant = self.service.catalogue.get('白萝卜')
        original = Plot(1, plant, 5000, yield_bonus=20)
        await self.store.transact(
            self.who, 'crop', 'fixture', {}, 1000,
            lambda repo: (repo.save_plot(original) or {}),
        )
        before = await self.store.snapshot(self.who)
        snapshots = await asyncio.gather(*(
            self.service.snapshot(self.who) for _ in range(4)
        ))
        self.assertTrue(all(len(s.plots) == 11 for s in snapshots))
        self.assertEqual(snapshots[0].account, before.account)
        self.assertEqual(snapshots[0].plots[:8], before.plots)
        self.assertTrue(all(p.plant is None and p.yield_bonus == 0
                            for p in snapshots[0].plots[8:]))
        await self.store.close()
        await self.store.initialize()
        self.assertEqual(len((await self.service.snapshot(self.who)).plots), 11)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM operations "
                             "WHERE action='land_compensation'").fetchone()[0],
                             1)

    async def test_old_three_and_five_receive_three(self):
        for count in (3, 5, 27):
            with self.subTest(count=count):
                self.old_account(count)
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute("DELETE FROM operations "
                               "WHERE action='land_compensation'")
                self.assertEqual(len((await self.service.snapshot(
                    self.who,
                )).plots), count + 3)

    async def test_unknown_capacity_and_noncontiguous_keep_all_assets(self):
        self.old_account(28)
        before = await self.store.snapshot(self.who)
        with self.assertRaisesRegex(FarmError, 'land_compensation_capacity'):
            await self.service.snapshot(self.who)
        self.assertEqual(await self.store.snapshot(self.who), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM plots WHERE slot>5 OR slot=2')
        before = await self.store.snapshot(self.who)
        with self.assertRaisesRegex(FarmError, 'land_layout_invalid'):
            await self.service.snapshot(self.who)
        self.assertEqual(await self.store.snapshot(self.who), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM operations WHERE action='register'")
        with self.assertRaisesRegex(FarmError, 'land_origin_unknown'):
            await self.service.snapshot(self.who)
        self.assertEqual(await self.store.snapshot(self.who), before)

    async def test_compensation_failure_rolls_back_and_can_retry(self):
        self.old_account(3)
        before = await self.store.snapshot(self.who)
        original = SQLiteRepository.add_plot

        def fail(repo, slot):
            original(repo, slot)
            raise RuntimeError('fixture')

        with patch.object(SQLiteRepository, 'add_plot', fail):
            with self.assertRaises(RuntimeError):
                await self.service.snapshot(self.who)
        self.assertEqual(await self.store.snapshot(self.who), before)
        self.assertEqual(len((await self.service.snapshot(self.who)).plots), 6)

    async def test_reclaim_failure_and_concurrent_different_events(self):
        await self.funds()
        await self.service.snapshot(self.who)
        before = await self.store.snapshot(self.who)
        with patch.object(SQLiteRepository, 'add_plot',
                          side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):
                await self.service.reclaim(self.who, 'failed')
        self.assertEqual(await self.store.snapshot(self.who), before)
        receipts = await asyncio.gather(
            self.service.reclaim(self.who, 'one'),
            self.service.reclaim(self.who, 'two'),
        )
        self.assertEqual({r.data['slot'] for r in receipts}, {7, 8})
        self.assertEqual((await self.service.snapshot(self.who)).account.point, 0)

    async def test_same_event_concurrently_charges_once(self):
        await self.funds(point=10000, experience=3000)
        receipts = await asyncio.gather(*(
            self.service.reclaim(self.who, 'same-event') for _ in range(4)
        ))
        self.assertTrue(all(r == receipts[0] for r in receipts))
        self.assertEqual(len((await self.service.snapshot(self.who)).plots), 7)
        ledger = await self.store.ledger(self.who)
        costs = [entry['delta'] for entry in ledger
                 if entry['operation_id'] == 'same-event']
        self.assertEqual(costs, [-10000])

    async def test_last_configured_plot_can_be_bought_without_extrapolation(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany('INSERT INTO plots(identity, slot) VALUES (?, ?)',
                           [(self.who.key, s) for s in range(7, 24)])
        await self.funds(point=2000000, experience=156000)
        receipt = await self.service.reclaim(self.who, 'last')
        self.assertEqual(receipt.data['slot'], 24)
        self.assertEqual(receipt.data['cost'], 2000000)
        self.assertEqual(receipt.data['account']['point'], 0)
        with self.assertRaisesRegex(FarmError, 'land_rule_unavailable'):
            await self.service.reclaim(self.who, 'beyond')

    async def test_legacy_import_receives_compensation_after_migration(self):
        from test_legacy_migration import create_legacy
        source = Path(self.temp.name) / 'old.db'
        create_legacy(source)
        legacy = replace(self.who, user_id='1')
        await self.store.migrate_legacy(source, legacy, self.service.catalogue,
                                        1000)
        before = await self.store.snapshot(legacy)
        after = await self.service.snapshot(legacy)
        self.assertEqual(len(after.plots), 7)
        self.assertEqual(after.account, before.account)
        self.assertEqual(after.plots[:4], before.plots)
