"""``PgBookkeeperStore`` — the Postgres adapter for the bookkeeper port.

Mirrors ``scheduler/stores/postgres.py``: sync psycopg, autocommit, an opaque ``scope`` column
(the tenant), and HASH(scope) partitioning on the transactional table (``DATA_MODEL`` pattern).
``clients`` is low-volume reference data (not partitioned). Every query filters by ``scope``.

The host points the vertical at this store by setting ``COGNO_BOOKKEEPER_DSN`` +
``COGNO_BOOKKEEPER_SCOPE`` (see ``server.py``).
"""

from __future__ import annotations

import uuid
from typing import Optional

import psycopg

from cogno_praxis.bookkeeper.store import Client, Transaction


def _ensure_schema(conn: "psycopg.Connection", partitions: int) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS bookkeeper_clients (
               scope text NOT NULL,
               client_id text NOT NULL,
               name text NOT NULL,
               PRIMARY KEY (scope, client_id))""")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS bookkeeper_transactions (
               tx_id text NOT NULL,
               scope text NOT NULL,
               kind text NOT NULL,
               identity_id text NOT NULL DEFAULT '',
               description text NOT NULL DEFAULT '',
               amount numeric(14,2) NOT NULL,
               tx_date date NOT NULL,
               client_id text NOT NULL DEFAULT '',
               client_name text NOT NULL DEFAULT '',
               created_at text NOT NULL DEFAULT '',
               PRIMARY KEY (scope, tx_id)
           ) PARTITION BY HASH (scope)""")
    for k in range(partitions):
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS bookkeeper_transactions_p{k} "  # nosec B608 — k is an int
            f"PARTITION OF bookkeeper_transactions "
            f"FOR VALUES WITH (MODULUS {partitions}, REMAINDER {k})")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bk_tx_scope_date "
        "ON bookkeeper_transactions (scope, tx_date DESC)")


def _tx(row: tuple) -> Transaction:
    return Transaction(tx_id=row[0], kind=row[1], identity_id=row[2], description=row[3],
                       amount=float(row[4]), tx_date=row[5].isoformat(),
                       client_id=row[6], client_name=row[7], created_at=row[8])


_TX_COLS = ("tx_id, kind, identity_id, description, amount, tx_date, client_id, client_name, "
            "created_at")


class PgBookkeeperStore:
    """Postgres-backed bookkeeper store, scoped to one tenant. Sync; autocommit."""

    def __init__(self, dsn: str, scope: str, *, partitions: int = 8) -> None:
        self._scope = scope
        self._conn = psycopg.connect(dsn, autocommit=True)
        _ensure_schema(self._conn, partitions)

    def close(self) -> None:
        self._conn.close()

    # clients
    def upsert_client(self, name: str) -> Client:
        row = self._conn.execute(
            "SELECT client_id, name FROM bookkeeper_clients WHERE scope = %s AND lower(name) = lower(%s)",
            (self._scope, name)).fetchone()
        if row:
            return Client(client_id=row[0], name=row[1])
        cid = uuid.uuid4().hex[:12]
        self._conn.execute(
            "INSERT INTO bookkeeper_clients (scope, client_id, name) VALUES (%s, %s, %s)",
            (self._scope, cid, name))
        return Client(client_id=cid, name=name)

    def list_clients(self) -> list[Client]:
        rows = self._conn.execute(
            "SELECT client_id, name FROM bookkeeper_clients WHERE scope = %s ORDER BY name",
            (self._scope,)).fetchall()
        return [Client(client_id=r[0], name=r[1]) for r in rows]

    # transactions
    def add(self, tx: Transaction) -> None:
        self._conn.execute(
            f"INSERT INTO bookkeeper_transactions (scope, {_TX_COLS}) "  # nosec B608 — fixed columns
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (self._scope, tx.tx_id, tx.kind, tx.identity_id, tx.description, tx.amount,
             tx.tx_date, tx.client_id, tx.client_name, tx.created_at))

    def get(self, tx_id: str) -> Optional[Transaction]:
        row = self._conn.execute(
            f"SELECT {_TX_COLS} FROM bookkeeper_transactions WHERE scope = %s AND tx_id = %s",  # nosec B608
            (self._scope, tx_id)).fetchone()
        return _tx(row) if row else None

    def remove(self, tx_id: str) -> None:
        self._conn.execute(
            "DELETE FROM bookkeeper_transactions WHERE scope = %s AND tx_id = %s",
            (self._scope, tx_id))

    def list(self, *, kind: Optional[str] = None, identity_id: Optional[str] = None,
             date_from: Optional[str] = None, date_to: Optional[str] = None) -> list[Transaction]:
        sql = f"SELECT {_TX_COLS} FROM bookkeeper_transactions WHERE scope = %s"  # nosec B608
        params: list = [self._scope]
        if kind is not None:
            sql += " AND kind = %s"
            params.append(kind)
        if identity_id is not None:
            sql += " AND identity_id = %s"
            params.append(identity_id)
        if date_from is not None:
            sql += " AND tx_date >= %s"
            params.append(date_from)
        if date_to is not None:
            sql += " AND tx_date <= %s"
            params.append(date_to)
        sql += " ORDER BY tx_date DESC, created_at DESC"
        rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [_tx(r) for r in rows]
