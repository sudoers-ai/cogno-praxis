"""Integration: PgCompanyStore against a real Postgres.

Needs no DSN: the suite aims at ``cogno_praxis_test`` on the local server by itself and
auto-skips when nothing is listening there (see ``conftest.resolve_test_dsn``).
``COGNO_TEST_PG_DSN`` overrides, and a database whose name does not say "test" is refused at
collection — this test ``DROP TABLE tenant_companies``.

That table name is the reason this file is more careful than its siblings: it is NOT a table
this vertical invented. ``tenant_companies`` is the host's, live since 2026-09-02, and the host
still READS it to build the "empresa em foco" block. A test pointed at a real deployment would
drop a tenant's registered companies. The collection guard is what stands between those two
facts, and this docstring says so out loud rather than trusting the reader to know.

Proves the registration round-trips through Postgres, that the derived key makes a second
registration an UPDATE rather than a second row, and that the scope isolates tenants.
"""

from __future__ import annotations

import pytest

psycopg = pytest.importorskip("psycopg")

from tests.integration.conftest import resolve_test_dsn  # noqa: E402

DSN = resolve_test_dsn()      # COGNO_TEST_PG_DSN, else `cogno_praxis_test` on the local server
pytestmark = pytest.mark.skipif(
    not DSN, reason="no Postgres reachable (see tests/integration/conftest.py)")

from cogno_praxis.company import CompanyError, CompanyService              # noqa: E402
from cogno_praxis.company.stores.postgres import PgCompanyStore            # noqa: E402

_CNPJ_OK = "11.222.333/0001-81"
_CNPJ_BAD = "11.222.333/0001-99"


def _fresh_store(scope: str) -> PgCompanyStore:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS tenant_companies CASCADE")
    return PgCompanyStore(DSN, scope)


def test_a_registration_round_trips_through_postgres():
    svc = CompanyService(_fresh_store("acme"))
    row = svc.register("Padaria São João", cnpj=_CNPJ_OK, visual_identity="azul",
                       guidelines="tom informal", identity_id="u1")
    stored = svc.get(row.company_id)
    assert stored is not None
    assert stored.name == "Padaria São João"
    assert stored.cnpj == "11222333000181"
    assert stored.visual_identity == {"visual_identity": "azul", "guidelines": "tom informal"}
    assert stored.created_by_user_id == "u1"


def test_the_derived_key_makes_a_second_registration_an_UPDATE():
    svc = CompanyService(_fresh_store("acme"))
    svc.register("Padaria São João", visual_identity="azul")
    svc.register("padaria sao joao", visual_identity="verde")
    rows = svc.list_companies()
    assert len(rows) == 1
    assert rows[0].visual_identity == {"visual_identity": "verde"}


def test_created_at_and_author_survive_an_update():
    """`ON CONFLICT DO UPDATE` deliberately leaves `created_at`/`created_by_user_id` alone: a
    correction is not a new registration by a new author."""
    store = _fresh_store("acme")
    first = CompanyService(store).register("Acme", identity_id="u1")
    again = CompanyService(store).register("Acme", identity_id="u2")
    assert again.created_by_user_id == "u1"
    assert again.created_at == first.created_at
    assert again.updated_at >= first.updated_at


def test_the_scope_isolates_tenants():
    a = CompanyService(_fresh_store("acme"))
    b = CompanyService(PgCompanyStore(DSN, "initech"))
    a.register("Acme")
    b.register("Initech")
    assert [c.name for c in a.list_companies()] == ["Acme"]
    assert [c.name for c in b.list_companies()] == ["Initech"]


def test_a_refused_registration_never_reaches_the_table():
    svc = CompanyService(_fresh_store("acme"))
    with pytest.raises(CompanyError):
        svc.register("Acme", cnpj=_CNPJ_BAD)
    assert svc.list_companies() == []


def test_a_blank_scope_is_refused_before_a_connection_is_opened():
    """`tenant_id` is the first half of the PRIMARY KEY and the whole of the row's isolation."""
    with pytest.raises(ValueError, match="scope"):
        PgCompanyStore(DSN, "  ")


def test_the_late_cnpj_column_is_added_to_a_table_that_predates_it():
    """The live table was created with eight columns and no `cnpj`. `CREATE TABLE IF NOT EXISTS`
    is a no-op against it, so the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is what keeps the
    first INSERT from raising `UndefinedColumn` on every turn."""
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS tenant_companies CASCADE")
        c.execute("""CREATE TABLE tenant_companies (
                         tenant_id text NOT NULL, company_id text NOT NULL,
                         name text NOT NULL DEFAULT '', segment text NOT NULL DEFAULT '',
                         visual_identity jsonb NOT NULL DEFAULT '{}',
                         created_by_user_id text NOT NULL DEFAULT '',
                         created_at double precision NOT NULL DEFAULT 0.0,
                         updated_at double precision NOT NULL DEFAULT 0.0,
                         PRIMARY KEY (tenant_id, company_id))""")
    svc = CompanyService(PgCompanyStore(DSN, "acme"))          # runs the migration
    assert svc.register("Acme", cnpj=_CNPJ_OK).cnpj == "11222333000181"
