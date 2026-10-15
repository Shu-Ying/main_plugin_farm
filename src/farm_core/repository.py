"""单个 SQLite 事务内的仓储；不自行提交或开启事务。"""

from dataclasses import asdict
import json
import sqlite3

from .domain import (
    Account, Asset, FarmError, InventoryItem, Plot, Plant, StorageError,
    integer,
)


class SQLiteRepository:
    def __init__(
        self, connection: sqlite3.Connection, identity: str,
        operation_id: str, action: str, now: int,
    ):
        self._db = connection
        self._identity = identity
        self._operation_id = operation_id
        self._action = action
        self._now = now

    def account(self) -> Account:
        row = self._db.execute(
            "SELECT name, point, vip_point, experience "
            "FROM accounts WHERE identity=?", (self._identity,),
        ).fetchone()
        if row is None:
            raise FarmError("not_registered")
        return Account(**dict(row))

    def register(self, name: str) -> bool:
        exists = self._db.execute(
            "SELECT 1 FROM accounts WHERE identity=?", (self._identity,),
        ).fetchone()
        if exists:
            return False
        self._db.execute(
            "INSERT INTO accounts(identity, name) VALUES (?, ?)",
            (self._identity, name),
        )
        self._db.executemany(
            "INSERT INTO plots(identity, slot) VALUES (?, ?)",
            [(self._identity, slot) for slot in range(1, 4)],
        )
        self.asset(Asset.POINT, 500)
        return True

    def asset(self, asset: Asset, delta: int) -> None:
        if not isinstance(asset, Asset):
            raise FarmError("invalid_asset")
        integer(delta, -(2**63 - 1))
        previous = getattr(self.account(), asset.value)
        updated = previous + delta
        if updated < 0:
            raise FarmError("insufficient_funds")
        integer(updated)
        if delta == 0:
            return
        column = asset.value
        cursor = self._db.execute(
            f"UPDATE accounts SET {column}=? "
            f"WHERE identity=? AND {column}=?",
            (updated, self._identity, previous),
        )
        if cursor.rowcount != 1:
            raise FarmError("state_conflict")
        self._db.execute(
            "INSERT INTO ledger("
            "identity, operation_id, asset, delta, reason, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                self._identity, self._operation_id, asset.value, delta,
                self._action, self._now,
            ),
        )

    def item(self, name: str) -> InventoryItem:
        row = self._db.execute(
            "SELECT name, seeds, crops, locked FROM inventory "
            "WHERE identity=? AND name=?", (self._identity, name),
        ).fetchone()
        if row is None:
            return InventoryItem(name)
        return InventoryItem(
            row["name"], row["seeds"], row["crops"], bool(row["locked"]),
        )

    def items(self) -> tuple[InventoryItem, ...]:
        rows = self._db.execute(
            "SELECT name, seeds, crops, locked FROM inventory "
            "WHERE identity=? ORDER BY name", (self._identity,),
        ).fetchall()
        return tuple(
            InventoryItem(r["name"], r["seeds"], r["crops"], bool(r["locked"]))
            for r in rows
        )

    def stock(self, name: str, seeds: int = 0, crops: int = 0) -> None:
        previous = self.item(name)
        new_seeds, new_crops = previous.seeds + seeds, previous.crops + crops
        if min(new_seeds, new_crops) < 0:
            raise FarmError("insufficient_stock")
        integer(new_seeds)
        integer(new_crops)
        self._db.execute(
            "INSERT INTO inventory(identity, name, seeds, crops) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(identity, name) "
            "DO UPDATE SET seeds=excluded.seeds, crops=excluded.crops",
            (self._identity, name, new_seeds, new_crops),
        )

    def lock(self, name: str, locked: bool) -> None:
        self.stock(name)
        self._db.execute(
            "UPDATE inventory SET locked=? WHERE identity=? AND name=?",
            (int(locked), self._identity, name),
        )

    def plots(self) -> tuple[Plot, ...]:
        rows = self._db.execute(
            "SELECT * FROM plots WHERE identity=? ORDER BY slot",
            (self._identity,),
        ).fetchall()
        try:
            return tuple(
                Plot(
                    r["slot"],
                    Plant(**json.loads(r["plant"])) if r["plant"] else None,
                    r["mature_at"], r["harvest_count"],
                    r["yield_bonus"], r["experience_bonus"],
                )
                for r in rows
            )
        except (TypeError, ValueError) as exc:
            raise StorageError("invalid_plot_snapshot") from exc

    def save_plot(self, plot: Plot) -> None:
        data = (
            json.dumps(asdict(plot.plant), ensure_ascii=False)
            if plot.plant else None
        )
        cursor = self._db.execute(
            "UPDATE plots SET plant=?, mature_at=?, harvest_count=?, "
            "yield_bonus=?, experience_bonus=? WHERE identity=? AND slot=?",
            (
                data, plot.mature_at, plot.harvest_count, plot.yield_bonus,
                plot.experience_bonus, self._identity, plot.slot,
            ),
        )
        if cursor.rowcount != 1:
            raise FarmError("unknown_plot")
