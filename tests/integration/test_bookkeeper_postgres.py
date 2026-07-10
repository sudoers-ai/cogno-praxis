"""Integration: PgBookkeeperStore against a real Postgres.

Set ``COGNO_TEST_PG_DSN`` (e.g. ``postgresql://postgres:test@localhost:55432/cogno``) to run;
auto-skips otherwise. Proves the financial flow round-trips through Postgres, the transactions
table is HASH(scope)-partitioned, and scope isolates tenants.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get("COGNO_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set COGNO_TEST_PG_DSN to run")

from cogno_praxis.bookkeeper import BookkeeperService                    # noqa: E402
from cogno_praxis.bookkeeper.stores.postgres import PgBookkeeperStore    # noqa: E402

_TODAY = date(2026, 7, 10)


def _fresh_store(scope: str) -> PgBookkeeperStore:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS bookkeeper_transactions CASCADE")
        c.execute("DROP TABLE IF EXISTS bookkeeper_clients CASCADE")
    return PgBookkeeperStore(DSN, scope)


def test_full_bookkeeper_flow_through_postgres():
    store = _fresh_store("acme")
    svc = BookkeeperService(store, today=lambda: _TODAY)

    svc.add_income("corte", 50, "emp-1", client_name="João")
    svc.add_outcome("luz", 80, "emp-1")
    svc.add_income("barba", 30, "emp-1", client_name="João")

    s = svc.get_summary("emp-1", "EMPLOYEE")
    assert s["total_income"] == 80.0 and s["total_outcome"] == 80.0 and s["net"] == 0.0
    assert [c["name"] for c in svc.list_clients()] == ["João"]     # upsert, not duplicated

    # remove the most recent income matching "barba"
    removed = svc.remove_by_search("barba", "emp-1")
    assert removed is not None and removed["amount"] == 30.0
    assert svc.get_summary("emp-1", "EMPLOYEE")["total_income"] == 50.0

    store.close()


def test_scope_isolates_tenants():
    a = _fresh_store("tenant-a")
    b = PgBookkeeperStore(DSN, "tenant-b")            # same tables, different scope
    BookkeeperService(a, today=lambda: _TODAY).add_income("x", 100, "e1")
    # tenant-b sees nothing tenant-a recorded
    assert BookkeeperService(b, today=lambda: _TODAY).get_summary("e1", "ADMIN")["total_income"] == 0.0
    a.close()
    b.close()
