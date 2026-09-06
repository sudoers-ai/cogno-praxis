"""The delivery adapter: the ONE place the vertical touches a transport, and the two answers.

Everything the domain does with a send is read off one boolean, so this file is about where that
boolean comes from. ``cogno-herald`` does the actual SMTP — the same function
``cogno_host.invites`` mails every booking invite with — and what is tested here is the wiring:
the organizer derivation, the argument order, and the fact that "no SMTP configured" produces
``None`` rather than a sender that silently swallows the message.
"""

from __future__ import annotations

import asyncio

import pytest

from cogno_praxis.coordinator.mailer import (
    DEFAULT_ORGANIZER_NAME,
    SmtpCalendarSender,
    _tenant_smtp_from_env,
    sender_from_env,
)

_SMTP = {"host": "smtp.escola.test", "port": 587, "user": "bot@escola.test",
         "from_email": "coord@escola.test", "from_name": "Coordenação"}


class _Recorder:
    def __init__(self, sent: bool = True) -> None:
        self.sent = sent
        self.calls: list[tuple] = []

    async def __call__(self, *args):
        self.calls.append(args)
        return {"sent": self.sent}


# ── the organizer ─────────────────────────────────────────────────────────────────────

def test_the_organizer_follows_the_booking_invites_rule_exactly():
    """``from_email`` → ``user`` → nothing, and a default display name. Not a new convention:
    the same derivation ``cogno_host.invites._organizer`` applies to the booking invite, because
    the ORGANIZER of an event and the From of the mail carrying it are one fact."""
    assert SmtpCalendarSender(_SMTP).organizer() == ("coord@escola.test", "Coordenação")
    no_from = {k: v for k, v in _SMTP.items() if k != "from_email"}
    assert SmtpCalendarSender(no_from).organizer() == ("bot@escola.test", "Coordenação")
    bare = {"host": "smtp.escola.test"}
    assert SmtpCalendarSender(bare).organizer() == ("", DEFAULT_ORGANIZER_NAME)


# ── the send ──────────────────────────────────────────────────────────────────────────

def test_a_send_hands_herald_the_arguments_in_the_order_it_declares_them():
    rec = _Recorder()
    sender = SmtpCalendarSender(_SMTP, send_fn=rec)
    ok = asyncio.run(sender.send(to="ana@escola.test", subject="Suas aulas", body="12 aulas",
                                 ics="BEGIN:VCALENDAR\r\n", filename="aulas.ics"))
    assert ok is True
    smtp, to_list, subject, body, ics, filename = rec.calls[0]
    assert smtp is _SMTP and to_list == ["ana@escola.test"]
    assert (subject, body, filename) == ("Suas aulas", "12 aulas", "aulas.ics")
    assert ics.startswith("BEGIN:VCALENDAR")


def test_a_server_that_refuses_produces_False_and_not_an_exception():
    """The refusal has to travel as a VALUE: the domain turns it into "nothing was sent", and an
    exception here would arrive as a crash instead of an honest sentence."""
    sender = SmtpCalendarSender(_SMTP, send_fn=_Recorder(sent=False))
    assert asyncio.run(sender.send(to="a@b.test", subject="s", body="b", ics="x")) is False


def test_a_bare_boolean_from_a_custom_transport_is_read_too():
    """A host that injects its own sender need not mimic herald's dict shape."""
    async def _plain(*args):
        return True
    sender = SmtpCalendarSender(_SMTP, send_fn=_plain)
    assert asyncio.run(sender.send(to="a@b.test", subject="s", body="b", ics="x")) is True


# ── resolving a sender out of the environment ─────────────────────────────────────────

def test_with_nothing_configured_there_is_no_sender_at_all():
    """``None``, never a no-op sender. The third possibility — something that accepts the
    message and drops it — is the only one a professor cannot detect."""
    pytest.importorskip("cogno_herald")
    import os
    saved = {k: os.environ.pop(k, None) for k in ("SMTP_HOST", "COGNO_COORDINATOR_SMTP")}
    try:
        assert sender_from_env() is None
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_the_environment_half_of_heralds_chain_is_what_builds_it(monkeypatch):
    pytest.importorskip("cogno_herald")
    monkeypatch.delenv("COGNO_COORDINATOR_SMTP", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.env.test")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "env@escola.test")
    sender = sender_from_env()
    assert sender is not None and sender.organizer()[0] == "env@escola.test"


def test_a_tenant_override_beats_the_environment(monkeypatch):
    """The same precedence the booking invite resolves per tenant (override → global env →
    None), reached here through the one variable the host can stamp per turn."""
    pytest.importorskip("cogno_herald")
    monkeypatch.setenv("SMTP_HOST", "smtp.env.test")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "env@escola.test")
    monkeypatch.setenv("COGNO_COORDINATOR_SMTP",
                       '{"host": "smtp.tenant.test", "from_email": "tenant@escola.test"}')
    sender = sender_from_env()
    assert sender is not None and sender.organizer()[0] == "tenant@escola.test"


@pytest.mark.parametrize("raw", ["", "   ", "not json", "[1,2]", '"a string"'])
def test_a_malformed_override_is_ignored_rather_than_fatal(monkeypatch, raw):
    """A typo in one variable must not take the whole vertical down: every schedule read in the
    subprocess would die with it, over a mailbox nobody asked to use this turn."""
    monkeypatch.setenv("COGNO_COORDINATOR_SMTP", raw)
    assert _tenant_smtp_from_env() is None


def test_a_wellformed_override_arrives_in_the_shape_herald_reads():
    import os
    os.environ["COGNO_COORDINATOR_SMTP"] = '{"host": "smtp.tenant.test"}'
    try:
        assert _tenant_smtp_from_env() == {"schedule_config": {"smtp": {"host": "smtp.tenant.test"}}}
    finally:
        os.environ.pop("COGNO_COORDINATOR_SMTP", None)


def test_the_production_path_resolves_heralds_sender_lazily(monkeypatch):
    """The branch that actually runs in a deployment: no ``send_fn``, so the transport is
    imported at CALL time. Lazy because ``cogno-herald`` is optional — importing it at module
    load would make a deployment that never mails a calendar fail to start the vertical."""
    herald = pytest.importorskip("cogno_herald")
    rec = _Recorder()
    monkeypatch.setattr(herald, "send_email_with_ics", rec)
    assert asyncio.run(SmtpCalendarSender(_SMTP).send(
        to="ana@escola.test", subject="s", body="b", ics="BEGIN:VCALENDAR\r\n")) is True
    assert rec.calls[0][1] == ["ana@escola.test"]
