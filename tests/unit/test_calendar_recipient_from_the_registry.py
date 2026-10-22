"""The calendar's recipient: the professors tab first, the institution's REGISTRY second (P5).

**The defect, measured on a production tenant (2026-10-22).** A coordinator asked to mail a
professor's classes as a calendar. The professors tab had no e-mail for him, so the tool refused
("there is no e-mail address on file"). He HAS an address — in the host's own registry of
identities, which the tool never reads for anybody but the caller. The calendar never went.

**The rule.**

* the professors tab's address, when there is one — unchanged, and the proposal is today's text;
* otherwise, for the COORDINATION only (an oversight role), the address of the registry
  identity whose label designates THAT professor — by the very match ``_resolve_professor`` uses
  (the one ``email_context`` used to resolve a recipient's label to the schedule, until #181):
  folded substring over every spelling the tenant's data carries, exactly ONE person or none.
  The proposal then SAYS the address came from the registry;
* two registry entries for that professor with DIFFERENT addresses → a refusal that names the
  labels, never a pick;
* nothing in the registry → today's refusal, byte for byte.

The registry arrives as ``identity_directory`` — injected by the host, never offered to the
model — and none of its addresses may reach a log line, or a reply, unless it is the one used.

Names, addresses and figures below are invented.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    RecordingCalendarSender,
)
from cogno_praxis.coordinator.server import build_server

_RULES = (
    "SPREADSHEETS:\nDE_09=1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A1:E200"\n'
    'TAB_PROFESSORS: "Info"\nRANGE_PROFESSORS: "A1:C50"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
    'FIXED_COLUMNS: "Data, Dia"\n'
)
_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
_ROWS = [
    ["01/09/2026", "Ter", "Otelo Brisa", "NoSQL", "101"],
    ["08/09/2026", "Ter", "Otelo Brisa", "NoSQL", "101"],
    ["02/09/2026", "Qua", "Cira Penumbra", "Redes", "102"],
    ["03/09/2026", "Qui", "Lia Corvelo", "Redes", "103"],
    ["04/09/2026", "Sex", "Otília Fontoura", "Redes", "104"],
]
#: The professors tab: Otelo is DECLARED, with no address. Cira has one.
_PROFS = [["Professor", "e-mail"], ["Otelo Brisa", ""], ["Cira Penumbra", "cira@aba.test"]]

REGISTRY_ADDRESS = "otelo@registo.test"
#: Another person's address in the same registry. It must never appear anywhere.
SENTINEL = "sentinela-cira@registo.test"
_DIRECTORY = [{"label": "Otelo Brisa", "email": REGISTRY_ADDRESS},
              {"label": "Cira Penumbra", "email": SENTINEL}]
_SUP = {"role": "SUPERVISOR", "identity_label": "Sofia", "month": "2026-09"}
_TODAYS_REFUSAL = ("ERROR: There is no e-mail address on file for Otelo Brisa, so there is "
                   "nowhere to send the calendar. This is a missing address, not a failure — ask "
                   "them to have it recorded. Nothing was sent.")


def _service(*, profs=None, rows=None) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [list(_HEADER)] + [list(r) for r in (rows or _ROWS)])
    store.put(_SID, "Info", [list(r) for r in (profs if profs is not None else _PROFS)])
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 8, 31))


def _text(res) -> str:
    return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")


def _call(tool: str, args: dict, *, svc=None, sender=None) -> str:
    """Through the REAL server door — the one the host's bridge calls."""
    mcp = build_server(svc or _service(), sender=sender or RecordingCalendarSender())

    async def run():
        try:
            return _text(await mcp.call_tool(tool, args))
        except Exception as exc:  # noqa: BLE001 — a mutating tool RAISES its refusal
            return f"RAISED: {exc}"
    return asyncio.run(run())


def _preview(directory=None, *, svc=None, **kw) -> str:
    args = {"professor": "Otelo Brisa", **_SUP, **kw}
    if directory is not None:
        args["identity_directory"] = directory
    return _call("preview_schedule_to_calendar", args, svc=svc)


def _proposal_line(text: str) -> str:
    hits = [ln for ln in text.splitlines() if ln.startswith("PROPOSAL:")]
    assert len(hits) == 1, text
    return hits[0]


# ── 1. THE TWIN ────────────────────────────────────────────────────────────────────────────

def test_twin_the_preview_uses_the_registry_and_says_so():
    """No address on the tab, one in the registry: the proposal names it and SAYS where it came
    from, on the one line the reply relays. On the base: today's refusal."""
    out = _preview(_DIRECTORY)
    assert out.startswith("NOT SENT"), out
    assert _proposal_line(out) == (
        f"PROPOSAL: 2 class(es) of September 2026 → {REGISTRY_ADDRESS} "
        f"(from the Cogno registry — the professors tab has no address for Otelo Brisa)")
    assert SENTINEL not in out


def test_twin_the_send_mails_the_registry_address():
    sender = RecordingCalendarSender()
    out = _call("send_schedule_to_calendar",
                {"professor": "Otelo Brisa", **_SUP, "identity_directory": _DIRECTORY},
                sender=sender)
    assert out.startswith("SENT: 2 class(es) e-mailed to " + REGISTRY_ADDRESS), out
    assert [m["to"] for m in sender.sent] == [REGISTRY_ADDRESS]
    assert SENTINEL not in out


def test_the_service_says_which_source_answered():
    """``(address, source)`` — the closed alphabet the proposal reads. Read off the module by
    attribute, so on the base this fails on the assertion that names what is missing rather than
    on an import."""
    from cogno_praxis.coordinator import service as service_module
    assert hasattr(service_module, "RECIPIENT_FROM_REGISTRY"), "no source alphabet"
    RECIPIENT_FROM_REGISTRY = service_module.RECIPIENT_FROM_REGISTRY
    RECIPIENT_FROM_SHEET = service_module.RECIPIENT_FROM_SHEET
    svc = _service()
    assert svc.calendar_recipient(professor="Otelo Brisa", role="SUPERVISOR",
                                  identity_label="Sofia",
                                  identity_directory=_DIRECTORY) == (REGISTRY_ADDRESS,
                                                                     RECIPIENT_FROM_REGISTRY)
    assert svc.calendar_recipient(professor="Cira Penumbra", role="SUPERVISOR",
                                  identity_label="Sofia",
                                  identity_directory=_DIRECTORY) == ("cira@aba.test",
                                                                     RECIPIENT_FROM_SHEET)
    p = svc.preview_schedule_to_calendar(sender=RecordingCalendarSender(), professor="Otelo Brisa",
                                         identity_directory=_DIRECTORY, **_SUP)
    assert (p.recipient, p.source) == (REGISTRY_ADDRESS, RECIPIENT_FROM_REGISTRY)


# ── 2. THE CONTROLS ────────────────────────────────────────────────────────────────────────

def test_control_the_professors_tab_wins_and_the_text_is_todays():
    """An address on the tab is used, and the proposal is the text of before byte for byte —
    the registry is not even consulted."""
    profs = [["Professor", "e-mail"], ["Otelo Brisa", "otelo@aba.test"]]
    com = _preview(_DIRECTORY, svc=_service(profs=profs))
    sem = _preview(None, svc=_service(profs=profs))
    assert com == sem
    assert _proposal_line(com) == "PROPOSAL: 2 class(es) of September 2026 → otelo@aba.test"
    assert REGISTRY_ADDRESS not in com and SENTINEL not in com


def test_control_nobody_in_the_registry_is_todays_refusal():
    only_another = [{"label": "Cira Penumbra", "email": SENTINEL}]
    assert _preview(only_another) == _TODAYS_REFUSAL
    assert _preview(None) == _TODAYS_REFUSAL
    assert _preview([]) == _TODAYS_REFUSAL


_TWO = [{"label": "Otelo Brisa", "email": REGISTRY_ADDRESS},
        {"label": "Otelo", "email": "outro-otelo@registo.test"},
        {"label": "Cira Penumbra", "email": SENTINEL}]


def test_control_two_entries_with_different_addresses_never_pick_one():
    """Two registry labels that both designate Otelo, two addresses: nothing is proposed,
    nothing is sent, and no address of the registry is shown. True in both worlds — on the base
    because the registry is never read; here because the refusal below refuses."""
    out = _preview(_TWO)
    assert out.startswith("ERROR:") and "Nothing was sent" in out, out
    for address in (REGISTRY_ADDRESS, "outro-otelo@registo.test", SENTINEL):
        assert address not in out
    sender = RecordingCalendarSender()
    sent = _call("send_schedule_to_calendar",
                 {"professor": "Otelo Brisa", **_SUP, "identity_directory": _TWO}, sender=sender)
    assert sent.startswith("RAISED:") and sender.sent == []


def test_twin_two_entries_with_different_addresses_are_refused_by_name():
    """…and the refusal says WHY, naming the labels — never the addresses."""
    out = _preview(_TWO)
    assert "2 people in this institution's registry match Otelo Brisa" in out, out
    assert "(Otelo, Otelo Brisa)" in out
    assert "professors tab" in out


def test_twin_the_same_address_twice_is_not_a_choice():
    """The same mailbox under two labels (or two cases) is one address — nothing to choose."""
    twice = [{"label": "Otelo Brisa", "email": REGISTRY_ADDRESS},
             {"label": "Otelo", "email": REGISTRY_ADDRESS.upper()}]
    assert REGISTRY_ADDRESS in _proposal_line(_preview(twice))


def test_control_a_label_that_fits_two_professors_designates_nobody():
    """«Lia» is inside «Lia Corvelo» AND «Otília Fontoura»: by the match's own rule it designates
    nobody, so it is not Lia Corvelo's address — the refusal of today."""
    out = _preview([{"label": "Lia", "email": "lia@registo.test"}], professor="Lia Corvelo")
    assert out.startswith("ERROR: There is no e-mail address on file for Lia Corvelo"), out
    assert "lia@registo.test" not in out


def test_control_a_name_that_fits_two_professors_has_no_registry_address():
    """The other side of the same rule: the professor NAMED has to be one person too. «Lia» is
    Lia Corvelo and Otília Fontoura, so even a registry label «Lia» — the same two people — is not
    an answer: the refusal of today."""
    out = _preview([{"label": "Lia", "email": "lia@registo.test"}], professor="Lia")
    assert out.startswith("ERROR: There is no e-mail address on file for Lia,"), out
    assert "lia@registo.test" not in out


def test_twin_the_full_label_designates_her():
    """The pair of the control above: the label written out designates exactly one person."""
    full = _preview([{"label": "Lia Corvelo", "email": "lia@registo.test"}], professor="Lia Corvelo")
    assert "→ lia@registo.test (from the Cogno registry" in _proposal_line(full)


def test_control_a_professor_is_not_given_the_registry():
    """The fallback is the coordination's. A professor sending their OWN calendar is answered
    by the host's own address for them (``identity_email``) or the tab — a registry handed to a
    non-oversight call is ignored."""
    out = _call("preview_schedule_to_calendar",
                {"role": "EMPLOYEE", "identity_label": "Otelo Brisa", "month": "2026-09",
                 "identity_directory": _DIRECTORY})
    assert out == _TODAYS_REFUSAL, out


def test_control_malformed_entries_are_ignored_not_fatal():
    junk = [{"label": "Otelo Brisa"}, {"label": "Otelo Brisa", "email": "sem-arroba"},
            {"label": "", "email": REGISTRY_ADDRESS}, {"email": REGISTRY_ADDRESS},
            {"label": "   ", "email": "  "}]
    assert _preview(junk) == _TODAYS_REFUSAL


def test_the_own_address_still_wins_for_the_caller():
    """Unchanged: the host's own address for the caller comes first (the order of before)."""
    out = _call("preview_schedule_to_calendar",
                {"professor": "Otelo Brisa", "role": "SUPERVISOR", "identity_label": "Otelo Brisa",
                 "month": "2026-09", "identity_email": "otelo@proprio.test",
                 "identity_directory": _DIRECTORY})
    assert _proposal_line(out) == "PROPOSAL: 2 class(es) of September 2026 → otelo@proprio.test"


# ── 3. NO ADDRESS OF THE REGISTRY REACHES A LOG LINE ──────────────────────────────────────

def test_no_registry_address_reaches_a_log_line(caplog):
    """Every logger of the package, at DEBUG, over the twin, the send and the refusal."""
    two = [{"label": "Otelo Brisa", "email": REGISTRY_ADDRESS},
           {"label": "Otelo", "email": "outro-otelo@registo.test"}] + _DIRECTORY[1:]
    with caplog.at_level(logging.DEBUG):
        _preview(_DIRECTORY)
        _call("send_schedule_to_calendar",
              {"professor": "Otelo Brisa", **_SUP, "identity_directory": _DIRECTORY})
        _preview(two)
    logged = "\n".join(f"{r.name} {r.getMessage()}" for r in caplog.records)
    for address in (REGISTRY_ADDRESS, "outro-otelo@registo.test", SENTINEL):
        assert address not in logged


# ── 4. A HALF-READ SCHEDULE RESOLVES NOBODY ────────────────────────────────────────────────

_SID_2 = "1ZzYyXxWwVvUuTtSsRrQqPpOoNnMmLlKkJjIiHhGgF0"


def test_control_a_schedule_that_did_not_read_in_full_resolves_nobody():
    """A second spreadsheet that does not read: the cast is partial, and a partial cast can make
    an ambiguous label look like one person. So the registry is not consulted — today's refusal
    — while the same request over a schedule that read in full uses it (the twin above)."""
    rules = _RULES.replace("SPREADSHEETS:\n",
                           f"SPREADSHEETS:\nDE_10={_SID_2}\n", 1)

    class _HalfStore(InMemorySpreadsheetStore):
        def read_range(self, sheet_id, tab, a1_range):
            if sheet_id == _SID_2:
                raise RuntimeError("sheet unavailable")
            return super().read_range(sheet_id, tab, a1_range)

    store = _HalfStore()
    store.put(_SID, "Secretaria", [list(_HEADER)] + [list(r) for r in _ROWS])
    store.put(_SID, "Info", [list(r) for r in _PROFS])
    svc = CoordinatorService(store, CoordinatorConfig(rules), today=lambda: date(2026, 8, 31))
    assert len(svc.cfg.spreadsheets) == 2
    out = _preview(_DIRECTORY, svc=svc)
    assert out.startswith("ERROR: There is no e-mail address on file for Otelo Brisa"), out
    assert REGISTRY_ADDRESS not in out and SENTINEL not in out
