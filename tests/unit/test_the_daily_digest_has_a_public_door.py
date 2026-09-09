"""The daily digest is rendered OUT of process, so it needs a name we promise.

``cogno-host``'s ``workers/sofia_daily.py`` is a sweep, not a turn: it never builds an MCP
server, so it renders the professor's digest itself. Until now it did that by importing
``_daily_checks_text`` and ``_status_args`` — **two private names, across a pinned commit SHA.**

A ``_`` name is this library promising nothing. Renaming one is an ordinary refactor we are
entitled to make, and the consumer's pin-bump PR does not touch the import that breaks. What it
costs over there is not a red build, which is the part worth writing down: that import sits
inside a per-tenant ``except Exception`` whose warning names the TENANT and never the cause, so
every professor silently stops being messaged and the sweep still exits 0.

So this file pins the door, in both halves:

* the public names EXIST and are exported from ``cogno_praxis.coordinator`` (the vertical's
  declared surface — a name that is importable but absent from ``__all__`` is a promise nobody
  can read);
* they are the SAME OBJECTS as the implementations, not a second rendering of the same idea —
  a copy would drift, and the second copy is always the one nobody tests.

What this deliberately does NOT do is rename anything. The definitions and their six call sites
in ``build_server`` are untouched, so the commit adds a promise and moves no code; the private
names stay valid for a consumer pinned to a revision older than this one, which is every
consumer until its own pin advances.
"""

from __future__ import annotations

from datetime import date

from cogno_praxis import coordinator as vertical
from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    daily_checks_text,
    status_args,
)
from cogno_praxis.coordinator.server import _daily_checks_text, _status_args

_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
_RULES = (
    f"SPREADSHEETS:\nDSA={_SID}\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
    'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n'
)


def _service(today: date) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    rows = [[today.strftime("%d/%m/%Y"), "SEG", "Sofia", "Redes", "S1"]]
    store.put(_SID, "Secretaria", [[""] * 5] * 3 + [list(_HEADER)] + rows)
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: today)


def test_the_public_names_are_on_the_verticals_declared_surface():
    """Importable AND declared. ``__all__`` is what a refactor author reads before renaming."""
    assert "daily_checks_text" in vertical.__all__
    assert "status_args" in vertical.__all__
    assert vertical.daily_checks_text is daily_checks_text
    assert vertical.status_args is status_args


def test_the_public_name_IS_the_implementation_not_a_second_copy():
    """An alias, on purpose. A public wrapper that re-renders would be a second copy of the
    digest, and the second copy is always the one nobody tests — which is the failure this
    door exists to close, not a new instance of it."""
    assert daily_checks_text is _daily_checks_text
    assert status_args is _status_args


def test_the_door_actually_renders_the_day():
    """The promise is worth nothing if it points at something that cannot be called: the two
    names are used TOGETHER (``status_args`` supplies the keyword arguments the renderer takes),
    which is exactly how the out-of-process consumer calls them."""
    today = date(2026, 9, 7)
    svc = _service(today)
    checks = svc.daily_checks(role="EMPLOYEE", identity_label="Sofia")
    assert not checks.empty, "the fixture stopped producing a day to render"

    rendered = daily_checks_text(checks, **status_args(svc))
    assert "Redes" in rendered
    assert rendered == _daily_checks_text(checks, **_status_args(svc))
