"""The log lines that carried a name, an id or somebody's text — what they say now, at run time.

Read by AST on ``5e7a452``, 12 of the package's 19 log calls formatted a person's name, a
spreadsheet's id, a scope, a sentence of the tenant's rules or an exception's message.
``test_logs_carry_no_third_party_text.py`` holds the CLASS, by AST. This file drives each of
those lines with the thing it used to print:

* the line still comes out — at its level, with its new fields (compared whole, so a field
  that goes missing fails too);
* no record of the package, at any level, holds a byte of the name, the id or the text.

It imports nothing the change added, so it runs on the tree before it. There the 13 twins
were red, each because the value was in the log, and the 3 controls green. Every name and id
here is invented.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
)
from cogno_praxis.coordinator import config as config_module
from tests.unit.test_coordinator_pay import (AA, BB, ME, _BASE_RULES, _HOURS_AA, _HOURS_BB,
                                             _PAY_RULES, _SCHEDULE_AA, _SCHEDULE_BB)
from tests.unit.test_pay_declared_in_prose import TENANT_RULES_IN_PROSE
from tests.unit.test_pay_declared_in_prose import _BASE as PROSE_BASE
from tests.unit.test_two_spellings_are_one_professor import _TAB_HEADER, _blocks, _class
from tests.unit.test_two_spellings_are_one_professor import _svc as faculty_svc

SENTINEL = "ZQX7"
KEY_AA, KEY_BB = "Turma AA_01", "Turma BB_02"            # what _BASE_RULES calls the two sheets
IBOPE_RULES = 'TAB_IBOPE: "Resultados IBOPE"\nCOLUMN_IBOPE: "Resultado"\n'


def sha(value: str) -> str:
    """The digest a line carries — written out, so this file needs nothing of the change."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


class Captured:
    """Every record the package emitted, at every level, formatted as a handler would."""

    def __init__(self, caplog):
        self._caplog = caplog

    @property
    def lines(self) -> "list[str]":
        return [r.getMessage() + (f"\n{r.exc_text or ''}" if r.exc_info else "")
                for r in self._caplog.records if r.name.startswith("cogno_praxis")]

    def of(self, event: str) -> "list[str]":
        return [ln for ln in self.lines if f"event={event} " in f"{ln} "]

    def clean(self, *needles: str) -> None:
        for needle in needles:
            leaked = [ln for ln in self.lines if needle.casefold() in ln.casefold()]
            assert not leaked, f"{needle!r} reached the log: {leaked}"


@pytest.fixture
def log(caplog, monkeypatch):
    monkeypatch.setattr(config_module, "_PROSE_WARNED", set())
    with caplog.at_level(logging.DEBUG, logger="cogno_praxis"):
        yield Captured(caplog)


class _Down(Exception):
    """What an HTTP client raises: the request URL — and with it the id — in its message."""

    def __init__(self, sheet_id: str, status: "int | None") -> None:
        super().__init__(f"GET https://sheets.invalid/v4/spreadsheets/{sheet_id}/values "
                         f"failed {SENTINEL}")
        if status is not None:
            self.response = type("Response", (), {"status_code": status})()


def _service(rules: str, *, broken_tab: str = "", status: "int | None" = None,
             hours_aa: "list[list[str]] | None" = None) -> CoordinatorService:
    class Store(InMemorySpreadsheetStore):
        def read_range(self, sheet_id, tab, a1_range):
            if tab == broken_tab and sheet_id == AA:
                raise _Down(sheet_id, status)
            return super().read_range(sheet_id, tab, a1_range)

    store = Store()
    store.put(AA, "Secretaria", _SCHEDULE_AA)
    store.put(BB, "Secretaria", _SCHEDULE_BB)
    store.put(AA, "Informacoes Adicionais", hours_aa or _HOURS_AA)
    store.put(BB, "Informacoes Adicionais", _HOURS_BB)
    store.put(AA, "Resultados IBOPE", [["Professor", "Resultado"], [ME, "85%"]])
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: date(2026, 9, 1))


def _unreadable(tab: str, status: int = 0) -> str:
    return (f"stage=coordinator event=sheet_unreadable tab={tab} sheet_sha={sha(KEY_AA)} "
            f"error=_Down status={status}")


# ── the two names ──────────────────────────────────────────────────────────────────────────

def test_two_rows_that_share_an_address_are_counted_and_nobody_is_named(log):
    """The line of the brief. Two colleagues on one mailbox, the names not corroborating: NOT
    joined, each block names the other — and the log says one pair, not who."""
    faculty = [_TAB_HEADER,
               ["Estatística", "40", "Nuno Prata", "secretaria@example.edu"],
               ["Redes", "40", "Nuno Ferraz", "secretaria@example.edu"]]
    fac, by = _blocks(faculty_svc([_class("02", "Nuno Prata"), _class("09", "Nuno Ferraz")],
                                  faculty))
    assert by["Nuno Prata"].maybe_same == ("Nuno Ferraz",)        # the tool still says who
    log.clean("Nuno", "Prata", "Ferraz", "secretaria@", "example.edu")
    lines = log.of("faculty_names_not_joined")
    assert lines and set(lines) == {
        "stage=coordinator event=faculty_names_not_joined pairs=1 — they share an e-mail "
        "address and neither name is the other written out; check the professors tab"}


def test_three_rows_on_one_address_are_three_pairs(log):
    faculty = [_TAB_HEADER,
               ["Estatística", "40", "Nuno Prata", "secretaria@example.edu"],
               ["Redes", "40", "Nuno Ferraz", "secretaria@example.edu"],
               ["Álgebra", "40", "Lia Cortes", "secretaria@example.edu"]]
    _blocks(faculty_svc([_class("02", "Nuno Prata")], faculty))
    log.clean("Nuno", "Prata", "Ferraz", "Cortes")
    assert all("pairs=3 " in ln for ln in log.of("faculty_names_not_joined"))
    assert log.of("faculty_names_not_joined")


def test_rows_that_are_one_person_written_two_ways_log_nothing(log):
    """The control: a shared address the names DO corroborate is a join, and it is silent."""
    faculty = [_TAB_HEADER,
               ["Estatística", "40", "Íris Calheiros Amado", "iris@example.edu"],
               ["Redes", "40", "Íris Calheiros", "iris@example.edu"]]
    _blocks(faculty_svc([_class("02", "Íris Calheiros")], faculty))
    assert log.of("faculty_names_not_joined") == []
    log.clean("Calheiros")


# ── the spreadsheet's id, its name, and the store's exception ──────────────────────────────

def test_a_schedule_that_cannot_be_read_logs_the_digest_of_its_key_and_the_class(log):
    svc = _service(_BASE_RULES + _PAY_RULES, broken_tab="Secretaria", status=404)
    svc.estimate_professor_pay(identity_label=ME)
    log.clean(AA, KEY_AA, "AA_01", SENTINEL, "sheets.invalid", "Secretaria")
    assert log.of("sheet_unreadable") and set(log.of("sheet_unreadable")) == {
        _unreadable("schedule", 404)}


def test_an_hours_tab_that_cannot_be_read_says_hours(log):
    svc = _service(_BASE_RULES + _PAY_RULES, broken_tab="Informacoes Adicionais")
    svc.estimate_professor_pay(identity_label=ME)
    log.clean(AA, KEY_AA, SENTINEL, "Informacoes")
    assert _unreadable("hours") in log.of("sheet_unreadable")
    assert {ln.split("tab=")[1].split()[0] for ln in log.of("sheet_unreadable")} <= {
        "hours", "professors"}


def test_an_ibope_tab_that_cannot_be_read_says_ibope(log):
    svc = _service(_BASE_RULES + _PAY_RULES + IBOPE_RULES, broken_tab="Resultados IBOPE")
    svc.estimate_professor_pay(identity_label=ME)
    log.clean(AA, KEY_AA, SENTINEL, "Resultados")
    assert _unreadable("ibope") in log.of("sheet_unreadable")


def test_a_professors_tab_that_cannot_be_read_says_professors(log):
    svc = _service(_BASE_RULES + _PAY_RULES, broken_tab="Informacoes Adicionais")
    svc.estimate_faculty_pay(period="2026-09", identity_label="Coordenação", role="SUPERVISOR")
    log.clean(AA, KEY_AA, SENTINEL, "Informacoes")
    assert _unreadable("professors") in log.of("sheet_unreadable")


def test_a_sheet_that_reads_logs_nothing_about_it(log):
    _service(_BASE_RULES + _PAY_RULES).estimate_professor_pay(identity_label=ME)
    assert log.of("sheet_unreadable") == []


# ── what the tenant typed ──────────────────────────────────────────────────────────────────

def test_an_hours_column_that_is_not_on_the_tab_is_named_by_its_role(log):
    rules = _BASE_RULES + f'COLUMN_HOURS: "Horas {SENTINEL}"\n' + _PAY_RULES.split("\n", 1)[1]
    _service(rules).estimate_professor_pay(identity_label=ME)
    log.clean(SENTINEL, "Informacoes", KEY_AA, KEY_BB, "Disciplina")
    assert set(log.of("hours_columns_missing")) == {
        f"stage=coordinator event=hours_columns_missing sheet_sha={sha(key)} missing=hours — "
        "the workload context is skipped, the estimate is unaffected" for key in (KEY_AA, KEY_BB)}


def test_a_discipline_with_no_readable_total_is_named_by_its_row(log):
    hours = [list(_HOURS_AA[0]), list(_HOURS_AA[1]),
             [f"Topicos {SENTINEL}", "a combinar", ME, "alfa@exemplo.invalid"]]
    _service(_BASE_RULES + _PAY_RULES, hours_aa=hours).estimate_professor_pay(identity_label=ME)
    log.clean(SENTINEL, "Topicos", "a combinar", KEY_AA)
    assert set(log.of("hours_unreadable")) == {
        f"stage=coordinator event=hours_unreadable sheet_sha={sha(KEY_AA)} row=3"}
    assert all(r.levelno == logging.DEBUG for r in log._caplog.records
               if "event=hours_unreadable" in r.getMessage())


def test_a_spreadsheets_entry_that_is_not_an_id_logs_the_digest_of_its_key(log):
    cfg = CoordinatorConfig(f"SPREADSHEETS:\nTurma {SENTINEL} = short-{SENTINEL}\n"
                            f"Turma AA_01 = {AA}\n")
    assert list(cfg.spreadsheets) == ["Turma AA_01"]
    log.clean(SENTINEL, "Turma")
    assert log.of("spreadsheet_entry_skipped") == [
        f"stage=coordinator event=spreadsheet_entry_skipped reason=not_an_id "
        f"sheet_sha={sha(f'Turma {SENTINEL}')} value_len={len('short-' + SENTINEL)}"]


def test_pay_figures_in_prose_log_the_keys_and_a_count(log):
    CoordinatorConfig(PROSE_BASE + TENANT_RULES_IN_PROSE)
    CoordinatorConfig(PROSE_BASE + TENANT_RULES_IN_PROSE)          # once per configuration
    log.clean("R$", "120,00", "30,00", "por hora", "Adicional", "Workshop", "30%")
    lines = log.of("pay_figures_in_prose")
    assert len(lines) == 1
    assert lines[0].startswith(
        "stage=coordinator event=pay_figures_in_prose "
        "keys=PAY_RATE_PER_HOUR,HOURS_PER_CLASS,IBOPE_BONUS,IBOPE_MIN_RESPONSE_PCT excerpts=")
    assert int(lines[0].split("excerpts=")[1].split()[0]) >= 4


# ── the scheduler ──────────────────────────────────────────────────────────────────────────

def test_a_holiday_calendar_that_fails_logs_the_class_of_the_error(log, monkeypatch):
    holidays = pytest.importorskip("holidays")
    from cogno_praxis.scheduler import engine

    def boom(*args, **kwargs):
        raise NotImplementedError(f"no calendar for {args} {SENTINEL}")

    monkeypatch.setattr(holidays, "country_holidays", boom)
    # what a tenant's configuration can be: anything — here a sentence with a street in it
    country, state = f"Brasil, {SENTINEL} 12", f"Rua {SENTINEL}, 7"
    assert engine._load_holiday_set(country, state) == {}
    assert engine._load_holiday_set(country, None) == {}
    log.clean(SENTINEL, "no calendar", "Brasil", "Rua")
    assert log.of("holidays_unavailable") == [
        f"stage=scheduler event=holidays_unavailable country_sha={sha(country)} "
        f"state_sha={state_sha} error=NotImplementedError — holiday filtering is off"
        for state_sha in (sha(state), "-")]


def test_an_index_that_cannot_be_built_logs_the_sqlstate_and_the_class(log):
    psycopg = pytest.importorskip("psycopg")
    from cogno_praxis.scheduler.stores import postgres

    class Conn:
        def execute(self, *args, **kwargs):
            raise psycopg.errors.LockNotAvailable(
                f"canceling statement: row (tenant-{SENTINEL}, 12, 2026-09-01, 10:00)")

    postgres._ensure_slot_uniqueness(Conn())
    log.clean(SENTINEL, "tenant-", "10:00")
    assert log.of("slot_uniqueness_unavailable") == [
        "stage=scheduler event=slot_uniqueness_unavailable reason=55P03 error=LockNotAvailable"]


def test_an_empty_catalog_that_is_refused_logs_the_digest_of_the_scope(log):
    pytest.importorskip("psycopg")
    from cogno_praxis.scheduler.stores import postgres

    scope = f"tenant-{SENTINEL}:5511970001111"

    class Conn:
        def execute(self, *args, **kwargs):
            return type("Cursor", (), {"fetchone": lambda self: (3,)})()

    store = object.__new__(postgres.PgAppointmentStore)
    store._conn, store._scope = Conn(), scope
    store.sync_hosts([])
    log.clean(SENTINEL, "tenant-", "970001111")
    lines = log.of("sync_hosts_empty_refused")
    assert len(lines) == 1 and lines[0].startswith(
        f"stage=scheduler event=sync_hosts_empty_refused scope_sha={sha(scope)} kept=3 — ")


def test_control_the_capture_sees_a_line_that_carries_a_name(log):
    """``clean`` over an empty capture passes anything. This is the line as it was."""
    logging.getLogger("cogno_praxis.coordinator.service").warning(
        "coordinator: %r and %r share an e-mail address", "Nuno Prata", "Nuno Ferraz")
    with pytest.raises(AssertionError, match="reached the log"):
        log.clean("Ferraz")
    with pytest.raises(AssertionError, match="reached the log"):
        log.clean("nuno")                                      # folded, like a reader's grep
