"""The calendar is never mailed to a professors-tab address that is not ONE e-mail.

**The defect.** ``calendar_recipient`` took the professors tab's cell when it held an ``@``
(``"@" in value``) and ``strip()``-ed it, and the send handed it to the mailer as one recipient. A
cell with two «@», a blank inside or two addresses went to the mail server as written; a blank at
an end was trimmed — a silent repair of what the tenant typed. The host refuses those values on
every path it mails from (cogno-host #1331); this one is mailed from praxis, where the host's
check is not.

**The rule.** The tab's cell is asked :func:`cogno_praxis.email_address.is_one_address` (the host's
#1242 rule, ``fullmatch``) AS WRITTEN. A cell that is not one address is REFUSED: ``("",
RECIPIENT_INVALID)``, the send and the preview raise «NOT SENT — invalid_recipient: …», one log
line counts it and never names it, and nothing falls through to the registry.

Names and addresses are invented.
"""

from __future__ import annotations

import logging

import pytest

from cogno_praxis.coordinator import RecordingCalendarSender
from tests.unit.test_calendar_recipient_from_the_registry import (_PROFS, _SUP, _call,
                                                                   _service)

#: Shapes of the production rows (two «@», a blank inside) and two more a cell can hold (two
#: addresses; a line break inside). A blank at an END is not here: the tab reader trims every
#: cell when it reads the tab (see the boundary test at the end).
NOT_ONE = ("cira@aba@aba.test", "cira  penumbra@aba.test", "cira@aba.test; outra@aba.test",
           "cira@aba.test\nx")
_IDS = ["dois_arrobas", "espaco_no_meio", "duas_moradas", "quebra"]
#: Another address for the same professor in the registry: it must never be used instead.
REGISTRY = [{"label": "Cira Penumbra", "email": "registo-cira@registo.test"}]


def _profs(address: str) -> list:
    return [list(_PROFS[0]), ["Otelo Brisa", ""], ["Cira Penumbra", address]]


def _send(address: str, *, sender=None, directory=None) -> str:
    args = {"professor": "Cira Penumbra", **_SUP}
    if directory is not None:
        args["identity_directory"] = directory
    return _call("send_schedule_to_calendar", args, svc=_service(profs=_profs(address)),
                 sender=sender)


@pytest.mark.parametrize("bad", NOT_ONE, ids=_IDS)
def test_twin_a_tab_address_that_is_not_one_email_is_refused_and_nothing_is_sent(bad, caplog):
    """On the base: SENT, to the cell as written (or trimmed)."""
    caplog.set_level(logging.WARNING, logger="cogno_praxis.coordinator.service")
    sender = RecordingCalendarSender()
    out = _send(bad, sender=sender)
    assert sender.sent == [], out
    assert "invalid_recipient" in out and "Nothing was sent" in out, out
    assert "cira@" not in out and "penumbra@" not in out          # never the value
    lines = [r.getMessage() for r in caplog.records if "email_refused" in r.getMessage()]
    assert len(lines) == 1 and "reason=invalid_recipient path=calendar" in lines[0]
    assert not any("cira" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.parametrize("bad", NOT_ONE, ids=_IDS)
def test_twin_the_preview_refuses_the_same(bad):
    out = _call("preview_schedule_to_calendar", {"professor": "Cira Penumbra", **_SUP},
                svc=_service(profs=_profs(bad)))
    assert "invalid_recipient" in out and "PROPOSAL:" not in out, out


@pytest.mark.parametrize("bad", NOT_ONE, ids=_IDS)
def test_a_refused_tab_address_never_falls_through_to_the_registry(bad):
    sender = RecordingCalendarSender()
    out = _send(bad, sender=sender, directory=REGISTRY)
    assert sender.sent == [] and "registo-cira@" not in out, out


def test_the_service_answers_the_closed_marker_and_no_address():
    from cogno_praxis.coordinator import service as service_module
    svc = _service(profs=_profs(NOT_ONE[0]))
    assert svc.calendar_recipient(professor="Cira Penumbra", role="SUPERVISOR",
                                  identity_label="Sofia") == ("", service_module.RECIPIENT_INVALID)
    assert service_module.RECIPIENT_INVALID == "invalid_recipient"


def test_control_a_valid_tab_address_is_sent_as_written():
    sender = RecordingCalendarSender()
    out = _send("cira@aba.test", sender=sender)
    assert out.startswith("SENT: "), out
    assert [m["to"] for m in sender.sent] == ["cira@aba.test"]


def test_control_no_tab_address_is_todays_refusal_not_invalid_recipient():
    out = _call("send_schedule_to_calendar", {"professor": "Otelo Brisa", **_SUP},
                svc=_service())
    assert "There is no e-mail address on file for Otelo Brisa" in out
    assert "invalid_recipient" not in out


@pytest.mark.parametrize("value, expected", [
    ("cira@aba.test", True), ("c.p+aviso@sub.aba.test", True),
    *[(v, False) for v in NOT_ONE], ("cira@aba.test ", False), (" cira@aba.test", False),
    ("cira", False), ("cira@aba", False), ("", False), (None, False), (42, False)])
def test_is_one_address_is_the_hosts_rule(value, expected):
    from cogno_praxis.email_address import is_one_address
    assert is_one_address(value) is expected


@pytest.mark.parametrize("ends", ["cira@aba.test ", " cira@aba.test", "cira@aba.test\t"],
                         ids=["espaco_no_fim", "espaco_no_inicio", "tab_no_fim"])
def test_boundary_the_tab_reader_trims_every_cell_so_a_blank_at_an_end_never_reaches_here(ends):
    """DECLARED, not designed here: ``_faculty_rows`` trims EVERY cell of the professors tab when
    it reads it — the contract of the one tab reader every caller shares (the names, the
    disciplines, the contact lookup) — so a blank at an end of the e-mail cell is gone before
    ``calendar_recipient`` asks its question, and the address sent is the trimmed one. The
    predicate itself refuses it (``test_is_one_address_is_the_hosts_rule``). Refusing it here
    would mean changing what the reader hands EVERY caller; this pins today's reading so that
    the day the reader stops trimming, this test says so."""
    sender = RecordingCalendarSender()
    out = _send(ends, sender=sender)
    assert [m["to"] for m in sender.sent] == ["cira@aba.test"], out
