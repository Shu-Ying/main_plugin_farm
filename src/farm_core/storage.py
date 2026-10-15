"""显式初始化的 SQLite 存储；每个用例独占一条事务连接。"""

import asyncio
from contextlib import closing, contextmanager
import hashlib
import json
import logging
from pathlib import Path
import sqlite3

from .domain import (
    FarmError, Identity, Receipt, SchemaError, Snapshot, StorageError,
)
from .repository import SQLiteRepository

LOGGER = logging.getLogger(__name__)
APPLICATION_ID = 0x4641524D
SCHEMA_VERSION = 1

SCHEMA = (
    """CREATE TABLE accounts(
        identity TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        point INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(point)='integer' AND point>=0),
        vip_point INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(vip_point)='integer' AND vip_point>=0),
        experience INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(experience)='integer' AND experience>=0)
    )""",
    """CREATE TABLE operations(
        identity TEXT NOT NULL REFERENCES accounts(identity),
        operation_id TEXT NOT NULL,
        action TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        result TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY(identity, operation_id)
    )""",
    """CREATE TABLE inventory(
        identity TEXT NOT NULL REFERENCES accounts(identity),
        name TEXT NOT NULL,
        seeds INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(seeds)='integer' AND seeds>=0),
        crops INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(crops)='integer' AND crops>=0),
        locked INTEGER NOT NULL DEFAULT 0 CHECK(locked IN (0,1)),
        PRIMARY KEY(identity, name)
    )""",
    """CREATE TABLE plots(
        identity TEXT NOT NULL REFERENCES accounts(identity),
        slot INTEGER NOT NULL CHECK(slot>0),
        plant TEXT,
        mature_at INTEGER,
        harvest_count INTEGER NOT NULL DEFAULT 0 CHECK(harvest_count>=0),
        yield_bonus INTEGER NOT NULL DEFAULT 0,
        experience_bonus INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(identity, slot)
    )""",
    """CREATE TABLE ledger(
        id INTEGER PRIMARY KEY,
        identity TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        asset TEXT NOT NULL
            CHECK(asset IN ('point','vip_point','experience')),
        delta INTEGER NOT NULL CHECK(typeof(delta)='integer' AND delta!=0),
        reason TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(identity, operation_id)
            REFERENCES operations(identity, operation_id)
            DEFERRABLE INITIALLY DEFERRED
    )""",
)


class SQLiteStore:
    def __init__(self, path: str | Path, timeout: float = 10):
        if str(path) == ":memory:":
            raise ValueError("Use a dedicated file for transaction connections")
        self.path = Path(path).resolve()
        self._timeout = timeout
        self._ready = False
        self._pending = set()
        self._lifecycle = asyncio.Lock()

    async def _offload(self, function):
        task = asyncio.create_task(asyncio.to_thread(function))
        self._pending.add(task)

        def finished(completed):
            self._pending.discard(completed)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)
        return await asyncio.shield(task)

    @contextmanager
    def _connection(self):
        try:
            with closing(sqlite3.connect(
                self.path, timeout=self._timeout, isolation_level=None,
            )) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                yield connection
        except sqlite3.Error as exc:
            raise StorageError("sqlite_failure") from exc

    @staticmethod
    def _validate(connection):
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        expected = {"accounts", "operations", "inventory", "plots", "ledger"}
        if (
            app_id != APPLICATION_ID or version != SCHEMA_VERSION
            or tables != expected
        ):
            raise SchemaError("unsupported_database_schema")

    async def initialize(self) -> None:
        async with self._lifecycle:
            await self._offload(self._initialize)
            self._ready = True

    def _initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                app = connection.execute("PRAGMA application_id").fetchone()[0]
                version = connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if app == 0 and version == 0 and not tables:
                    for statement in SCHEMA:
                        connection.execute(statement)
                    connection.execute(
                        f"PRAGMA application_id={APPLICATION_ID}"
                    )
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                self._validate(connection)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    async def close(self) -> None:
        async with self._lifecycle:
            self._ready = False
            pending = tuple(self._pending)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    def _ensure_ready(self):
        if not self._ready:
            raise StorageError("store_not_initialized_or_closed")

    async def transact(
        self, identity: Identity, operation_id: str, action: str,
        parameters: dict, now: int, operation,
    ) -> Receipt:
        self._ensure_ready()
        request = json.dumps(
            {"action": action, "parameters": parameters},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(request.encode("utf-8")).hexdigest()

        def execute():
            with self._connection() as connection:
                self._validate(connection)
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT fingerprint, result FROM operations "
                        "WHERE identity=? AND operation_id=?",
                        (identity.key, operation_id),
                    ).fetchone()
                    if existing:
                        if existing["fingerprint"] != fingerprint:
                            raise FarmError("operation_conflict")
                        result = json.loads(existing["result"])
                    else:
                        repository = SQLiteRepository(
                            connection, identity.key, operation_id, action, now,
                        )
                        result = operation(repository)
                        connection.execute(
                            "INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                identity.key, operation_id, action, fingerprint,
                                json.dumps(result, ensure_ascii=False), now,
                            ),
                        )
                    connection.commit()
                except BaseException as exc:
                    connection.rollback()
                    LOGGER.log(
                        logging.INFO if isinstance(exc, FarmError)
                        else logging.WARNING,
                        "farm rollback action=%s operation=%s error=%s",
                        action, operation_id, type(exc).__name__,
                    )
                    raise
            LOGGER.info(
                "farm committed action=%s operation=%s", action, operation_id,
            )
            return Receipt(operation_id, action, result)

        return await self._offload(execute)

    async def snapshot(self, identity: Identity) -> Snapshot:
        self._ensure_ready()

        def query():
            with self._connection() as connection:
                self._validate(connection)
                connection.execute("BEGIN")
                repository = SQLiteRepository(
                    connection, identity.key, "", "query", 0,
                )
                result = Snapshot(
                    repository.account(), repository.items(),
                    repository.plots(),
                )
                connection.commit()
                return result

        return await self._offload(query)

    async def ledger(self, identity: Identity) -> tuple[dict, ...]:
        self._ensure_ready()

        def query():
            with self._connection() as connection:
                self._validate(connection)
                rows = connection.execute(
                    "SELECT operation_id, asset, delta, reason, created_at "
                    "FROM ledger WHERE identity=? ORDER BY id",
                    (identity.key,),
                ).fetchall()
                return tuple(dict(row) for row in rows)

        return await self._offload(query)
