"""``PgCompanyStore`` — the Postgres adapter for the company port.

Sync psycopg, autocommit, every query filtered by the scope — the shape of
``bookkeeper/stores/postgres.py``. Two deliberate divergences from that sibling, and both are
about writing to a table that ALREADY EXISTS with rows in it:

* **the scope column is named ``tenant_id``, not ``scope``**, and the table is
  ``tenant_companies``. This vertical did not invent its storage: it inherited the host's
  ``PgTenantCompanyStore`` table, live since 2026-09-02. The host still READS that table to
  build the "empresa em foco" block it puts in the persona's context
  (``cogno_host/company_focus.py``), so a fresh ``company_*`` table would have left the writes
  here and the reads there, looking at different rows. Same table, same column names, same
  primary key — the move changes who writes, not where.
* **no HASH partitioning.** The live table is not partitioned and ``CREATE TABLE IF NOT
  EXISTS`` is a no-op against it, so declaring a partitioned twin here would be a statement
  that never runs and a claim nobody can check. Companies are low-volume reference data — the
  same reason ``bookkeeper_clients`` is unpartitioned while ``bookkeeper_transactions`` is not.

The host points the vertical at this store by setting ``COGNO_COMPANY_DSN`` +
``COGNO_COMPANY_SCOPE`` (see ``server.py``).
"""

from __future__ import annotations

import time
from typing import Optional

import psycopg
from psycopg.types.json import Jsonb

from cogno_praxis.company.store import Company

# Same order as the SELECT mapper below, so ``_row``'s indices can be read against it. A class
# constant (a literal column list) — no caller can reach it, and every VALUE travels as %s.
_COLS = ("company_id, name, cnpj, segment, visual_identity, created_by_user_id, "
         "created_at, updated_at")


def _ensure_schema(conn: "psycopg.Connection") -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tenant_companies (
               tenant_id text NOT NULL,
               company_id text NOT NULL,
               name text NOT NULL DEFAULT '',
               cnpj text NOT NULL DEFAULT '',
               segment text NOT NULL DEFAULT '',
               visual_identity jsonb NOT NULL DEFAULT '{}',
               created_by_user_id text NOT NULL DEFAULT '',
               created_at double precision NOT NULL DEFAULT 0.0,
               updated_at double precision NOT NULL DEFAULT 0.0,
               PRIMARY KEY (tenant_id, company_id))""")
    # Back-compat, and NOT optional: the statement above is `IF NOT EXISTS`, and the live table
    # already exists — created 2026-09-02 with eight columns and no `cnpj`. Adding the column
    # only to the CREATE is a NO-OP on every box that has already booted once, and the first
    # INSERT naming it then raises `UndefinedColumn` on EVERY turn. DEFAULT '' keeps every
    # existing row exactly as it is: no CNPJ on file reads as "not supplied", which is the
    # value this vertical itself writes.
    conn.execute(
        "ALTER TABLE tenant_companies ADD COLUMN IF NOT EXISTS cnpj text NOT NULL DEFAULT ''")


def _company(row: tuple) -> Company:
    return Company(company_id=row[0], name=row[1], cnpj=row[2], segment=row[3],
                   visual_identity=row[4] or {}, created_by_user_id=row[5],
                   created_at=float(row[6]), updated_at=float(row[7]))


class PgCompanyStore:
    """Postgres-backed company store, scoped to one tenant. Sync; autocommit."""

    def __init__(self, dsn: str, scope: str) -> None:
        if not (scope or "").strip():
            # `tenant_id` is the first half of the row's PRIMARY KEY and the whole of its
            # isolation. A blank one files every tenant's companies in one bucket that no
            # tenant-scoped read ever returns — a data leak and a lost record at once.
            raise ValueError("PgCompanyStore requires a non-empty scope (the tenant id)")
        self._scope = scope
        self._conn = psycopg.connect(dsn, autocommit=True)
        _ensure_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def upsert(self, company: Company) -> Company:
        now = time.time()
        created = company.created_at or now
        row = self._conn.execute(
            """INSERT INTO tenant_companies (tenant_id, company_id, name, cnpj, segment,
                   visual_identity, created_by_user_id, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (tenant_id, company_id) DO UPDATE SET
                   name = EXCLUDED.name, cnpj = EXCLUDED.cnpj,
                   segment = EXCLUDED.segment,
                   visual_identity = EXCLUDED.visual_identity,
                   updated_at = EXCLUDED.updated_at
               RETURNING company_id, name, cnpj, segment, visual_identity,
                         created_by_user_id, created_at, updated_at""",
            (self._scope, company.company_id, company.name, company.cnpj, company.segment,
             Jsonb(company.visual_identity), company.created_by_user_id, created, now)
        ).fetchone()
        assert row is not None
        return _company(row)

    def get(self, company_id: str) -> Optional[Company]:
        row = self._conn.execute(
            f"SELECT {_COLS} FROM tenant_companies "                      # nosec B608
            "WHERE tenant_id = %s AND company_id = %s",
            (self._scope, company_id)).fetchone()
        return _company(row) if row else None

    def list_companies(self) -> "list[Company]":
        rows = self._conn.execute(
            f"SELECT {_COLS} FROM tenant_companies WHERE tenant_id = %s "  # nosec B608
            "ORDER BY company_id", (self._scope,)).fetchall()
        return [_company(r) for r in rows]

    def delete(self, company_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM tenant_companies WHERE tenant_id = %s AND company_id = %s",
            (self._scope, company_id))
        return cur.rowcount > 0
