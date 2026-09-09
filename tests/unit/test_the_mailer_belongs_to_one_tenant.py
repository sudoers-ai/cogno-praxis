"""Which mailbox a class calendar leaves by — asked per send, answered by the tenant, or refused.

**The defect, measured on the deployment that runs this.** ``cogno_host.modules`` spawns the
coordinator child with ``{**os.environ, **env_extra}`` and its own comment says
``COGNO_COORDINATOR_SMTP`` "is genuinely the box's and nothing per-turn re-injects it"; the box's
``.env`` declares ``SMTP_HOST``/``SMTP_USER``/``SMTP_PASSWORD``/``SMTP_FROM_EMAIL`` and declares
no ``COGNO_COORDINATOR_SMTP`` at all. Under the old chain (tenant → ``SMTP_*`` → ``None``) that
is one sentence: **every tenant sent through the deployment's real account**, whether or not it
had asked for a mailbox — a rehearsal tenant included, whose messages would arrive in strangers'
inboxes from the box's own address. And the only configuration that stopped it — pointing the
shared variable at a sink — redirected the deployment's OWN coordinator with it, because both
ends read the same process variable. Not an exit: a trade.

The second half was ``mcp = build_server()`` at import: the mailbox was resolved once, when the
MCP subprocess STARTED, so even a host that began stamping the variable per turn would have
been ignored by every turn after the first.

Three twins, and the third is the one that keeps the fix from being inert:

1. a tenant that declared nothing sends NOTHING, on a box that has a perfectly good mailbox;
2. a tenant that declared its own sends by ITS OWN, with the box's sitting right there unused;
3. the mailbox is chosen when the tool is CALLED — two tenants served by one process, and by one
   already-built server, leave by two different accounts.

**Nothing here sends mail.** Every transport is a double: either ``RecordingCalendarSender`` or a
recorder monkeypatched over ``cogno_herald.send_email_with_ics``. The one place a real SMTP dial
could happen is a resolved ``SmtpCalendarSender`` with no ``send_fn``, and that object's
``organizer()`` — which is what most of these assertions read — touches no network at all.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    RecordingCalendarSender,
)
from cogno_praxis.coordinator.mailer import (
    TENANT_SMTP_ENV,
    declared_smtp,
    sender_for_tenant,
    sender_from_env,
)
from cogno_praxis.coordinator.server import build_server

# ── the fixture: one professor, one class, an address to send to ──────────────────────

_RULES = (
    "SPREADSHEETS:\nDE_09=1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A1:E200"\n'
    'TAB_PROFESSORS: "Info"\nRANGE_PROFESSORS: "A1:C50"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
)
_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_TODAY = date(2026, 8, 31)

#: The box's own account, as the live ``.env`` declares it — the mailbox that must never be
#: borrowed by a tenant that did not ask for it.
_DEPLOY_ENV = {"SMTP_HOST": "smtp.deploy.test", "SMTP_USER": "no-reply@deploy.test",
               "SMTP_PASSWORD": "s3cret", "SMTP_FROM_EMAIL": "no-reply@deploy.test",
               "SMTP_FROM_NAME": "Cogno"}

_TENANT_A = '{"host": "smtp.escola-a.test", "from_email": "coord@escola-a.test"}'
_TENANT_B = '{"host": "smtp.escola-b.test", "from_email": "coord@escola-b.test"}'


def _service():
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [["Data", "Dia", "Professor", "Disciplina", "Sala"],
                                   ["01/09/2026", "Ter", "Ana", "NoSQL", "101"]])
    store.put(_SID, "Info", [["Professor", "e-mail"], ["Ana", "ana@escola.test"]])
    return CoordinatorService(store, cfg, today=lambda: _TODAY)


_SEND_ARGS = {"professor": "Ana", "month": "2026-09",
              "identity_label": "Ana", "role": "EMPLOYEE"}


def _text(res) -> str:
    return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")


def _box(monkeypatch, *, tenant: "str | None") -> None:
    """Put the process in the deployment's real shape: the box's ``SMTP_*``, plus (or minus) a
    declaration for the tenant whose turn this is."""
    for k, v in _DEPLOY_ENV.items():
        monkeypatch.setenv(k, v)
    if tenant is None:
        monkeypatch.delenv(TENANT_SMTP_ENV, raising=False)
    else:
        monkeypatch.setenv(TENANT_SMTP_ENV, tenant)


class _Transport:
    """A stand-in for ``cogno_herald.send_email_with_ics`` — records the SMTP config it was
    handed, which is the only way to see WHICH account a message would have left by."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def __call__(self, *args):
        self.calls.append(args)
        return {"sent": True}

    @property
    def hosts(self) -> "list[str]":
        return [c[0].get("host", "") for c in self.calls]


# ── TWIN 1: nothing declared, nothing sent ────────────────────────────────────────────

def test_a_tenant_that_declared_no_mailbox_sends_nothing_though_the_box_has_one(monkeypatch):
    """The half that lets a rehearsal tenant exist at all.

    The CONTROL is in this test, deliberately, and it runs FIRST: an assertion of absence that
    cannot produce the presence is an assertion about a broken fixture. So the same environment
    is first shown to be a *perfectly good, resolvable mailbox* — herald builds a sender out of
    it the moment anybody asks it to — and only then is the coordinator's answer, over that same
    environment, shown to be ``None``. The ``None`` is therefore a DECISION about provenance,
    not an empty variable.
    """
    herald = pytest.importorskip("cogno_herald")
    _box(monkeypatch, tenant=None)

    # CONTROL — the presence. The box's account is real, complete and loadable right now.
    from_the_box = herald.resolve_smtp_config(None)
    assert from_the_box is not None, "fixture is broken: the box's SMTP_* did not resolve"
    assert from_the_box["host"] == "smtp.deploy.test"
    # ...and it is exactly what the old chain handed the coordinator, unasked.

    # THE CLAIM — the absence. Same process, same variables, one question later.
    assert sender_from_env() is None
    assert declared_smtp(None) == {} and sender_for_tenant(None) is None


def test_the_tool_refuses_the_send_rather_than_borrowing_the_boxs_account(monkeypatch):
    """The same twin where it is spent: through the tool, over the whole server.

    The refusal RAISES (``CoordinatorError``) rather than returning a polite sentence, which is
    the vertical's existing contract — a returned sentence is a successful call, and the MCP
    bridge stamps a successful call on a non-read-only tool as a write that happened. Nothing
    left, so nothing may be recorded as having left.

    The control is the twin below it in this same module: identical fixture, identical call, one
    declaration added, and the message goes.
    """
    pytest.importorskip("cogno_herald")
    _box(monkeypatch, tenant=None)
    # If anything did try to send, this would be the transport — and it must record nothing.
    transport = _Transport()
    monkeypatch.setattr("cogno_herald.send_email_with_ics", transport)

    mcp = build_server(_service(), tz_name="America/Sao_Paulo")
    with pytest.raises(Exception) as exc:
        asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS)))
    assert "no e-mail is configured" in str(exc.value).lower()
    assert transport.calls == []


# ── TWIN 2: what a tenant declared is what it sends by ────────────────────────────────

def test_a_tenant_that_declared_its_own_mailbox_sends_by_that_one(monkeypatch):
    """And the box's account is sitting right there, fully configured, and is not used.

    Asserted on the SMTP config the transport was actually handed, not on a sender object built
    on the side: which account a message left by is a fact about the call, and only the call has
    it.
    """
    pytest.importorskip("cogno_herald")
    _box(monkeypatch, tenant=_TENANT_A)
    transport = _Transport()
    monkeypatch.setattr("cogno_herald.send_email_with_ics", transport)

    mcp = build_server(_service(), tz_name="America/Sao_Paulo")
    out = _text(asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS))))

    assert out.startswith("SENT:")
    assert transport.hosts == ["smtp.escola-a.test"]
    assert "smtp.deploy.test" not in transport.hosts
    # the ORGANIZER the professor replies to is the institution's, never the box's
    assert "ORGANIZER" in transport.calls[0][4] and "coord@escola-a.test" in transport.calls[0][4]


def test_the_declaration_is_normalized_by_heralds_own_rules_and_not_by_a_second_copy(monkeypatch):
    """``port``/``use_tls``/``from_email`` defaults come from ``resolve_smtp_config`` — the same
    function the booking invite normalizes with. What this module changed is WHICH branch of it
    is reachable, not what a declaration means once it exists."""
    pytest.importorskip("cogno_herald")
    _box(monkeypatch, tenant='{"host": "smtp.escola-a.test", "user": "bot@escola-a.test"}')
    sender = sender_from_env()
    assert sender is not None
    # from_email defaults to the authenticated user — herald's rule, not one written here
    assert sender.organizer()[0] == "bot@escola-a.test"


@pytest.mark.parametrize("raw", ["", "   ", "not json", "[1,2]", '"a string"', "{}",
                                 '{"host": ""}', '{"host": "   "}', '{"port": 587}'])
def test_a_declaration_that_names_no_server_is_no_declaration(monkeypatch, raw):
    """Malformed, empty, or hostless — all of them mean "this tenant declared nothing", and all
    of them therefore mean nothing is sent. A typo must not take the vertical down (every
    schedule read in the child would die with it, over a mailbox nobody asked to use); it must
    also not quietly promote the box's account, which is what "ignore and continue" used to do.
    """
    pytest.importorskip("cogno_herald")
    _box(monkeypatch, tenant=None)
    monkeypatch.setenv(TENANT_SMTP_ENV, raw)
    assert sender_from_env() is None


@pytest.mark.parametrize("cfg", [None, {}, "a string", {"schedule_config": None},
                                 {"schedule_config": "smtp"},
                                 {"schedule_config": {"smtp": "smtp.escola.test"}},
                                 {"schedule_config": {}}])
def test_a_config_of_the_wrong_shape_reads_as_nothing_declared_and_never_raises(cfg):
    """The host owns this argument — a stored config, a JSON column, an environment variable —
    so every level of the shape is checked rather than trusted.

    An ``AttributeError`` climbing out of a mailer would kill a turn that was only trying to read
    a schedule, over a mailbox nobody asked to use. And the safe direction is fixed: a shape this
    code cannot read means NOTHING was declared, therefore nothing is sent — never a fallback.

    The control is every other test in this module: a well-formed declaration builds a sender.
    """
    assert declared_smtp(cfg) == {}
    assert sender_for_tenant(cfg) is None


# ── TWIN 3: chosen at the moment of the call, not at import ───────────────────────────

def test_two_tenants_in_one_process_leave_by_two_different_accounts(monkeypatch):
    """The twin that makes the fix non-inert, and it reproduces the shape of the old defect.

    ONE server, built ONCE — the same object ``mcp = build_server()`` produces at import — and
    two turns for two different institutions. With the mailbox captured at build time the second
    call goes out through the first tenant's account; with it resolved per call, each leaves by
    its own. The assertion is the pair, in order, on the transport itself.
    """
    pytest.importorskip("cogno_herald")
    transport = _Transport()
    monkeypatch.setattr("cogno_herald.send_email_with_ics", transport)

    _box(monkeypatch, tenant=_TENANT_A)
    mcp = build_server(_service(), tz_name="America/Sao_Paulo")     # built ONCE, before both
    asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS)))

    _box(monkeypatch, tenant=_TENANT_B)                              # a different tenant's turn
    asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS)))

    assert transport.hosts == ["smtp.escola-a.test", "smtp.escola-b.test"]


def test_a_host_that_resolves_the_tenant_itself_is_asked_on_every_call(monkeypatch):
    """The injected seam, which is the one an in-process multi-tenant caller uses — a sweep over
    every tenant, say — and which touches no environment at all.

    Same shape as ``cogno_host.api.pg_app._build_invite_sender``: the host passes a CALLABLE and
    the send asks it, rather than handing over a mailbox resolved once at wiring time.
    """
    _box(monkeypatch, tenant=None)              # the environment is irrelevant on this path
    a = RecordingCalendarSender(organizer_email="coord@escola-a.test")
    b = RecordingCalendarSender(organizer_email="coord@escola-b.test")
    turns = [a, b]

    mcp = build_server(_service(), sender_for=lambda: turns.pop(0),
                       tz_name="America/Sao_Paulo")
    asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS)))
    asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS)))

    assert len(a.sent) == 1 and len(b.sent) == 1
    assert "coord@escola-a.test" in a.sent[0]["ics"]
    assert "coord@escola-b.test" in b.sent[0]["ics"]


def test_a_resolver_that_answers_None_for_this_tenant_refuses_the_send(monkeypatch):
    """The injected seam has to be able to say "not this one" — otherwise a host with a sweep
    over many tenants can only choose between mailing all of them and mailing none.

    The control is the test above: the identical call, the identical server shape, a resolver
    that answers a sender, and the message goes.
    """
    _box(monkeypatch, tenant=None)
    mcp = build_server(_service(), sender_for=lambda: None, tz_name="America/Sao_Paulo")
    with pytest.raises(Exception) as exc:
        asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS)))
    assert "no e-mail is configured" in str(exc.value).lower()


def test_a_server_may_not_be_built_with_two_answers_to_which_mailbox():
    """``sender`` and ``sender_for`` disagreeing is the one failure neither of them can report:
    the message leaves by one of them and the trace names the other."""
    with pytest.raises(ValueError, match="never both"):
        build_server(_service(), sender=RecordingCalendarSender(), sender_for=lambda: None)


def test_the_fixed_sender_seam_still_pins_one_mailbox():
    """The other half of that rule: ``sender=`` is a host that ALREADY resolved the tenant, and
    every existing caller and test relies on it. Unchanged, and asked for nothing per call."""
    rec = RecordingCalendarSender(organizer_email="coord@escola-a.test")
    mcp = build_server(_service(), sender=rec, tz_name="America/Sao_Paulo")
    asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS)))
    asyncio.run(mcp.call_tool("send_schedule_to_calendar", dict(_SEND_ARGS)))
    assert len(rec.sent) == 2
