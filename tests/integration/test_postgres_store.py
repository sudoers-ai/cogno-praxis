"""Integration: the Postgres AppointmentStore against a real Postgres.

Set ``COGNO_TEST_PG_DSN`` (e.g. ``postgresql://postgres:test@localhost:55432/cogno``) to
run; auto-skips otherwise. Proves the full scheduler flow round-trips through Postgres,
the ``appointments`` table is HASH(scope)-partitioned, and scope isolates tenants.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get("COGNO_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set COGNO_TEST_PG_DSN to run")

from cogno_praxis.scheduler import Host, SchedulerService            # noqa: E402
from cogno_praxis.scheduler.stores.postgres import PgAppointmentStore  # noqa: E402

_TODAY = date(2026, 6, 30)   # Tuesday → 2026-07-01 is a working Wednesday


def _drop_and_store(scope: str) -> PgAppointmentStore:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS appointments CASCADE")
        c.execute("DROP TABLE IF EXISTS schedule_hosts CASCADE")
    return PgAppointmentStore(DSN, scope)


def test_full_scheduler_flow_through_postgres():
    store = _drop_and_store("acme")
    store.add_host(Host("dr_silva", "Dr. Silva", "GP"))
    svc = SchedulerService(store, today=lambda: _TODAY)

    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    assert appt.status == "CONFIRMED"                       # dr_silva auto_confirms
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")

    moved = svc.reschedule(appt.appointment_id, "2026-07-01", "11:00")
    assert moved.time == "11:00" and moved.appointment_id == appt.appointment_id

    svc.cancel(appt.appointment_id)
    assert "11:00" in svc.check_availability("dr_silva", "2026-07-01")
    store.close()


def test_partitioned_by_hash_scope_and_isolated():
    s1 = _drop_and_store("t1")
    s1.add_host(Host("h", "H"))
    s2 = PgAppointmentStore(DSN, "t2")          # second tenant, same tables
    s2.add_host(Host("h", "H"))

    with psycopg.connect(DSN) as c:
        n = c.execute(
            "SELECT count(*) FROM pg_inherits i JOIN pg_class p ON i.inhparent = p.oid "
            "WHERE p.relname = 'appointments'").fetchone()[0]
        assert n == 8                            # 8 HASH(scope) partitions

    svc1 = SchedulerService(s1, today=lambda: _TODAY)
    svc1.book("h", "2026-07-01", "09:00", "Ana")
    assert len(s1.list()) == 1 and len(s2.list()) == 0   # t2 never sees t1's rows
    s1.close()
    s2.close()


def test_two_sided_visibility_survives_postgres():
    # The doctor-sees-the-guest's-booking fix, end-to-end vs real Postgres: a guest books with a
    # professional (auto_confirm off → PENDING); the SAME row must be found by BOTH the doctor
    # (host_id) and the guest (guest_id), and guest_id must persist on the row.
    store = _drop_and_store("clinic")
    store.add_host(Host("dr_vini", "Dr. Vinicius Vale", "Cardio", auto_confirm=False))
    svc = SchedulerService(store, today=lambda: _TODAY)

    appt = svc.book("dr_vini", "2026-07-01", "09:00", "Ana",
                    guest_id="ana_id", host_name="Dr. Vinicius Vale")
    assert appt.status == "PENDING"

    # EMPLOYEE view (host_id) sees the guest's PENDING booking
    doc = svc.list_appointments(identity_id="dr_vini", role="EMPLOYEE")
    assert [a.appointment_id for a in doc] == [appt.appointment_id]
    assert doc[0].guest_id == "ana_id" and doc[0].host_name == "Dr. Vinicius Vale"

    # GUEST view (guest_id) sees the same row; a different guest sees nothing
    assert [a.appointment_id for a in svc.list_appointments(identity_id="ana_id", role="GUEST")] \
        == [appt.appointment_id]
    assert svc.list_appointments(identity_id="bob_id", role="GUEST") == []

    # SUPERVISOR sees all; the guest_id column is really persisted (raw SQL)
    assert len(svc.list_appointments(identity_id="x", role="SUPERVISOR")) == 1
    with psycopg.connect(DSN) as c:
        row = c.execute("SELECT guest_id, host_name FROM appointments "
                        "WHERE scope='clinic' AND appointment_id=%s",
                        (appt.appointment_id,)).fetchone()
    assert row == ("ana_id", "Dr. Vinicius Vale")
    store.close()
