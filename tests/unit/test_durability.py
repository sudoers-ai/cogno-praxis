"""Per-vertical graph-durability vetoes: each vertical flags ONLY its own domain's perishable
relations; durable who-is-who relations always pass. The generic signals (dates, generic
concepts) are the host core's job and are NOT tested here."""

from cogno_praxis.bookkeeper.durability import is_perishable_edge as book_perishable
from cogno_praxis.scheduler.durability import is_perishable_edge as sched_perishable


def test_scheduler_flags_its_own_perishable_relations():
    for rel in ("HAS_APPOINTMENT", "APPOINTMENT", "BLOCKED_DATE", "IS_BOOKED",
                "RESCHEDULED_TO", "AGENDAMENTO", "TEM_CONSULTA", "MARCADO_COM"):
        assert sched_perishable("A", "B", rel), rel


def test_scheduler_keeps_durable_relations():
    for rel in ("WORKS_AT", "SPECIALTY", "REFERS_TO", "EMPLOYS", "HAS_CONDITION", "PREFERS"):
        assert not sched_perishable("A", "B", rel), rel


def test_scheduler_does_not_flag_financial_relations():
    # cross-vertical isolation: the scheduler must NOT veto bookkeeper state (that's the
    # bookkeeper vertical's job, active only for a BOOKKEEPER turn).
    assert not sched_perishable("Cliente", "R$ 500", "HAS_BALANCE")
    assert not sched_perishable("Ana", "fatura", "PAID")


def test_bookkeeper_flags_its_own_perishable_relations():
    for rel in ("HAS_BALANCE", "PAID", "UNPAID", "INVOICE_STATUS", "OWES", "IS_OVERDUE",
                "TRANSACTION", "SALDO", "FATURA_PENDENTE", "VENCIMENTO"):
        assert book_perishable("A", "B", rel), rel


def test_bookkeeper_keeps_durable_relations():
    for rel in ("EMPLOYS", "OWNS", "IS_CLIENT_OF", "WORKS_AT", "MANAGES"):
        assert not book_perishable("A", "B", rel), rel


def test_bookkeeper_does_not_flag_scheduling_relations():
    assert not book_perishable("Dr", "Ana", "HAS_APPOINTMENT")
