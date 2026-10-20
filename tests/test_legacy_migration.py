import asyncio
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from farm_core import Catalogue, FarmService, Identity, SQLiteStore
from farm_core.domain import FarmError


def create_legacy(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
            CREATE TABLE user(uid TEXT PRIMARY KEY, name TEXT, exp INTEGER,
                              point INTEGER, vipPoint INTEGER, soil INTEGER);
            CREATE TABLE userSeed(uid TEXT, seed TEXT, count INTEGER);
            CREATE TABLE userPlant(uid TEXT, plant TEXT, count INTEGER,
                                   isLock INTEGER);
            CREATE TABLE userSoil(uid TEXT, soilIndex INTEGER, plantName TEXT,
                matureTime INTEGER, soilLevel INTEGER, wiltStatus INTEGER,
                bugStatus INTEGER, harvestCount INTEGER, isSoilPlanted INTEGER);
            CREATE TABLE userItem(uid TEXT, item TEXT, count INTEGER);
            INSERT INTO user VALUES ('1', '旧农场', 900, 1234, 56, 4);
            INSERT INTO userSeed VALUES ('1', '白萝卜', 12);
            INSERT INTO userPlant VALUES ('1', '白萝卜', 23, 1);
            INSERT INTO userSoil VALUES
                ('1', 1, '白萝卜', 2000, 2, 0, 1, 0, 1),
                ('1', 2, '白萝卜', 1000, 3, 1, 0, 0, 1),
                ('1', 3, '', 0, 0, 0, 0, 0, 0);
            INSERT INTO userItem VALUES ('1', '化肥', 7);
        ''')


class LegacyMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'farm.db'
        create_legacy(self.source)
        self.catalogue = Catalogue.bundled()
        self.store = SQLiteStore(self.root / 'farm.sqlite3')
        await self.store.initialize(self.catalogue)
        self.who = Identity('zhenxun-preview', 'bot', 'OneBot V11', '1')

    async def asyncTearDown(self):
        await self.store.close()
        self.temp.cleanup()

    async def migrate(self, who=None):
        return await self.store.migrate_legacy(
            self.source, who or self.who, self.catalogue, 1500,
        )

    async def assert_empty(self):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            for table in ('accounts', 'inventory', 'plots', 'operations',
                          'ledger'):
                self.assertEqual(db.execute(
                    f'SELECT COUNT(*) FROM {table}'
                ).fetchone()[0], 0)

    async def test_assets_plots_archive_and_source_preserved(self):
        before = self.source.read_bytes()
        self.assertTrue(await self.migrate())
        snapshot = await self.store.snapshot(self.who)
        self.assertEqual((snapshot.account.name, snapshot.account.point,
                          snapshot.account.vip_point,
                          snapshot.account.experience),
                         ('旧农场', 1234, 56, 900))
        item = snapshot.inventory[0]
        self.assertEqual((item.seeds, item.crops, item.locked), (12, 23, True))
        self.assertEqual(len(snapshot.plots), 4)
        self.assertEqual(snapshot.plots[0].mature_at, 2000)
        self.assertEqual(snapshot.plots[0].pest_count, 1)
        self.assertEqual(snapshot.plots[0].yield_bonus, 20)
        self.assertTrue(snapshot.plots[1].withered)
        self.assertEqual(snapshot.plots[1].experience_bonus, 28)
        self.assertIsNone(snapshot.plots[3].plant)
        with closing(sqlite3.connect(self.store.path)) as db, db:
            result = json.loads(db.execute(
                "SELECT result FROM operations WHERE action='legacy_import'"
            ).fetchone()[0])
            self.assertEqual(result['legacy_rows']['userItem'][0]['count'], 7)
            self.assertEqual(result['unsupported_tables'], ['userItem'])
            self.assertEqual(db.execute(
                'SELECT SUM(delta) FROM ledger WHERE asset=?', ('point',),
            ).fetchone()[0], 1234)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),
                             [])
        self.assertEqual(self.source.read_bytes(), before)

    async def test_repeated_import_does_not_restore_spent_assets(self):
        await self.migrate()
        service = FarmService(self.store, self.catalogue, clock=lambda: 1500)
        await service.buy(self.who, '白萝卜', 1, 'buy')
        before = await self.store.snapshot(self.who)
        self.assertFalse(await self.migrate())
        self.assertEqual(await self.store.snapshot(self.who), before)
        await self.store.close()
        self.store = SQLiteStore(self.root / 'farm.sqlite3')
        await self.store.initialize(self.catalogue)
        self.source.rename(self.root / 'farm.db.saved')
        self.assertFalse(await self.migrate())
        self.assertEqual(await self.store.snapshot(self.who), before)

    async def test_concurrent_identities_bind_only_once(self):
        other = Identity('zhenxun-preview', 'other', 'QQ', '1')
        results = await asyncio.gather(
            self.migrate(), self.migrate(other), return_exceptions=True,
        )
        self.assertEqual(sum(result is True for result in results), 1)
        failures = [r for r in results if isinstance(r, FarmError)]
        self.assertEqual([r.code for r in failures], ['legacy_identity_bound'])
        with closing(sqlite3.connect(self.store.path)) as db, db:
            self.assertEqual(db.execute(
                'SELECT COUNT(*) FROM accounts'
            ).fetchone()[0], 1)

    async def test_existing_account_is_not_overwritten(self):
        service = FarmService(self.store, self.catalogue, clock=lambda: 1500)
        await service.register(self.who, '新农场', 'new')
        before = await self.store.snapshot(self.who)
        with self.assertRaisesRegex(FarmError, 'legacy_account_conflict'):
            await self.migrate()
        self.assertEqual(await self.store.snapshot(self.who), before)

    async def test_unknown_crop_rolls_back_all_tables(self):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("UPDATE userSeed SET seed='不存在的作物'")
        with self.assertRaisesRegex(FarmError, 'unknown_plant'):
            await self.migrate()
        await self.assert_empty()

    async def test_negative_balance_is_rejected(self):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute('UPDATE user SET point=-1')
        with self.assertRaisesRegex(FarmError, 'invalid_integer'):
            await self.migrate()
        await self.assert_empty()

    async def test_ambiguous_crop_is_not_guessed(self):
        plant = self.catalogue.get('白萝卜')
        self.catalogue = Catalogue((plant, replace(plant, plant_id=999999)))
        with self.assertRaisesRegex(FarmError, 'ambiguous_plant'):
            await self.migrate()
        await self.assert_empty()

    async def test_duplicate_plot_rolls_back_and_can_retry_after_repair(self):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute('INSERT INTO userSoil SELECT * FROM userSoil '
                       'WHERE soilIndex=1')
        with self.assertRaisesRegex(FarmError, 'legacy_data_invalid'):
            await self.migrate()
        await self.assert_empty()
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute('DELETE FROM userSoil WHERE rowid='
                       '(SELECT MAX(rowid) FROM userSoil)')
        self.assertTrue(await self.migrate())

    async def test_missing_source_or_user_does_not_create_account(self):
        self.assertFalse(await self.migrate(
            Identity('zhenxun-preview', 'bot', 'OneBot V11', 'missing'),
        ))
        self.source.unlink()
        self.assertFalse(await self.migrate())
        await self.assert_empty()

    async def test_missing_schema_is_rejected(self):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute('DROP TABLE userSeed')
        with self.assertRaisesRegex(FarmError, 'legacy_schema_unsupported'):
            await self.migrate()
        await self.assert_empty()
