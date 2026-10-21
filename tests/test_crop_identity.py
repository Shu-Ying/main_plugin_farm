import json
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from farm_core import Catalogue, FarmError, FarmService, Identity, SQLiteStore
from farm_core.domain import Plant, SchemaError
from farm_core.storage import APPLICATION_ID, SCHEMA, SCHEMA_VERSION


def plant(plant_id=1, name="萝卜", **changes):
    return replace(
        Plant(plant_id, name, 0, 10, False, 0, 2, 3, 4, 2, 1, 1),
        **changes,
    )


class CropIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "farm.db"
        self.store = SQLiteStore(self.path)
        await self.store.initialize()
        self.now = 1000
        self.identity = Identity("test", "realm", "qq", "user")
        self.service = FarmService(
            self.store, Catalogue([plant()]), lambda: self.now,
        )
        await self.service.register(self.identity, "农场", "register")

    async def asyncTearDown(self):
        await self.store.close()
        self.temp.cleanup()

    async def test_same_name_requires_id_and_keeps_inventory_separate(self):
        self.service.catalogue = Catalogue([plant(), plant(2)])
        with self.assertRaisesRegex(FarmError, "ambiguous_plant"):
            await self.service.buy(self.identity, "萝卜", 1, "ambiguous")
        await self.service.buy(self.identity, "#1", 1, "first")
        await self.service.buy(self.identity, "#2", 2, "second")
        items = (await self.service.snapshot(self.identity)).inventory
        self.assertEqual(
            [(i.plant_id, i.seeds) for i in items], [(1, 1), (2, 2)],
        )
        await self.service.sow(self.identity, "#1", 1, "sow")
        self.now += 2
        await self.service.harvest(self.identity, "harvest")
        await self.service.lock(self.identity, "#1", True, "lock")
        with self.assertRaisesRegex(FarmError, "plant_locked"):
            await self.service.sell(self.identity, "#1", None, "locked")
        await self.service.lock(self.identity, "#1", False, "unlock")
        sale = await self.service.sell(self.identity, None, None, "sale")
        self.assertEqual(sale.data["proceeds"], 12)
        self.assertEqual(
            (await self.service.snapshot(self.identity)).inventory[1].seeds, 2,
        )

    async def test_rename_preserves_seeds_crops_and_lock(self):
        await self.service.buy(self.identity, "萝卜", 2, "buy")
        await self.service.sow(self.identity, "萝卜", 1, "sow")
        self.service.catalogue = Catalogue([plant(name="新萝卜")])
        self.now += 2
        await self.service.harvest(self.identity, "harvest")
        await self.service.lock(self.identity, "新萝卜", True, "lock")
        item = (await self.service.snapshot(self.identity)).inventory[0]
        self.assertEqual((item.plant_id, item.seeds, item.crops), (1, 1, 3))
        self.assertTrue(item.locked)
        await self.service.lock(self.identity, "新萝卜", False, "unlock")
        sale = await self.service.sell(self.identity, "新萝卜", None, "sale")
        self.assertEqual(sale.data["proceeds"], 12)

    async def test_purchase_rules_reject_without_debit(self):
        for index, changes in enumerate((
            {"purchasable": False}, {"enabled": False}, {"crop_type": 11},
        )):
            self.service.catalogue = Catalogue([plant(**changes)])
            with self.assertRaises(FarmError):
                await self.service.buy(self.identity, "萝卜", 1, str(index))
        snapshot = await self.service.snapshot(self.identity)
        self.assertEqual(snapshot.account.point, 500)
        self.assertEqual(snapshot.inventory, ())

    async def test_delisting_allows_sowing_but_disabled_blocks_it(self):
        await self.service.buy(self.identity, "萝卜", 2, "buy")
        self.service.catalogue = Catalogue([plant(purchasable=False)])
        await self.service.sow(self.identity, "萝卜", 1, "sow")
        self.service.catalogue = Catalogue([plant(enabled=False)])
        with self.assertRaisesRegex(FarmError, "plant_disabled"):
            await self.service.sow(self.identity, "萝卜", 1, "disabled")
        self.now += 2
        await self.service.harvest(self.identity, "harvest")
        await self.service.sell(self.identity, None, None, "sell")


class CatalogueMetadataTests(unittest.TestCase):
    def test_local_identity_has_no_web_id(self):
        carrot = Catalogue.bundled().get("胡萝卜")
        self.assertEqual(carrot.plant_id, 1)
        self.assertNotIn("source_crop_id", asdict(carrot))

    def test_legacy_purchase_flag_is_preserved(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads(
            (root / "src/farm_core/data/plants.json").read_bytes()
        )
        for row in data["plants"]:
            self.assertEqual(
                Plant.from_legacy(row).purchasable, bool(row["isBuy"]),
            )


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    def create_v1(self, path, unknown=False, version=1):
        with closing(sqlite3.connect(path)) as db, db:
            for statement in SCHEMA:
                if statement.startswith('CREATE TABLE thefts('):
                    continue
                if version == 1 and statement.startswith("CREATE TABLE inventory("):
                    statement = """CREATE TABLE inventory(
                        identity TEXT, name TEXT, seeds INTEGER,
                        crops INTEGER, locked INTEGER,
                        PRIMARY KEY(identity, name))"""
                if statement.startswith("CREATE TABLE plots("):
                    statement = """CREATE TABLE plots(
                        identity TEXT, slot INTEGER, plant TEXT,
                        mature_at INTEGER, harvest_count INTEGER,
                        yield_bonus INTEGER, experience_bonus INTEGER,
                        PRIMARY KEY(identity, slot))"""
                db.execute(statement)
            db.execute(f"PRAGMA application_id={APPLICATION_ID}")
            db.execute(f"PRAGMA user_version={version}")
            db.execute("INSERT INTO accounts VALUES ('user', '农场', 123, 4, 5)")
            name = "不认识的作物" if unknown else "萝卜"
            if version == 1:
                db.execute(
                    "INSERT INTO inventory VALUES ('user', ?, 7, 9, 1)",
                    (name,),
                )
            else:
                db.execute(
                    "INSERT INTO inventory VALUES ('user', 1, ?, 7, 9, 1)",
                    (name,),
                )
            snapshot = asdict(plant())
            for key in ("purchasable", "enabled", "crop_type"):
                snapshot.pop(key)
            db.execute(
                "INSERT INTO plots VALUES ('user', 1, ?, 1234, 0, 0, 0)",
                (json.dumps(snapshot),),
            )

    async def test_v1_migration_preserves_inventory_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "farm.db"
            self.create_v1(path)
            store = SQLiteStore(path)
            await store.initialize(catalogue=Catalogue([plant()]))
            await store.close()
            await store.initialize()
            await store.close()
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(
                    db.execute("PRAGMA user_version").fetchone()[0],
                    SCHEMA_VERSION,
                )
                row = db.execute(
                    "SELECT plant_id, name, seeds, crops, locked FROM inventory"
                ).fetchone()
                self.assertEqual(row, (1, "萝卜", 7, 9, 1))
                self.assertEqual(
                    db.execute("SELECT point FROM accounts").fetchone()[0], 123,
                )
                self.assertEqual(
                    db.execute("SELECT mature_at FROM plots").fetchone()[0],
                    1234,
                )
                snapshot = json.loads(db.execute(
                    "SELECT plant FROM plots"
                ).fetchone()[0])
                self.assertEqual(Plant(**snapshot).plant_id, 1)

    async def test_v2_migration_keeps_existing_season_without_retroactive_pests(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "farm.db"
            self.create_v1(path, version=2)
            store = SQLiteStore(path)
            await store.initialize()
            await store.close()
            await store.initialize()
            await store.close()
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute(
                    "PRAGMA user_version"
                ).fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(db.execute(
                    "SELECT mature_at, pest_count, pest_spawned, "
                    "growth_remaining, maturity_pests FROM plots"
                ).fetchone(), (1234, 0, 0, None, 0))
                self.assertEqual(db.execute(
                    "SELECT point FROM accounts"
                ).fetchone()[0], 123)

    async def test_unknown_v1_crop_rolls_back_instead_of_losing_stock(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "farm.db"
            self.create_v1(path, unknown=True)
            store = SQLiteStore(path)
            with self.assertRaises(SchemaError):
                await store.initialize(catalogue=Catalogue([plant()]))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(
                    db.execute("PRAGMA user_version").fetchone()[0], 1,
                )
                self.assertEqual(
                    db.execute("SELECT seeds, crops FROM inventory").fetchone(),
                    (7, 9),
                )

    async def test_ambiguous_v1_names_abort_without_partial_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "farm.db"
            self.create_v1(path)
            store = SQLiteStore(path)
            with self.assertRaisesRegex(
                SchemaError, "inventory_identity_unresolved",
            ):
                await store.initialize(
                    catalogue=Catalogue([plant(), plant(2)]),
                )
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(
                    db.execute("PRAGMA user_version").fetchone()[0], 1,
                )
                self.assertEqual(db.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE name='inventory_v2'"
                ).fetchall(), [])
