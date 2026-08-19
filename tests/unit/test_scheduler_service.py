"""Unit tests for the scheduler domain logic (service + store), no MCP."""

from datetime import date, timedelta

import pytest

from cogno_praxis.scheduler import (
    Host,
    InMemoryAppointmentStore,
    SchedulerError,
    SchedulerService,
)
from cogno_praxis.scheduler.store import CANCELED, COMPLETED, CONFIRMED, PENDING

# A fixed "today" so the "start from tomorrow" rule is deterministic; the test dates
# below (2026-07-xx) are comfortably in the future relative to it.
_TODAY = date(2026, 6, 30)


def _svc():
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    return SchedulerService(store, today=lambda: _TODAY)


def test_list_hosts():
    svc = _svc()
    assert [h.host_id for h in svc.list_hosts()] == ["dr_silva"]


def test_availability_all_slots_when_empty():
    svc = _svc()
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert free == list(svc._slots)


def test_availability_unknown_host_raises():
    with pytest.raises(SchedulerError, match="unknown host"):
        _svc().check_availability("ghost", "2026-07-01")


def test_book_then_slot_disappears():
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    assert appt.status == CONFIRMED          # dr_silva auto_confirms (default)
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")


def _fill_day(svc, host_id, day):
    """Book every free slot on ``day`` so the day is full."""
    for slot in list(svc.check_availability(host_id, day)):
        svc.book(host_id, day, slot, "filler")


def test_next_available_day_returns_next_working_day_when_full():
    # A full Wednesday → the overflow is the next working day (Thursday), fully open.
    svc = _svc()
    _fill_day(svc, "dr_silva", "2026-07-01")            # Wed, now full
    assert svc.check_availability("dr_silva", "2026-07-01") == []
    nxt = svc.next_available_day("dr_silva", "2026-07-01")
    assert nxt is not None
    ndate, nslots = nxt
    assert ndate == "2026-07-02"                        # Thu
    assert nslots == list(svc._slots)                   # untouched → all slots free


def test_next_available_day_skips_the_weekend():
    # A full Friday → overflow jumps the Sat/Sun and lands on Monday.
    svc = _svc()
    _fill_day(svc, "dr_silva", "2026-07-03")            # Fri, now full
    nxt = svc.next_available_day("dr_silva", "2026-07-03")
    assert nxt is not None and nxt[0] == "2026-07-06"   # Mon (07-04/07-05 are the weekend)


def test_next_available_day_returns_partial_day_when_partially_booked():
    # The next day is itself partly booked → only its remaining slots are offered.
    svc = _svc()
    _fill_day(svc, "dr_silva", "2026-07-01")
    svc.book("dr_silva", "2026-07-02", "09:00", "early bird")
    ndate, nslots = svc.next_available_day("dr_silva", "2026-07-01")
    assert ndate == "2026-07-02" and "09:00" not in nslots and "10:00" in nslots


def test_next_available_day_none_when_horizon_is_all_booked():
    # Nothing opens within the horizon → None (the tool then says so honestly).
    svc = _svc()
    for offset in range(1, 40):                         # fill everything for the next ~6 weeks
        d = (date(2026, 7, 1) + __import__("datetime").timedelta(days=offset)).isoformat()
        try:
            _fill_day(svc, "dr_silva", d)
        except SchedulerError:
            pass                                         # weekend/holiday → nothing to fill
    assert svc.next_available_day("dr_silva", "2026-07-01", horizon_days=5) is None


def test_next_available_day_unknown_host_raises():
    with pytest.raises(SchedulerError, match="unknown host"):
        _svc().next_available_day("ghost", "2026-07-01")


def test_book_resolves_a_name_slug_host_id():
    # a small model invents 'dr_jose_luiz_manzoli' instead of the catalog id (a numeric user_id);
    # fuzzy resolution matches it by normalized name so the booking still lands on the real host
    store = InMemoryAppointmentStore()
    store.hosts["8443"] = Host("8443", "Dr. José Luiz Manzoli", "Endócrino")
    svc = SchedulerService(store, today=lambda: _TODAY)
    appt = svc.book("dr_jose_luiz_manzoli", "2026-07-01", "09:00", "Ana")
    assert appt.host_id == "8443"            # resolved to the real catalog id
    # and availability accepts the slug too
    assert "09:00" not in svc.check_availability("dr_jose_luiz_manzoli", "2026-07-01")
    # a genuinely unknown host still errors
    with pytest.raises(SchedulerError, match="unknown host"):
        svc.book("ghost_doctor", "2026-07-01", "10:00", "Ana")


def test_book_resolves_a_single_specialty():
    # "marca com o cardiologista" is valid when exactly one host has that specialty (role).
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Vinicius Vale", "Cardiologista")
    store.hosts["dr_m"] = Host("dr_m", "Dr. Manzoli", "Endócrino")
    svc = SchedulerService(store, today=lambda: _TODAY)
    appt = svc.book("cardiologista", "2026-07-01", "09:00", "Ana")
    assert appt.host_id == "dr_silva"        # the one cardiologist
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")  # slot now taken


def test_ambiguous_specialty_stays_unresolved():
    # two cardiologists → the specialty is ambiguous; do NOT guess (the caller lists + user picks).
    store = InMemoryAppointmentStore()
    store.hosts["dr_a"] = Host("dr_a", "Dr. A", "Cardiologista")
    store.hosts["dr_b"] = Host("dr_b", "Dr. B", "Cardiologista")
    svc = SchedulerService(store, today=lambda: _TODAY)
    with pytest.raises(SchedulerError, match="unknown host"):
        svc.book("cardiologista", "2026-07-01", "09:00", "Ana")


def test_auto_confirm_false_keeps_pending():
    store = InMemoryAppointmentStore()
    store.hosts["dr_x"] = Host("dr_x", "Dr. X", "GP", auto_confirm=False)
    svc = SchedulerService(store, today=lambda: _TODAY)
    appt = svc.book("dr_x", "2026-07-01", "09:00", "Ana")
    assert appt.status == PENDING            # waits for the professional to accept
    accepted, changed = svc.update_status(appt.appointment_id, "CONFIRMED")
    assert accepted.status == CONFIRMED and changed is True


def test_book_unknown_host_raises():
    with pytest.raises(SchedulerError, match="unknown host"):
        _svc().book("ghost", "2026-07-01", "09:00", "Ana")


def test_book_invalid_slot_raises():
    with pytest.raises(SchedulerError, match="not a bookable slot"):
        _svc().book("dr_silva", "2026-07-01", "03:00", "Ana")


def test_double_booking_raises():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    with pytest.raises(SchedulerError, match="already booked"):
        svc.book("dr_silva", "2026-07-01", "09:00", "Bob")


def test_book_is_idempotent_for_same_client():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    b = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")     # identical → returns existing
    assert b.appointment_id == a.appointment_id
    assert len(svc.list_appointments()) == 1                   # not duplicated
    # a DIFFERENT client at the same slot still conflicts
    with pytest.raises(SchedulerError, match="already booked"):
        svc.book("dr_silva", "2026-07-01", "09:00", "Bob")


def test_same_slot_different_date_ok():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    appt = svc.book("dr_silva", "2026-07-02", "09:00", "Bob")
    assert appt.date == "2026-07-02"


def test_list_appointments_filters():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    svc.book("dr_silva", "2026-07-01", "10:00", "Bob")
    assert len(svc.list_appointments()) == 2
    assert len(svc.list_appointments(with_name="ana")) == 1   # case-insensitive


def test_list_appointments_hides_terminal_by_default():
    # A stale CANCELED/COMPLETED row must not leak into the live agenda — that noise made the
    # voicer narrate a fresh cancellation ("cancelado com sucesso") off an old row.
    svc, clock = _clocked(_TODAY)
    live = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    gone = svc.book("dr_silva", "2026-07-01", "10:00", "Bob")
    done = svc.book("dr_silva", "2026-07-01", "11:00", "Cid")
    svc.cancel(gone.appointment_id)
    clock["d"] = date(2026, 7, 1)     # o dia chegou — só então "aconteceu" é verdade
    svc.update_status(done.appointment_id, COMPLETED)

    active = svc.list_appointments()
    assert [a.appointment_id for a in active] == [live.appointment_id]   # only PENDING/CONFIRMED
    assert all(a.status in {PENDING, CONFIRMED} for a in active)

    # the escape hatch brings history back when explicitly requested
    everything = svc.list_appointments(include_history=True)
    assert len(everything) == 3
    assert {a.status for a in everything} == {CONFIRMED, CANCELED, COMPLETED}  # dr_silva auto-confirms

    # the filter also applies to the role-scoped path (a guest never sees their canceled row)
    svc.book("dr_silva", "2026-07-02", "09:00", "Ana", guest_id="g-ana")
    canc = svc.book("dr_silva", "2026-07-02", "10:00", "Ana", guest_id="g-ana")
    svc.cancel(canc.appointment_id)
    guest_view = svc.list_appointments(identity_id="g-ana", role="GUEST")
    assert all(a.status in {PENDING, CONFIRMED} for a in guest_view)


def test_list_appointments_expires_past_rows_by_financial_class():
    """Past-dated LIVE rows terminalize on read, split by billable class (bookkeeper reads
    COMPLETED): CONFIRMED booking → COMPLETED (revenue), PENDING → CANCELED/expired (never
    happened), a CONFIRMED block → CANCELED/expired (not a consultation). Future/today stay live."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_x"] = Host("dr_x", "Dr. X", "GP", auto_confirm=False)   # books PENDING
    clock = {"d": date(2026, 6, 30)}
    svc = SchedulerService(store, today=lambda: clock["d"])

    confirmed = svc.book("dr_x", "2026-07-01", "09:00", "Ana")
    svc.update_status(confirmed.appointment_id, CONFIRMED)                  # accepted booking
    pending = svc.book("dr_x", "2026-07-01", "10:00", "Bob")               # stays PENDING
    block = svc.book("dr_x", "2026-07-01", "11:00", "")                    # nameless block
    future = svc.book("dr_x", "2026-07-10", "09:00", "Cid")
    svc.update_status(future.appointment_id, CONFIRMED)

    clock["d"] = date(2026, 7, 5)     # 07-01 rows are now past; 07-10 is still upcoming
    live = svc.list_appointments()    # the read triggers the sweep
    assert [a.appointment_id for a in live] == [future.appointment_id]

    everything = {a.appointment_id: a for a in svc.list_appointments(include_history=True)}
    assert everything[confirmed.appointment_id].status == COMPLETED        # billable
    assert everything[pending.appointment_id].status == CANCELED           # never accepted
    assert everything[pending.appointment_id].cancel_reason == "expired"
    assert everything[block.appointment_id].status == CANCELED             # a block is not revenue
    assert everything[block.appointment_id].cancel_reason == "expired"
    assert everything[future.appointment_id].status == CONFIRMED           # untouched

    # the bookkeeper's revenue query sees exactly the one real completed consultation
    completed = svc.list_appointments(status="COMPLETED")
    assert [a.appointment_id for a in completed] == [confirmed.appointment_id]


def test_sweep_is_idempotent_and_leaves_bad_dates_alone():
    """A second sweep re-writes the same terminal value (multi-worker safe); an unparseable
    date is never silently terminalized."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_x"] = Host("dr_x", "Dr. X", "GP")
    clock = {"d": date(2026, 6, 30)}
    svc = SchedulerService(store, today=lambda: clock["d"])
    good = svc.book("dr_x", "2026-07-01", "09:00", "Ana")                  # CONFIRMED
    bad = svc.book("dr_x", "2026-07-01", "10:00", "Bob")
    store.get(bad.appointment_id).date = "not-a-date"                      # corrupt the row

    clock["d"] = date(2026, 7, 5)
    svc.list_appointments()
    svc.list_appointments()                                                # sweep twice
    assert store.get(good.appointment_id).status == COMPLETED             # stable, not re-flipped
    assert store.get(bad.appointment_id).status == CONFIRMED              # bad date left as-is


def test_cancel_frees_the_slot():
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    cancelled, changed = svc.cancel(appt.appointment_id, reason="patient request")
    assert changed
    assert cancelled.status == CANCELED
    assert cancelled.cancel_reason == "patient request"
    assert "09:00" in svc.check_availability("dr_silva", "2026-07-01")


def test_cancel_unknown_raises():
    with pytest.raises(SchedulerError, match="unknown appointment"):
        _svc().cancel("nope")


# ── Gap 2: cancel now guards status like its siblings (reschedule / update_status) ──

def test_cancel_completed_records_a_reason_instead_of_refusing():
    """Era `test_cancel_completed_is_refused`, e a recusa saiu em 2026-08-19.

    A regra vinha do pai ("linhas terminais são intocáveis") e custava caro aqui, porque neste
    produto a varredura conclui SOZINHA toda consulta passada — então o profissional relatando
    uma falta batia sempre nela, e o desvio de dois passos que a contornava corria contra
    qualquer listagem. O que ela protegia continua protegido em outro lugar: `cancel` é
    `destructiveHint=True`, o Gate B segura, o host confirma.

    O que sobra da regra, e é o que este teste passa a fixar: o cancelamento GRAVA o motivo.
    Uma linha atendida que vira cancelada tem que ficar legível depois."""
    svc, clock = _clocked(_TODAY)
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    clock["d"] = date(2026, 7, 1)
    svc.update_status(appt.appointment_id, COMPLETED)
    canceled, changed = svc.cancel(appt.appointment_id, reason="paciente faltou")
    assert changed and canceled.status == CANCELED
    assert canceled.cancel_reason == "paciente faltou"


def test_cancel_already_canceled_is_idempotent_noop():
    """Re-cancelling an already-CANCELED row is retry-safe (no error) but flagged
    ``changed=False`` so the voicer can say "was already canceled" instead of narrating a
    fresh cancellation off a stale id."""
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    _, first = svc.cancel(appt.appointment_id)
    assert first is True
    again, changed = svc.cancel(appt.appointment_id)
    assert changed is False and again.status == CANCELED


# ── Gap 1 (option A): row-level ownership on the destructive mutations ──

def _two_host_svc():
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    store.hosts["dr_souza"] = Host("dr_souza", "Dr. Souza", "GP")
    return SchedulerService(store, today=lambda: _TODAY)


def test_guest_cannot_cancel_another_guests_appointment():
    svc = _two_host_svc()
    ana = svc.book("dr_silva", "2026-07-01", "09:00", "Ana", guest_id="g-ana")
    # Bob (a different guest) holding Ana's id may not cancel it — even with a valid id.
    with pytest.raises(SchedulerError, match="not yours to modify"):
        svc.cancel(ana.appointment_id, identity_id="g-bob", role="GUEST")
    # Ana herself can.
    _, changed = svc.cancel(ana.appointment_id, identity_id="g-ana", role="GUEST")
    assert changed is True


def test_employee_scoped_to_own_agenda():
    svc = _two_host_svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana", guest_id="g-ana")
    # dr_souza (another professional) cannot touch a row on dr_silva's agenda.
    with pytest.raises(SchedulerError, match="not yours to modify"):
        svc.update_status(appt.appointment_id, CONFIRMED,
                          identity_id="dr_souza", role="EMPLOYEE")
    with pytest.raises(SchedulerError, match="not yours to modify"):
        svc.reschedule(appt.appointment_id, "2026-07-02", "10:00",
                       identity_id="dr_souza", role="EMPLOYEE")
    # dr_silva owns the agenda → allowed.
    ok, _ = svc.update_status(appt.appointment_id, CONFIRMED,
                              identity_id="dr_silva", role="EMPLOYEE")
    assert ok.status == CONFIRMED


def test_oversight_role_can_touch_any_row():
    svc = _two_host_svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana", guest_id="g-ana")
    _, changed = svc.cancel(appt.appointment_id, identity_id="sup-1", role="SUPERVISOR")
    assert changed is True


def test_role_omitted_skips_ownership_check():
    """Internal/test callers (and the host's demo-guest edge) pass no role → no ownership gate,
    exactly like ``list_appointments``. Visibility is what limits which ids they could have."""
    svc = _two_host_svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana", guest_id="g-ana")
    _, changed = svc.cancel(appt.appointment_id)     # no identity_id/role → allowed
    assert changed is True


def test_unknown_role_is_denied_failsafe():
    svc = _two_host_svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana", guest_id="g-ana")
    with pytest.raises(SchedulerError, match="not yours to modify"):
        svc.cancel(appt.appointment_id, identity_id="whoever", role="MARKETING")


def test_update_status_lifecycle():
    svc, clock = _clocked(_TODAY)
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    assert svc.update_status(appt.appointment_id, "confirmed")[0].status == CONFIRMED
    clock["d"] = date(2026, 7, 1)     # só se completa o que já aconteceu
    assert svc.update_status(appt.appointment_id, "COMPLETED")[0].status == COMPLETED
    # a COMPLETED appointment frees the slot again. Read through the STORE, not
    # check_availability: with the clock on the appointment's own day, the availability API
    # refuses it outright ("scheduling starts from tomorrow") — a booking policy, not the fact
    # under test.
    assert "09:00" not in svc.store.booked_times("dr_silva", "2026-07-01")


def test_update_status_noop_is_idempotent_and_flagged():
    """Re-issuing the SAME status is retry-safe (never an error) but flagged ``changed=False``
    so the tool text can say "was ALREADY CONFIRMED" — the model notices a stale/wrong id
    instead of celebrating a change that never happened (the bulk-confirm live bug)."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_x"] = Host("dr_x", "Dr. X", "GP", auto_confirm=False)   # books PENDING
    svc = SchedulerService(store, today=lambda: _TODAY)
    appt = svc.book("dr_x", "2026-07-01", "09:00", "Ana")
    first, changed = svc.update_status(appt.appointment_id, CONFIRMED)
    assert changed is True and first.status == CONFIRMED
    again, changed2 = svc.update_status(appt.appointment_id, CONFIRMED)
    assert changed2 is False and again.status == CONFIRMED   # unchanged, no error


def test_update_status_past_appointment_cannot_go_active():
    """Yesterday's appointment can be closed out (COMPLETED/CANCELED) but never (re)confirmed —
    confirming the past is meaningless and hides that the model picked a stale id."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_x"] = Host("dr_x", "Dr. X", "GP", auto_confirm=False)   # books PENDING
    clock = {"d": _TODAY}
    svc = SchedulerService(store, today=lambda: clock["d"])
    appt = svc.book("dr_x", "2026-07-01", "09:00", "Ana")       # future at booking time
    clock["d"] = date(2026, 7, 2)                                # ...now it is in the past
    with pytest.raises(SchedulerError, match="past"):
        svc.update_status(appt.appointment_id, CONFIRMED)
    done, changed = svc.update_status(appt.appointment_id, COMPLETED)   # closing out stays OK
    assert done.status == COMPLETED and changed is True


def test_list_appointments_status_filter():
    """"traga só os pendentes" is deterministic: the vertical filters, not the model."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_x"] = Host("dr_x", "Dr. X", "GP", auto_confirm=False)
    svc = SchedulerService(store, today=lambda: _TODAY)
    pend = svc.book("dr_x", "2026-07-01", "09:00", "Ana")                 # PENDING
    conf, _ = svc.update_status(svc.book("dr_x", "2026-07-01", "10:00", "Bob").appointment_id,
                                CONFIRMED)
    gone = svc.book("dr_x", "2026-07-01", "11:00", "Cid")
    svc.cancel(gone.appointment_id)                                       # CANCELED (terminal)

    only_pending = svc.list_appointments(status="pending")                # case-insensitive
    assert [a.appointment_id for a in only_pending] == [pend.appointment_id]
    only_conf = svc.list_appointments(status=CONFIRMED)
    assert [a.appointment_id for a in only_conf] == [conf.appointment_id]
    # an explicit terminal status implies history (no include_history needed)
    assert [a.appointment_id for a in svc.list_appointments(status="CANCELED")] \
        == [gone.appointment_id]
    with pytest.raises(SchedulerError, match="invalid status filter"):
        svc.list_appointments(status="WHATEVER")


def test_update_status_invalid_raises():
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    with pytest.raises(SchedulerError, match="invalid status"):
        svc.update_status(appt.appointment_id, "MAYBE")


def test_update_status_unknown_appointment_raises():
    with pytest.raises(SchedulerError, match="unknown appointment"):
        _svc().update_status("nope", "CONFIRMED")


def test_book_today_or_past_raises():
    svc = _svc()
    with pytest.raises(SchedulerError, match="starts from tomorrow"):
        svc.book("dr_silva", _TODAY.isoformat(), "09:00", "Ana")
    with pytest.raises(SchedulerError, match="starts from tomorrow"):
        svc.book("dr_silva", "2026-06-01", "09:00", "Ana")


def test_availability_today_or_past_raises():
    with pytest.raises(SchedulerError, match="starts from tomorrow"):
        _svc().check_availability("dr_silva", _TODAY.isoformat())


def test_book_malformed_date_raises():
    with pytest.raises(SchedulerError, match="invalid date"):
        _svc().book("dr_silva", "07/01/2026", "09:00", "Ana")


def test_resolve_date_relative():
    svc = _svc()  # today = 2026-06-30 (Tuesday)
    assert svc.resolve_date("amanhã") == "2026-07-01"
    assert svc.resolve_date("tomorrow") == "2026-07-01"
    assert svc.resolve_date("depois de amanhã") == "2026-07-02"
    assert svc.resolve_date("hoje") == "2026-06-30"


def test_resolve_date_weekdays():
    svc = _svc()  # today = 2026-06-30 (Tuesday, weekday=1)
    assert svc.resolve_date("próxima sexta-feira") == "2026-07-03"   # Fri
    assert svc.resolve_date("sexta que vem") == "2026-07-03"
    assert svc.resolve_date("quarta") == "2026-07-01"                 # Wed (next day)
    assert svc.resolve_date("segunda") == "2026-07-06"               # next Monday
    # today is Tuesday → "terça" means the NEXT one, +7
    assert svc.resolve_date("terça") == "2026-07-07"


def test_resolve_date_counted_relatives():
    """"daqui a N dias/semanas" — the family the host's tool description named VERBATIM.

    The parser had no branch for it, so the model read "'daqui a X dias' style relatives"
    off the tool description, passed exactly that, and got an error: measured on
    `secretary_bench` 2026-08-04, `resolve_date` failed 50-86% of its calls.
    """
    svc = _svc()  # today = 2026-06-30 (Tuesday)
    assert svc.resolve_date("daqui a 3 dias") == "2026-07-03"
    assert svc.resolve_date("daqui a 1 dia") == "2026-07-01"
    assert svc.resolve_date("dentro de 5 dias") == "2026-07-05"
    assert svc.resolve_date("em 2 semanas") == "2026-07-14"
    assert svc.resolve_date("in 10 days") == "2026-07-10"
    # spelled-out counts: far more common in speech than "daqui a 1 semana"
    assert svc.resolve_date("daqui a uma semana") == "2026-07-07"
    assert svc.resolve_date("daqui a duas semanas") == "2026-07-14"
    assert svc.resolve_date("in two weeks") == "2026-07-14"
    # a trailing time-of-day must not defeat the match
    assert svc.resolve_date("daqui a 3 dias de manhã") == "2026-07-03"
    # the weekday reading still wins where there IS a weekday
    assert svc.resolve_date("sexta que vem") == "2026-07-03"


def test_resolve_date_counted_relative_needs_a_whole_word():
    """"em"/"in" are two letters long and live inside plenty of other words. Without a word
    boundary the relative branch fired on "tambem 3 dias" and "certain 3 days", inventing a
    date out of a sentence that named none — the worst failure shape for a date tool, since
    a wrong date books a wrong appointment silently."""
    svc = _svc()
    for not_a_date in ("tambem 3 dias", "também 3 dias", "certain 3 days", "a ordem 3 dias"):
        with pytest.raises(SchedulerError):
            svc.resolve_date(not_a_date)
    # the real forms still parse
    assert svc.resolve_date("em 3 dias") == "2026-07-03"
    assert svc.resolve_date("marcar em 3 dias") == "2026-07-03"


def test_resolve_date_refuses_vague_ranges_on_purpose():
    """A span is not a day. Resolving "semana que vem" to (say) its Monday would let the
    agent silently book a day the user never chose — strictly worse than asking. These
    raise so the caller asks; the fix for them was to stop ADVERTISING them."""
    svc = _svc()
    for vague in ("semana que vem", "próxima semana", "essa semana", "no fim de semana",
                  "mês que vem", "next week", "this week", "de manhã"):
        with pytest.raises(SchedulerError):
            svc.resolve_date(vague)


def test_resolve_date_explicit_calendar():
    svc = _svc()  # today = 2026-06-30 (Tuesday)
    # numeric DAY-FIRST (pt-BR): 09/07 is 9 July, not 7 September
    assert svc.resolve_date("09/07") == "2026-07-09"
    assert svc.resolve_date("dia 09/07") == "2026-07-09"           # tolerates a prefix
    assert svc.resolve_date("9-7-2026") == "2026-07-09"            # other separators + year
    assert svc.resolve_date("9.7.26") == "2026-07-09"              # 2-digit year → 20xx
    # a bare day/month already past this year rolls to next year
    assert svc.resolve_date("29/06") == "2027-06-29"
    assert svc.resolve_date("30/06") == "2026-06-30"              # today itself is allowed
    # named month (PT + EN) and ISO passthrough
    assert svc.resolve_date("9 de julho") == "2026-07-09"
    assert svc.resolve_date("9 july") == "2026-07-09"
    assert svc.resolve_date("2026-07-09") == "2026-07-09"
    # impossible / unparseable → raise (caller asks the user)
    with pytest.raises(SchedulerError):
        svc.resolve_date("31/02")
    with pytest.raises(SchedulerError):
        svc.resolve_date("bananas")


def test_reschedule_moves_slot_keeps_id():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    moved = svc.reschedule(a.appointment_id, "2026-07-01", "11:00")
    assert moved.appointment_id == a.appointment_id          # same appointment
    assert (moved.date, moved.time) == ("2026-07-01", "11:00")
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert "09:00" in free and "11:00" not in free           # old freed, new taken


def test_reschedule_to_taken_slot_errors_with_alternatives():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    svc.book("dr_silva", "2026-07-01", "11:00", "Bob")
    with pytest.raises(SchedulerError, match="already booked. Free slots"):
        svc.reschedule(a.appointment_id, "2026-07-01", "11:00")


def test_reschedule_same_slot_is_noop():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    same = svc.reschedule(a.appointment_id, "2026-07-01", "09:00")
    assert same.appointment_id == a.appointment_id


def test_reschedule_unknown_raises():
    with pytest.raises(SchedulerError, match="unknown appointment"):
        _svc().reschedule("nope", "2026-07-01", "11:00")


def test_reschedule_past_date_raises():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    with pytest.raises(SchedulerError, match="starts from tomorrow"):
        svc.reschedule(a.appointment_id, _TODAY.isoformat(), "11:00")


def test_reschedule_canceled_appointment_raises():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    svc.cancel(a.appointment_id)
    with pytest.raises(SchedulerError, match="only an active"):
        svc.reschedule(a.appointment_id, "2026-07-01", "11:00")


def test_block_whole_day_removes_all_slots():
    svc = _svc()
    blocks = svc.block_schedule("dr_silva", "2026-07-01")
    assert len(blocks) == len(svc._slots)
    assert all(b.is_block and b.status == CONFIRMED for b in blocks)
    assert svc.check_availability("dr_silva", "2026-07-01") == []


def test_block_single_slot():
    svc = _svc()
    svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00")
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert "09:00" not in free and "10:00" in free


def test_block_time_range():
    svc = _svc()
    svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00", end_time="11:00")
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert "09:00" not in free and "10:00" not in free   # [09:00, 11:00)
    assert "11:00" in free                                # end is exclusive


def test_block_refuses_when_client_booked_in_range():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "10:00", "Ana")
    with pytest.raises(SchedulerError, match="client appointments exist"):
        svc.block_schedule("dr_silva", "2026-07-01")        # whole day clashes with Ana@10:00


def test_block_is_idempotent():
    svc = _svc()
    first = svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00")
    second = svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00")
    assert len(first) == 1 and second == []                 # already blocked → skipped


def test_block_allows_today_but_not_past():
    svc = _svc()  # today = 2026-06-30
    # blocking today is allowed (a host can mark today unavailable), unlike booking
    assert svc.block_schedule("dr_silva", _TODAY.isoformat(), start_time="09:00")
    with pytest.raises(SchedulerError, match="in the past"):
        svc.block_schedule("dr_silva", "2026-06-01")


def test_block_unknown_host_raises():
    with pytest.raises(SchedulerError, match="unknown host"):
        _svc().block_schedule("ghost", "2026-07-01")


def test_block_invalid_single_slot_raises():
    with pytest.raises(SchedulerError, match="not a bookable slot"):
        _svc().block_schedule("dr_silva", "2026-07-01", start_time="03:00")


def test_block_empty_range_raises():
    with pytest.raises(SchedulerError, match="no bookable slots"):
        _svc().block_schedule("dr_silva", "2026-07-01", start_time="12:00", end_time="13:00")


def test_block_does_not_appear_as_client_booking():
    svc = _svc()
    svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00")
    # a block carries no client name → filtering by a real name never returns it
    assert svc.list_appointments(with_name="Ana") == []
    blocks = [a for a in svc.list_appointments() if a.is_block]
    assert len(blocks) == 1


def test_resolve_date_unparseable_raises():
    with pytest.raises(SchedulerError, match="could not resolve"):
        _svc().resolve_date("qualquer coisa sem data")


def test_store_is_injectable_port():
    assert isinstance(InMemoryAppointmentStore(), __import__(
        "cogno_praxis.scheduler.store", fromlist=["AppointmentStore"]).AppointmentStore)


# ── two-sided identity model: role-based visibility (the doctor-sees-guest-booking fix) ──
def test_role_visibility_guest_doctor_supervisor():
    # A guest books WITH a doctor. The SAME row must be visible to BOTH sides — the guest
    # (guest_id) and the doctor (host_id) — which the old with_name-only model failed at.
    store = InMemoryAppointmentStore()
    store.hosts["dr_vini"] = Host("dr_vini", "Dr. Vinicius Vale", "Cardio", auto_confirm=False)
    svc = SchedulerService(store, today=lambda: _TODAY)

    appt = svc.book("dr_vini", "2026-07-06", "09:00", "Ana",
                    guest_id="ana_id", host_name="Dr. Vinicius Vale")
    assert appt.status == PENDING and appt.guest_id == "ana_id"

    # the DOCTOR (EMPLOYEE) sees the guest's PENDING booking in their own agenda
    doc_view = svc.list_appointments(identity_id="dr_vini", role="EMPLOYEE")
    assert [a.appointment_id for a in doc_view] == [appt.appointment_id]

    # the GUEST sees their own booking
    guest_view = svc.list_appointments(identity_id="ana_id", role="GUEST")
    assert [a.appointment_id for a in guest_view] == [appt.appointment_id]

    # a DIFFERENT guest sees nothing
    assert svc.list_appointments(identity_id="bob_id", role="GUEST") == []

    # a SUPERVISOR sees everything in scope
    sup_view = svc.list_appointments(identity_id="whoever", role="SUPERVISOR")
    assert [a.appointment_id for a in sup_view] == [appt.appointment_id]

    # an unknown role fails safe to the NARROWEST view (own bookings), never "see all"
    assert svc.list_appointments(identity_id="ana_id", role="WeirdRole") == guest_view


def test_single_active_follows_guest_id_not_name():
    # the single-active guard must key off the STABLE guest_id, so two people who happen to
    # share a display name don't collide, and one person is correctly capped.
    store = InMemoryAppointmentStore()
    store.hosts["h"] = Host("h", "Host", "", auto_confirm=True)
    svc = SchedulerService(store, today=lambda: _TODAY)
    svc.set_settings(max_active_per_client=1)

    svc.book("h", "2026-07-06", "09:00", "Ana", guest_id="ana_id")
    # same guest_id, another slot → blocked (their 1 active slot is used)
    with pytest.raises(SchedulerError, match="already has an active appointment"):
        svc.book("h", "2026-07-07", "10:00", "Ana", guest_id="ana_id")
    # a DIFFERENT guest_id with the SAME display name → allowed (not the same client)
    other = svc.book("h", "2026-07-07", "11:00", "Ana", guest_id="ana2_id")
    assert other.guest_id == "ana2_id"


# ── the status LIFECYCLE, not just the vocabulary ────────────────────────────────────
# Splitting the MCP tool into confirm_/complete_ narrowed which NAMES the model reaches; it
# did nothing about which TRANSITIONS are legal. All four cases below were MEASURED against
# the split as first shipped (2026-08-18) — each one succeeded and each one is a real loss.


def _clocked(today: date, *, auto_confirm: bool = True):
    """A service whose "today" can be moved, so the DOCTOR flow can be played out in order:
    book (must be in the future) → confirm → the day arrives → complete."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP", auto_confirm=auto_confirm)
    clock = {"d": today}
    return SchedulerService(store, today=lambda: clock["d"]), clock


def test_a_future_appointment_cannot_be_COMPLETED():
    """Measured before the guard: completing tomorrow's booking removed it from the agenda,
    freed the slot for someone else, and `cancel_appointment` then refused it forever — a
    booking evaporated through a tool with no destructiveHint, which is the very gate bypass
    the tool split was made to close."""
    svc, _clock = _clocked(_TODAY)
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Maria")
    with pytest.raises(SchedulerError, match="in the future"):
        svc.update_status(appt.appointment_id, COMPLETED)
    assert svc.store.get(appt.appointment_id).status == CONFIRMED   # untouched
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")   # still taken


def test_a_CANCELED_appointment_cannot_be_COMPLETED():
    """COMPLETED is the billable set the bookkeeper queries. Resurrecting a canceled row into
    it books phantom revenue — and `cancel()` already guarded the inverse direction, so the
    asymmetry was the bug."""
    svc, _clock = _clocked(_TODAY)
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Maria")
    svc.cancel(appt.appointment_id)
    with pytest.raises(SchedulerError, match="CANCELED"):
        svc.update_status(appt.appointment_id, COMPLETED)
    assert svc.store.get(appt.appointment_id).status == CANCELED


def test_a_schedule_BLOCK_cannot_be_COMPLETED():
    """``expire_past`` states the rule outright: "a block is not a consultation, so it must
    never enter the COMPLETED/revenue set" — it sends past blocks to CANCELED for exactly this
    reason. Measured: completing a block re-opened the blocked time for booking AND filed the
    block as revenue."""
    svc, _clock = _clocked(_TODAY)
    svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00", end_time="10:00",
                       description="Congresso")
    block = next(a for a in svc.store.list() if a.is_block)
    with pytest.raises(SchedulerError, match="BLOCK"):
        svc.update_status(block.appointment_id, COMPLETED)
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")   # still blocked


def test_reviving_a_canceled_row_never_double_books_its_old_slot():
    """The service trusted ``store.update`` to raise ``SlotTakenError`` — but only the Postgres
    adapter does; ``InMemoryAppointmentStore`` (the shipped default, and what every test and
    bench runs on) overwrites blindly. Measured: cancel Ana 09:00 → book Bia 09:00 → confirm
    Ana's id → TWO CONFIRMED rows at the same slot. A rule the default store does not enforce
    is not a rule, so the check moved into the service."""
    svc, _clock = _clocked(_TODAY)
    ana = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    svc.cancel(ana.appointment_id)
    svc.book("dr_silva", "2026-07-01", "09:00", "Bia")
    with pytest.raises(SchedulerError, match="booked by someone else"):
        svc.update_status(ana.appointment_id, CONFIRMED)
    live = [a for a in svc.store.list() if a.status == CONFIRMED and a.time == "09:00"]
    assert [a.with_name for a in live] == ["Bia"]


def test_COMPLETED_can_be_CORRECTED_but_not_quietly_canceled():
    """Revisado em 2026-08-19: a primeira versão fixava "COMPLETED é terminal nos dois
    sentidos", e isso era over-reach meu.

    O dano que eu queria fechar era CANCELED→COMPLETED (receita fantasma). Tornar o COMPLETED
    irreversível de quebra fez `complete_appointment` — tool SEM `destructiveHint`, que o Gate
    B nunca segura — alcançar um estado sem volta: marcar a linha errada como realizada tirava
    a consulta da agenda, liberava o horário e não tinha desfazer. É a forma exata que o split
    das tools existia para fechar, reintroduzida por mim do outro lado.

    Marcar como realizado voltou a ser reversível, e é isso que mantém a tool honestamente
    não-destrutiva.

    Revisado de novo em 2026-08-19: cancelar um COMPLETED **passou a ser permitido**, e o
    "quietly" do nome é o que restou da regra. Barrá-lo era a segunda tranca de uma porta que
    já tem uma — `cancel_appointment` é `destructiveHint=True`, então o Gate B segura a chamada
    e o host confirma antes de commitar. E como a varredura conclui sozinha toda linha passada,
    barrar essa aresta obrigava a um desvio de dois passos que CORRIA contra qualquer listagem
    (ver `test_the_sweep_undoes_the_undo`). O que a regra protegia continua protegido pelo
    gate; o que ela custava era o profissional não conseguir registrar uma falta.

    O que NÃO afrouxou: o cancelamento grava o motivo, então ele fica legível depois em vez de
    silencioso — que é o "quietly" — e a linha não pode ser lavada de volta para ativa (ver
    `test_the_expired_exemption_does_not_compose_into_a_past_revival`).
    """
    svc, clock = _clocked(_TODAY)
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Maria")
    clock["d"] = date(2026, 7, 1)
    svc.update_status(appt.appointment_id, COMPLETED)
    corrigido, changed = svc.update_status(appt.appointment_id, CONFIRMED)
    assert changed and corrigido.status == CONFIRMED      # errou a linha? dá para voltar
    svc.update_status(appt.appointment_id, COMPLETED)
    cancelado, changed = svc.cancel(appt.appointment_id, reason="não compareceu")
    assert changed and cancelado.status == CANCELED
    assert cancelado.cancel_reason == "não compareceu", "sem motivo seria justamente 'quietly'"


def test_a_consultation_the_system_expired_can_still_be_billed():
    """`_sweep_expired` manda um PENDING vencido para CANCELED(reason='expired') sem ninguém
    decidir nada. A consulta ACONTECEU; só ninguém confirmou a tempo.

    Antes deste conserto ela ficava presa: não podia voltar a CONFIRMED (regra do passado),
    nem ir a COMPLETED (regra do "foi cancelada, não aconteceu"), e `book` recusa data passada
    — as duas mensagens mandavam para caminhos fechados. Cancelamento que o SISTEMA fez não é
    decisão de que a consulta não ocorreu.
    """
    svc, clock = _clocked(_TODAY, auto_confirm=False)
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Maria")
    assert appt.status == PENDING
    clock["d"] = date(2026, 7, 2)
    svc.list_appointments()                       # dispara o sweep
    assert svc.store.get(appt.appointment_id).status == CANCELED
    done, changed = svc.update_status(appt.appointment_id, COMPLETED)
    assert changed and done.status == COMPLETED
    # …e um cancelamento de VERDADE (alguém pediu) segue barrado
    outro = svc.book("dr_silva", "2026-07-03", "09:00", "Bia")
    svc.cancel(outro.appointment_id, "cliente desistiu")
    with pytest.raises(SchedulerError, match="did not happen"):
        svc.update_status(outro.appointment_id, COMPLETED)

def test_the_whole_DOCTOR_flow_still_runs_end_to_end():
    """THE control arm. Every guard above forbids something; this proves they forbid only
    that. A rule that also blocks "confirma a Maria" / "já atendi" would be worse than the
    hole it closes."""
    svc, clock = _clocked(_TODAY, auto_confirm=False)
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Maria")
    assert appt.status == PENDING
    _, changed = svc.update_status(appt.appointment_id, CONFIRMED)
    assert changed
    clock["d"] = date(2026, 7, 1)                       # the day arrives
    done, changed = svc.update_status(appt.appointment_id, COMPLETED)
    assert changed and done.status == COMPLETED
    # …and a cancel-then-change-of-mind still works when the slot is free.
    other = svc.book("dr_silva", "2026-07-02", "10:00", "João")
    svc.cancel(other.appointment_id)
    revived, changed = svc.update_status(other.appointment_id, CONFIRMED)
    assert changed and revived.status == CONFIRMED


# ── configuração que se volta contra a agenda ────────────────────────────────────────
# Achados por varredura (2026-08-18): procurando outros pares tool-genérica/tool-destrutiva
# como o `update_appointment_status`, o que apareceu foi outra classe — config aceita em
# silêncio que derruba ou apaga a agenda. Nenhum é bypass de gate; os dois são reversíveis.
# Só o painel escreve aqui (nenhuma RolePolicy concede `set_schedule_settings` ao modelo).


def test_max_active_per_client_zero_disables_the_limit_instead_of_crashing():
    """MEDIDO: 0 fazia toda reserva estourar `IndexError: list index out of range`.

        if not already_here and len(mine) >= cfg.max_active_per_client:
            ex = mine[0]          # mine == [] e 0 >= 0 é True

    O admin põe 0 no painel (que não valida nada) e a agenda para, com uma mensagem que não
    diz nada nem para o usuário nem para o modelo — que, recebendo isso, não tem como se
    corrigir. Crash nunca é a recusa certa.

    0 = DESLIGADO é o que a própria classe promete para os irmãos deste knob ("0/None =
    disabled"), e é o lado não-catastrófico de um valor ambíguo: quem quis dizer "fechado" tem
    `block_schedule` e o expediente; quem quis dizer "sem limite" teria matado a própria agenda.
    """
    svc = _svc()
    svc.set_settings(max_active_per_client=0)
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")     # não estoura
    assert appt.status == CONFIRMED
    svc.book("dr_silva", "2026-07-02", "09:00", "Ana")            # e não há teto
    assert svc._config.max_active_per_client is None
    # …e um limite DE VERDADE continua limitando — senão o conserto teria virado um buraco.
    svc2 = _svc()
    svc2.set_settings(max_active_per_client=1)
    svc2.book("dr_silva", "2026-07-01", "09:00", "Bia")
    with pytest.raises(SchedulerError, match="already has an active appointment"):
        svc2.book("dr_silva", "2026-07-02", "09:00", "Bia")


def test_an_impossible_working_day_is_refused_at_the_WRITE():
    """MEDIDO: `work_start=17:00, work_end=09:00` era aceito em silêncio e a agenda apagava,
    com "no free slots ... and none in the next two weeks" — a mensagem culpa a
    disponibilidade pelo que é erro de configuração, então ninguém olha para o ajuste.
    """
    svc = _svc()
    with pytest.raises(SchedulerError, match="must be after work_start"):
        svc.set_settings(work_start="17:00", work_end="09:00")
    with pytest.raises(SchedulerError, match="must be after work_start"):
        svc.set_settings(work_start="09:00", work_end="09:00")   # dia de duração zero
    with pytest.raises(SchedulerError, match="slot_duration_minutes"):
        svc.set_settings(slot_duration_minutes=0)
    # a recusa não pode ter deixado a config pela metade
    assert svc.check_availability("dr_silva", "2026-07-01")
    # …e um expediente válido passa, incluindo um mais LARGO que o default.
    svc.set_settings(work_start="08:00", work_end="18:00")
    assert "08:00" in svc.check_availability("dr_silva", "2026-07-01")


def test_a_config_already_persisted_bad_still_LOADS():
    """A validação mora na escrita, não na leitura, e isso é deliberado.

    Se `SchedulerConfig.__init__` levantasse, um tenant cuja linha já está ruim perderia o
    scheduler inteiro no boot — pior que o estado em que ele já está. Ele carrega, rende o dia
    vazio que hoje já rende, e a PRÓXIMA escrita é que precisa ser coerente."""
    from cogno_praxis.scheduler.engine import SchedulerConfig

    bad = SchedulerConfig({"work_start": "17:00", "work_end": "09:00"})   # não levanta
    assert bad.work_end < bad.work_start
    with pytest.raises(ValueError):
        bad.validate()


# ── a no-show must be correctable, because the completion was not a decision ───────────
def _swept_past_row():
    """A CONFIRMED appointment from yesterday, after one listing has run.

    That listing is what matters: `_sweep_expired` terminalizes past rows by billable class
    on every read, so a past CONFIRMED becomes COMPLETED with nobody deciding anything. This
    is the state a professional saying "a Beatriz não veio" actually arrives at."""
    from cogno_praxis.scheduler import Host, InMemoryAppointmentStore, SchedulerService
    from cogno_praxis.scheduler.store import Appointment

    today = date(2026, 7, 6)
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    store.add(Appointment(appointment_id="a1", host_id="dr_silva", host_name="Dr. Silva",
                          date=(today - timedelta(days=1)).isoformat(), time="09:00",
                          with_name="Beatriz", status="CONFIRMED"))
    svc = SchedulerService(store, today=lambda: today)
    svc.list_appointments(host_id="dr_silva")
    assert store.get("a1").status == COMPLETED, "premise: the sweep completes it on its own"
    return svc


def test_there_is_no_refusal_left_to_name_a_way_out_of():
    """O #79 fez a recusa nomear o caminho de volta; este commit tira a recusa.

    Uma mensagem que ensina um desvio é melhor que um beco, e pior que não precisar de
    desvio: o desvio dela corria contra a varredura. O teste vira o inverso — não pode
    sobrar recusa aqui, nem a mensagem que a explicava."""
    svc = _swept_past_row()
    appt, changed = svc.cancel("a1", reason="no-show")
    assert changed and appt.status == CANCELED
    assert appt.cancel_reason == "no-show"

def test_a_no_show_can_actually_be_corrected_end_to_end():
    """The promised path, walked — with the two calls BACK TO BACK.

    And only so. See `test_the_sweep_undoes_the_undo` below: put a listing between them, which
    is what any turn boundary produces, and the path comes apart. This test pins the happy
    ordering and must NOT be read as "the path works" — reading it that way is exactly what let
    me declare #79 finished."""
    svc = _swept_past_row()
    svc.update_status("a1", CONFIRMED)                     # undo the automatic completion
    appt, changed = svc.cancel("a1", reason="no-show")
    assert appt.status == CANCELED and changed
    assert svc.store.get("a1").cancel_reason == "no-show"
    svc.list_appointments(host_id="dr_silva")
    assert svc.store.get("a1").status == CANCELED, "CANCELED is terminal — the sweep leaves it"


def test_the_sweep_undoes_the_undo():
    """The REAL sequence: undo, something lists, and only then cancel. Now green.

    It shipped as `xfail(strict)` in #80 and is unmarked here in the commit that earns it —
    which is the whole contract of a strict xfail: the day it passes, it fails, and somebody
    has to come back and say why. `cancel` accepts a COMPLETED row now, so the detour and its
    race are gone; the sequence below is one call.

    Kept anyway, because the ORDER is the point: `confirm → cancel` adjacent is the only order
    the old code survived, and a test that walks only that order is what let me call the path
    done twice."""
    svc = _swept_past_row()
    svc.update_status("a1", CONFIRMED)                     # the professional undoes it
    svc.list_appointments(host_id="dr_silva")              # …and ANYTHING lists
    svc.cancel("a1", reason="no-show")
    # The OUTCOME, not one route to it: whether the sweep stops re-completing, or `cancel`
    # learns to accept a COMPLETED row, either fix ends here. Asserting the intermediate
    # CONFIRMED instead would pin one implementation and reject the other.
    assert svc.store.get("a1").status == CANCELED, "the no-show never got recorded"
