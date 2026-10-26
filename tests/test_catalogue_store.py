import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from farm_core import SQLiteStore


class CatalogueStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_store_is_not_created_by_catalogue_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'not-created.sqlite3'
            store = SQLiteStore(path)
            self.assertEqual(await store.catalogue_ids(), set())
            self.assertFalse(path.exists())

    async def test_existing_ids_read_without_changing_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'farm.sqlite3'
            store = SQLiteStore(path)
            await store.initialize()
            await store.close()
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('INSERT INTO accounts(identity,name) VALUES (?,?)',
                           ('fixture', 'synthetic'))
                db.execute('INSERT INTO inventory(identity,plant_id,name,seeds)'
                           ' VALUES (?,?,?,?)', ('fixture', 9001, 'test', 1))
                db.execute('INSERT INTO plots(identity,slot,plant) VALUES (?,?,?)',
                           ('fixture', 1, json.dumps({'plant_id': 9002})))
            before = path.read_bytes()
            self.assertEqual(await store.catalogue_ids(), {9001, 9002})
            self.assertEqual(path.read_bytes(), before)
