"""The two listings this PR wires, through the REAL tools — and the guards they must keep feeding.

A read tool's text is not consumed by a machine in the ordinary sense: it is handed to the
SUPEREGO's voicer as "# Data gathered by the executor", so it is, in practice, what a person on
WhatsApp reads. That is why the shape is worth changing at all.

But three things upstream DO parse it, and each of them fails silently rather than loudly:

  * ``cogno_anima.tools.IdProvenanceDispatcher`` refuses ``cancel``/``confirm``/``complete``/
    ``reschedule`` unless the ``appointment_id`` appeared as a SUBSTRING (``wanted in r``) in a
    successful read earlier in the same turn. Tidy the id out of the listing and every write on
    this vertical is refused, with nothing red anywhere.
  * ``cogno_praxis.scheduler.grounding`` reads ``[PENDING]``/``[CONFIRMED]`` and the exact
    sentence ``No appointments found.`` — the second with ``match`` against ``…found\\.$``, so
    nothing may ever be appended to it.
  * ``cogno_host.company_focus`` parses a ONE-HIT ``company_search`` answer with
    ``ast.literal_eval``. A listing must not become parseable and a mapping must not stop being
    one; the pins for that live in ``test_companies_server.py`` and are untouched here.

So these tests assert the new SHAPE and, beside it, the OLD contracts the shape may not break.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.companies import CompanyService, InMemoryCompanyStore
from cogno_praxis.companies.server import build_server as build_companies
from cogno_praxis.render import CHANNEL_ENV
from cogno_praxis.scheduler import Host, InMemoryAppointmentStore, SchedulerService
from cogno_praxis.scheduler.grounding import (
    CONFIRMED_MARK_RE,
    LIST_EMPTY_RE,
    PENDING_MARK_RE,
)
from cogno_praxis.scheduler.server import build_server as build_scheduler

_TODAY = date(2026, 6, 30)

#: A note the tenant writes for itself. It is on the record, it is NOT a chosen field, and a
#: contact must never see it — the negative twin, at the vertical instead of at the renderer.
_PRIVATE_NOTE = "NOTA_INTERNA_QUE_NAO_PODE_SAIR"


@pytest.fixture(autouse=True)
def _whatsapp(monkeypatch):
    """Pin the channel so these assertions are about the LISTING, not about the box's env."""
    monkeypatch.setenv(CHANNEL_ENV, "whatsapp")


def _sched():
    store = InMemoryAppointmentStore()
    store.hosts["dr_a"] = Host("dr_a", "Dra. Sintética", "Clínica Geral")
    store.hosts["dr_b"] = Host("dr_b", "Dr. Fictício", "Ortopedia")
    return build_scheduler(SchedulerService(store, today=lambda: _TODAY))


def _text(res) -> str:
    return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")


async def _book(mcp, host_id, day, time, name, notes=""):
    args = {"host_id": host_id, "date": day, "time": time, "with_name": name}
    if notes:
        args["notes"] = notes
    return _text(await mcp.call_tool("book_appointment", args))


# ── the scheduler listing ────────────────────────────────────────────────────────────
async def test_two_days_group_under_a_bold_header_that_carries_BOTH_date_forms():
    """The spoken half is new information, not decoration.

    Every row used to carry an ISO date and nothing else, so a persona answering "quando é a
    minha consulta?" had to derive the weekday itself — the arithmetic ``format_date`` exists
    to remove. The ISO half is what ``check_availability``/``reschedule_appointment`` are
    computed from, and it is hoisted into the header because it is constant within a day."""
    mcp = _sched()
    await _book(mcp, "dr_a", "2026-07-01", "09:00", "Contacto Um")
    await _book(mcp, "dr_a", "2026-07-01", "10:00", "Contacto Dois")
    await _book(mcp, "dr_b", "2026-07-02", "09:00", "Contacto Três")
    out = _text(await mcp.call_tool("list_appointments", {}))

    heads = [ln for ln in out.splitlines() if ln.startswith("*")]
    assert heads == ["*quarta-feira, 1 de julho de 2026 (2026-07-01)*",
                     "*quinta-feira, 2 de julho de 2026 (2026-07-02)*"]
    assert out.count("2026-07-01") == 1, "the ISO date is hoisted ONCE, not repeated per row"
    assert sum(ln.startswith("- ") for ln in out.splitlines()) == 3


async def test_one_appointment_gets_no_header_line_and_still_names_its_day():
    mcp = _sched()
    await _book(mcp, "dr_a", "2026-07-01", "09:00", "Contacto Um")
    out = _text(await mcp.call_tool("list_appointments", {}))
    assert "\n" not in out and not out.startswith("- ")
    assert "quarta-feira" in out and "2026-07-01" in out and "09:00" in out


async def test_the_appointment_id_survives_because_a_guard_greps_for_it():
    """``IdProvenanceDispatcher`` does ``wanted in r`` over this very text."""
    mcp = _sched()
    booked = await _book(mcp, "dr_a", "2026-07-01", "09:00", "Contacto Um")
    appt_id = booked.split()[1].rstrip(":")
    out = _text(await mcp.call_tool("list_appointments", {}))
    assert appt_id in out
    assert out.rstrip().endswith(appt_id), "and it goes LAST, after the facts a person reads"


async def test_the_status_bracket_survives_because_the_grounding_rules_grep_for_it():
    mcp = _sched()
    await _book(mcp, "dr_a", "2026-07-01", "09:00", "Contacto Um")     # dr_a auto-confirms? no
    out = _text(await mcp.call_tool("list_appointments", {}))
    assert PENDING_MARK_RE.search(out) or CONFIRMED_MARK_RE.search(out)
    assert "[PENDING]" in out or "[CONFIRMED]" in out


async def test_an_empty_listing_is_the_exact_sentence_the_grounding_rule_matches():
    """``LIST_EMPTY_RE`` uses ``match`` against ``…found\\.$``: nothing may follow it.

    The sentence now has ONE definition — ``render_block``'s ``empty`` — where it used to be a
    literal in the tool AND a regex in the rules."""
    out = _text(await _sched().call_tool("list_appointments", {}))
    assert out == "No appointments found."
    assert LIST_EMPTY_RE.match(out.strip())


async def test_a_field_that_was_not_chosen_does_not_reach_the_contact():
    """The negative twin at the vertical: an internal note is on the row and is not a column."""
    mcp = _sched()
    await _book(mcp, "dr_a", "2026-07-01", "09:00", "Contacto Um", notes=_PRIVATE_NOTE)
    out = _text(await mcp.call_tool("list_appointments", {}))
    assert "Contacto Um" in out
    assert _PRIVATE_NOTE not in out


async def test_a_row_whose_date_cannot_be_read_keeps_its_date_and_is_not_swallowed():
    """A header that cannot be spoken is still a header. The row must never lose its day."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_a"] = Host("dr_a", "Dra. Sintética", "Clínica Geral")
    svc = SchedulerService(store, today=lambda: _TODAY)
    mcp = build_scheduler(svc)
    booked = await _book(mcp, "dr_a", "2026-07-01", "09:00", "Contacto Um")
    appt_id = booked.split()[1].rstrip(":")
    store.appointments[appt_id].date = "não é uma data"
    out = _text(await mcp.call_tool("list_appointments", {}))
    assert "não é uma data" in out and appt_id in out


# ── the companies listing ────────────────────────────────────────────────────────────
def _companies():
    svc = CompanyService(InMemoryCompanyStore())
    return svc, build_companies(svc)


async def _ctext(mcp, tool, **args) -> str:
    blocks, _ = await mcp.call_tool(tool, args)
    return "\n".join(b.text for b in blocks if getattr(b, "type", None) == "text")


async def test_a_company_listing_emphasises_the_name_and_keeps_every_chosen_field():
    """No grouping key and heterogeneous fields, so the labels STAY — see ``_COMPANY_FIELDS``.
    What the pattern gives this vertical is the emphasis and the separator, not the compression."""
    svc, mcp = _companies()
    svc.register("Padaria Sintética", cnpj="11.222.333/0001-81", segment="padaria artesanal",
                 visual_identity="paleta terrosa", guidelines="tom caloroso", identity_id="u1")
    out = await _ctext(mcp, "list_companies", identity_id="u1", role="ADMIN")
    assert out.startswith("*Padaria Sintética*"), "one row: no bullet, no header, name in bold"
    for expected in ("CNPJ", "11222333000181", "segmento padaria artesanal",
                     "identidade visual: paleta terrosa", "diretrizes: tom caloroso",
                     "id: padaria-sintetica"):
        assert expected in out, expected
    assert " — " not in out and " · " in out


async def test_a_company_listing_does_not_leak_who_registered_the_row():
    """``created_by_user_id`` is on the record, is not a chosen field, and is an identity."""
    svc, mcp = _companies()
    svc.register("Padaria Sintética", identity_id="AN_IDENTITY_NOBODY_ASKED_FOR")
    out = await _ctext(mcp, "list_companies", identity_id="AN_IDENTITY_NOBODY_ASKED_FOR",
                       role="ADMIN")
    assert "Padaria Sintética" in out
    assert "AN_IDENTITY_NOBODY_ASKED_FOR" not in out


async def test_several_companies_become_bullets_under_the_sentence_that_asks_which_one():
    svc, mcp = _companies()
    svc.register("Padaria Sintética", identity_id="u1")
    svc.register("Padaria Imaginária", identity_id="u1")
    out = await _ctext(mcp, "company_search", query="Padaria", identity_id="u1", role="ADMIN")
    lines = out.splitlines()
    assert lines[0].startswith("2 companies match") and "none was selected" in lines[0]
    assert lines[1].startswith("- *") and lines[2].startswith("- *")


async def test_an_empty_company_listing_still_says_so():
    _, mcp = _companies()
    out = await _ctext(mcp, "list_companies", identity_id="u1", role="ADMIN")
    assert out.startswith("No companies are registered yet.")


async def test_the_day_headers_come_out_in_date_order_even_after_a_reschedule():
    """The defect the grouping introduces, and the 48-call probe found (call 027).

    The store returns rows in its own order and a rescheduled appointment keeps its old
    position. While every line carried its own ISO date that was invisible; grouped under day
    headers it reads as 6 July, then 1 July, then 2 July — worse than the flat form."""
    mcp = _sched()
    booked = await _book(mcp, "dr_a", "2026-07-01", "09:00", "Contacto Um")
    appt_id = booked.split()[1].rstrip(":")
    await _book(mcp, "dr_a", "2026-07-02", "09:00", "Contacto Dois")
    await mcp.call_tool("reschedule_appointment",
                        {"appointment_id": appt_id, "new_date": "2026-07-06",
                         "new_time": "11:00"})
    out = _text(await mcp.call_tool("list_appointments", {"include_history": True}))
    heads = [ln for ln in out.splitlines() if ln.startswith("*")]
    assert heads == ["*quinta-feira, 2 de julho de 2026 (2026-07-02)*",
                     "*segunda-feira, 6 de julho de 2026 (2026-07-06)*"]
