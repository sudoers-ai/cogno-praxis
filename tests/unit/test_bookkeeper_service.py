"""Unit tests for BookkeeperService (in-memory store) — recording, role visibility, removal."""

from datetime import date

import pytest

from cogno_praxis.bookkeeper.engine import BookkeeperError
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore


def _svc():
    return BookkeeperService(InMemoryBookkeeperStore(), today=lambda: date(2026, 7, 10))


def test_add_income_records_and_creates_client():
    svc = _svc()
    tx = svc.add_income("corte de cabelo", "R$ 50,00", "emp-1", client_name="João")
    assert tx.kind == "income" and tx.amount == 50.0 and tx.tx_date == "2026-07-10"
    assert tx.client_name == "João"
    assert [c["name"] for c in svc.list_clients()] == ["João"]


def test_add_outcome_and_summary_net():
    svc = _svc()
    svc.add_income("serviço", 200, "emp-1")
    svc.add_outcome("luz", 80, "emp-1")
    s = svc.get_summary("emp-1", "EMPLOYEE")
    assert s["total_income"] == 200.0 and s["total_outcome"] == 80.0 and s["net"] == 120.0
    assert s["income_count"] == 1 and s["outcome_count"] == 1


def test_add_rejects_bad_amount_and_empty_description():
    svc = _svc()
    with pytest.raises(BookkeeperError):
        svc.add_income("x", "-5", "emp-1")
    with pytest.raises(BookkeeperError):
        svc.add_outcome("   ", 10, "emp-1")


def test_role_visibility_employee_sees_own_oversight_sees_all():
    svc = _svc()
    svc.add_income("a", 100, "emp-1")
    svc.add_income("b", 200, "emp-2")

    # EMPLOYEE emp-1 sees only their own
    own = svc.get_summary("emp-1", "EMPLOYEE")
    assert own["total_income"] == 100.0 and own["income_count"] == 1

    # oversight sees the whole scope regardless of the identity passed
    allv = svc.get_summary("emp-1", "SUPERVISOR")
    assert allv["total_income"] == 300.0 and allv["income_count"] == 2


def test_search_is_role_scoped():
    svc = _svc()
    svc.add_outcome("aluguel", 1000, "emp-1")
    svc.add_outcome("aluguel", 2000, "emp-2")
    assert len(svc.search("aluguel", "emp-1", "EMPLOYEE")) == 1
    assert len(svc.search("aluguel", "emp-1", "ADMIN")) == 2


def test_remove_by_search_removes_own_most_recent_only():
    svc = _svc()
    svc.add_outcome("internet março", 100, "emp-1")
    svc.add_outcome("internet abril", 120, "emp-1")
    svc.add_outcome("internet", 999, "emp-2")   # a different identity's record (isolation check)

    removed = svc.remove_by_search("internet", "emp-1")
    assert removed is not None and removed["amount"] == 120.0   # most recent of emp-1
    # emp-1 still has the older one; emp-2's is untouched (no cross-identity deletion)
    assert svc.get_summary("emp-1", "EMPLOYEE")["outcome_count"] == 1
    assert svc.get_summary("emp-2", "EMPLOYEE")["outcome_count"] == 1
    assert svc.remove_by_search("nao-existe", "emp-1") is None


def test_usage_and_help_notes_are_scoped_messages():
    svc = _svc()
    assert "host" in svc.usage_note().lower()
    assert "bookkeeper" in svc.help_note().lower()
