"""Integration: the Postgres AppointmentStore against a real Postgres.

Set ``COGNO_TEST_PG_DSN`` (e.g. ``postgresql://postgres:pw@localhost:55432/cogno_praxis_test``)
to run; auto-skips otherwise. These tests ``DROP TABLE``, so the database name must contain
"test" or ``conftest.py`` aborts the run — this example used to end in ``/cogno``, which is
the demo box's LIVE database. Proves the full scheduler flow round-trips through Postgres,
the ``appointments`` table is HASH(scope)-partitioned, and scope isolates tenants.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import date

import pytest

psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get("COGNO_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="set COGNO_TEST_PG_DSN to run")

from cogno_praxis.scheduler import Host, SchedulerService            # noqa: E402
from cogno_praxis.scheduler.service import SchedulerError            # noqa: E402
from cogno_praxis.scheduler.store import Appointment                 # noqa: E402
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


def test_sync_hosts_reconciles_catalog():
    # A professional removed from the tenant catalog must leave the persisted catalog too —
    # upsert-only seeding left ghost doctors bookable forever. Appointments keep their rows.
    store = _drop_and_store("clinic")
    store.add_host(Host("ghost", "Dr. Ghost", "Cardio"))
    store.add_host(Host("dr_real", "Dr. Real", "GP"))

    store.sync_hosts([Host("dr_real", "Dr. Real", "Endócrino"), Host("dr_new", "Dr. New", "GP")])
    hosts = {h.host_id: h for h in store.list_hosts()}
    assert set(hosts) == {"dr_real", "dr_new"}              # ghost gone, new added
    assert hosts["dr_real"].role == "Endócrino"             # kept host still upserted

    store.sync_hosts([])                                    # empty catalog → none bookable
    assert store.list_hosts() == []
    store.close()


def test_purge_identity_removes_host_and_guest_rows():
    # Parent parity (delete_identity → DELETE schedule.appointments WHERE host OR guest):
    # deleting an identity must take its appointments (both sides) and its catalog entry —
    # orphans otherwise resurface when the same channel id is ever re-registered.
    store = _drop_and_store("clinic")
    store.add_host(Host("dr_gone", "Dr. Gone", "GP"))
    store.add_host(Host("dr_stays", "Dr. Stays", "GP"))
    svc = SchedulerService(store, today=lambda: _TODAY)
    svc.book("dr_gone", "2026-07-01", "09:00", "Ana", guest_id="ana_id")
    svc.book("dr_stays", "2026-07-01", "09:00", "Gone Person", guest_id="dr_gone")
    svc.book("dr_stays", "2026-07-01", "10:00", "Bia", guest_id="bia_id")

    removed = store.purge_identity("dr_gone")
    assert removed == 2                                     # host-side + guest-side rows
    assert {h.host_id for h in store.list_hosts()} == {"dr_stays"}
    left = svc.list_appointments(host_id="dr_stays")
    assert [a.guest_id for a in left] == ["bia_id"]         # unrelated booking untouched
    assert store.purge_identity("") == 0
    store.close()


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


def test_concurrent_booking_of_one_slot_yields_exactly_one_appointment():
    """The check-then-insert race, closed by ``ux_appt_active_slot``.

    ``book()`` reads availability and then inserts; two turns of the SAME tenant run
    concurrently (host locks are per-session, and the MCP tools are threadpool-dispatched),
    so both can clear the check. Only the partial unique index makes the loser lose — and it
    must lose as a domain SchedulerError carrying alternatives, not a psycopg traceback."""
    store = _drop_and_store("clinic")
    store.add_host(Host("h1", "Dr. House", auto_confirm=True))

    booked, refused = [], []
    barrier = threading.Barrier(2)

    def _book(name: str, guest: str) -> None:
        s = PgAppointmentStore(DSN, "clinic")          # an independent connection per "turn"
        svc = SchedulerService(s, today=lambda: _TODAY)
        barrier.wait()                                  # maximise the overlap
        try:
            booked.append(svc.book("h1", "2026-07-01", "10:00", name, guest_id=guest))
        except SchedulerError as exc:
            refused.append(str(exc))
        finally:
            s.close()

    threads = [threading.Thread(target=_book, args=a)
               for a in (("Ana", "g_ana"), ("Bob", "g_bob"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(booked) == 1 and len(refused) == 1
    assert "already booked" in refused[0] and "Free slots" in refused[0]
    with psycopg.connect(DSN) as c:
        active = c.execute(
            "SELECT count(*) FROM appointments WHERE scope='clinic' AND status IN "
            "('PENDING','CONFIRMED') AND date='2026-07-01' AND time='10:00'").fetchone()[0]
    assert active == 1, "double booking survived the constraint"
    store.close()


def test_slot_constraint_still_allows_rebook_and_history():
    """The index is PARTIAL for a reason: only ACTIVE rows hold a slot. Re-booking the same
    slot after a cancel, and stacking CANCELED history on it, must both stay legal."""
    store = _drop_and_store("clinic")
    store.add_host(Host("h1", "Dr. House", auto_confirm=True))
    svc = SchedulerService(store, today=lambda: _TODAY)

    first = svc.book("h1", "2026-07-01", "10:00", "Ana", guest_id="g_ana")
    # same client re-issuing the identical booking is idempotent (EGO↔judge retry safety)
    assert svc.book("h1", "2026-07-01", "10:00", "Ana",
                    guest_id="g_ana").appointment_id == first.appointment_id

    svc.cancel(first.appointment_id, reason="freed")
    second = svc.book("h1", "2026-07-01", "10:00", "Bob", guest_id="g_bob")
    assert second.appointment_id != first.appointment_id

    svc.cancel(second.appointment_id, reason="freed again")
    third = svc.book("h1", "2026-07-01", "10:00", "Carol", guest_id="g_carol")
    with psycopg.connect(DSN) as c:
        rows = c.execute(
            "SELECT count(*) FROM appointments WHERE scope='clinic' AND date='2026-07-01' "
            "AND time='10:00'").fetchone()[0]
    assert rows == 3 and third.status == "CONFIRMED"   # two CANCELED + one live
    store.close()


def test_preexisting_duplicates_degrade_instead_of_killing_the_store(caplog):
    """Creating the unique index FAILS on a table that already holds conflicting active rows.
    That must not take the scheduler down at construction: it logs and falls back to the
    service-level pre-check (the pre-existing guard)."""
    store = _drop_and_store("clinic")
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("DROP INDEX IF EXISTS ux_appt_active_slot_v1")
        for aid in ("dup1", "dup2"):
            c.execute("INSERT INTO appointments (appointment_id, scope, host_id, date, time, "
                      "with_name, status) VALUES (%s,'clinic','h1','2026-07-01','10:00','X',"
                      "'CONFIRMED')", (aid,))
    with caplog.at_level(logging.WARNING, logger="cogno_praxis.scheduler.stores.postgres"):
        again = PgAppointmentStore(DSN, "clinic")       # must NOT raise
    assert "event=slot_uniqueness_unavailable" in " ".join(r.getMessage()
                                                           for r in caplog.records)
    again.close()
    store.close()


def _hidden_from_scan(store, appointment_id: str):
    """Make a row invisible to the service's pre-checks while it IS in the table — i.e. it
    appeared between the check and the write. That is the race, deterministically."""
    real = store.list
    store.list = lambda **kw: [a for a in real(**kw) if a.appointment_id != appointment_id]


def test_every_write_path_reports_a_slot_race_in_domain_terms():
    """The unique index guards INSERT *and* UPDATE, so ``book`` is not the only path that can
    lose a race. reschedule / update_status / block_schedule must each answer with a
    SchedulerError the model can act on — never a raw psycopg UniqueViolation."""
    store = _drop_and_store("clinic")
    store.add_host(Host("h1", "Dr. House", auto_confirm=True))
    svc = SchedulerService(store, today=lambda: _TODAY)

    # reschedule onto a slot occupied after its own pre-check
    mine = svc.book("h1", "2026-07-01", "09:00", "Ana", guest_id="g_ana")
    store.add(Appointment(appointment_id="rival1", host_id="h1", date="2026-07-01",
                          time="10:00", with_name="Bob", status="CONFIRMED"))
    _hidden_from_scan(store, "rival1")
    with pytest.raises(SchedulerError, match="already booked"):
        svc.reschedule(mine.appointment_id, "2026-07-01", "10:00")

    # update_status reviving a CANCELED appointment whose slot was retaken
    store = _drop_and_store("clinic")
    store.add_host(Host("h1", "Dr. House", auto_confirm=True))
    svc = SchedulerService(store, today=lambda: _TODAY)
    old = svc.book("h1", "2026-07-02", "09:00", "Ana", guest_id="g_ana")
    svc.cancel(old.appointment_id, reason="freed")
    store.add(Appointment(appointment_id="rival2", host_id="h1", date="2026-07-02",
                          time="09:00", with_name="Carol", status="CONFIRMED"))
    with pytest.raises(SchedulerError, match="now booked by someone else"):
        svc.update_status(old.appointment_id, "CONFIRMED")

    # block_schedule racing a client booking
    store = _drop_and_store("clinic")
    store.add_host(Host("h1", "Dr. House", auto_confirm=True))
    svc = SchedulerService(store, today=lambda: _TODAY)
    store.add(Appointment(appointment_id="rival3", host_id="h1", date="2026-07-03",
                          time="14:00", with_name="Cliente", status="CONFIRMED"))
    _hidden_from_scan(store, "rival3")
    with pytest.raises(SchedulerError, match="just booked by a client"):
        svc.block_schedule("h1", "2026-07-03", start_time="14:00")
    store.close()


def test_primary_key_collision_is_not_reported_as_a_taken_slot():
    """Only the slot index means "slot taken". An appointment_id collision (the other unique
    constraint) must surface as itself — mislabelling it would make the caller hunt for a
    conflicting appointment, find none, and offer the contested slot as free."""
    store = _drop_and_store("clinic")
    store.add_host(Host("h1", "Dr. House", auto_confirm=True))
    store.add(Appointment(appointment_id="dup", host_id="h1", date="2026-07-01", time="09:00",
                          with_name="Ana", status="CONFIRMED"))
    with pytest.raises(psycopg.errors.UniqueViolation):        # NOT SlotTakenError
        store.add(Appointment(appointment_id="dup", host_id="h1", date="2026-07-01",
                              time="11:00", with_name="Bob", status="CONFIRMED"))
    store.close()


# ── a varredura, através do banco de verdade ──────────────────────────────────────────
def _swept_past_row_pg(scope: str):
    """Uma consulta CONFIRMED de ontem, em Postgres, depois de UMA listagem.

    A listagem é o ponto: `_sweep_expired` terminaliza as linhas passadas pela classe
    faturável em toda leitura, então uma CONFIRMED do passado vira COMPLETED sem ninguém
    decidir nada — e ela ESCREVE no banco, o que é justamente o que só a integração prova."""
    from datetime import timedelta

    store = _drop_and_store(scope)
    store.add_host(Host("dr_silva", "Dr. Silva", "GP"))
    store.add(Appointment(appointment_id="ontem1", host_id="dr_silva", host_name="Dr. Silva",
                          date=(_TODAY - timedelta(days=1)).isoformat(), time="09:00",
                          with_name="Beatriz", status="CONFIRMED"))
    svc = SchedulerService(store, today=lambda: _TODAY)
    svc.list_appointments(host_id="dr_silva")
    assert store.get("ontem1").status == "COMPLETED", "premissa: a varredura conclui sozinha"
    return svc, store


def test_the_automatic_completion_is_written_to_postgres_not_just_in_memory():
    """A varredura persiste — não é artefato da store de memória.

    Vale medir por aqui porque esta distinção já mordeu neste mesmo arquivo: a revivência com
    slot retomado passava em memória porque só o Postgres levanta `SlotTakenError`. Uma regra
    que a store default não cumpre não é uma regra; uma escrita que só a de memória faz não é
    uma escrita."""
    _svc, store = _swept_past_row_pg("sweep_writes")
    with psycopg.connect(DSN) as c:
        row = c.execute("SELECT status FROM appointments WHERE scope=%s AND appointment_id=%s",
                        ("sweep_writes", "ontem1")).fetchone()
    assert row and row[0] == "COMPLETED", "a conclusão automática não chegou ao banco"


def test_undo_then_cancel_round_trips_through_postgres():
    """O caminho do não-comparecimento, com as duas chamadas coladas — a ordem que funciona."""
    svc, store = _swept_past_row_pg("undo_ok")
    svc.update_status("ontem1", "CONFIRMED")
    svc.cancel("ontem1", reason="no-show")
    with psycopg.connect(DSN) as c:
        row = c.execute("SELECT status, cancel_reason FROM appointments "
                        "WHERE scope=%s AND appointment_id=%s", ("undo_ok", "ontem1")).fetchone()
    assert row == ("CANCELED", "no-show")


@pytest.mark.xfail(strict=True, reason=(
    "MESMO DEFEITO ABERTO do unitário `test_the_sweep_undoes_the_undo`, medido aqui contra "
    "Postgres para provar que não é artefato da store de memória: a varredura recompleta a "
    "linha na listagem seguinte e o cancelamento volta a ser recusado."))
def test_the_sweep_undoes_the_undo_in_postgres_too():
    """Desfazer, algo lista, cancelar — a ordem que uma conversa realmente produz."""
    svc, store = _swept_past_row_pg("undo_race")
    svc.update_status("ontem1", "CONFIRMED")
    svc.list_appointments(host_id="dr_silva")
    svc.cancel("ontem1", reason="no-show")
    # O RESULTADO, não uma rota até ele — ver a nota no unitário equivalente.
    assert store.get("ontem1").status == "CANCELED", "o não-comparecimento não ficou registrado"
