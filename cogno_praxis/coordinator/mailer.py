"""The SMTP adapter behind :class:`~cogno_praxis.coordinator.ics.CalendarSender`.

The delivery half is NOT new code: it is ``cogno_herald.send_email_with_ics``, the same
function ``cogno_host.invites`` mails every booking invite with. What this module adds is the
port shape, so the vertical's domain never imports a transport.

**One tenant, one mailbox, resolved at the moment of the send.** :func:`sender_for_tenant` is
the whole rule and it is a PURE function of what a tenant DECLARED: no declaration, no sender,
and therefore no mail. It is the shape ``cogno_host.api.pg_app._build_invite_sender`` already
uses for the booking invite — an ``_smtp_of(tenant_id)`` the sender calls at SEND time rather
than a mailbox frozen when the process started.

**What it deliberately does NOT do is fall back to the deployment's ``SMTP_*``**, and that is
the difference between this and the booking invite. A booking invite is the product working:
every tenant's confirmations should leave, and the box's mailbox is the right default. A class
calendar is an OUTBOUND message to a professor from an institution, and a tenant that declared
no mailbox has not asked for one — resolving the box's would put the deployment's own address
on a stranger's invitation and put a rehearsal tenant's mail in a real inbox. Measured on the
deployment that runs this today: ``.env`` declares ``SMTP_HOST``/``SMTP_USER``/``SMTP_PASSWORD``
and declares no ``COGNO_COORDINATOR_SMTP`` at all, and ``cogno_host.modules`` hands the
coordinator child ``{**os.environ, **env_extra}`` with nothing per-turn re-injecting the
mailbox — so under the old chain EVERY tenant, declared or not, sent through the box's account.
The only exit was to point the shared variable somewhere else, which redirects the deployment's
own coordinator with it: not an exit, a trade.

So herald's ``resolve_smtp_config`` is still what normalizes a declaration (port, ``from_email``,
``use_tls``, the defaults) — it is called only once a declaration EXISTS, which makes its
environment branch unreachable from here by construction rather than by hope.

``cogno-herald`` is an OPTIONAL dependency (extra ``calendar``): a deployment that never sends
a calendar should not have to install a mail library, and a missing one degrades to a ``None``
sender — which the tool reads as "no e-mail is configured here", refuses honestly, and sends
nothing. The import is lazy for the same reason every other optional adapter imports lazily.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional, cast

_log = logging.getLogger(__name__)

#: ``from_name`` when the SMTP config declares none — the same default
#: ``cogno_herald.resolve_smtp_config`` writes for the environment chain.
DEFAULT_ORGANIZER_NAME = "Cogno"

#: The variable a host declares ONE tenant's coordinator mailbox in, as a JSON object, on the
#: stdio child it spawns for that tenant's turn. Named here because the refusal, the tests and
#: the host's injection all have to spell it the same way.
TENANT_SMTP_ENV = "COGNO_COORDINATOR_SMTP"


class SmtpCalendarSender:
    """Mail one built ``.ics`` over ONE tenant's SMTP.

    ``smtp`` is a ``cogno_herald.SmtpConfig`` mapping — the tenant's, always, never the
    deployment's by default. ``send_fn`` exists so the branch a server REFUSES can be exercised
    without a mail server; production leaves it ``None`` and the real
    ``cogno_herald.send_email_with_ics`` is resolved at call time.
    """

    def __init__(self, smtp: "dict[str, Any]", *,
                 send_fn: "Optional[Callable[..., Any]]" = None) -> None:
        self._smtp = smtp
        self._send_fn = send_fn

    def organizer(self) -> "tuple[str, str]":
        """The From identity, and therefore the events' ``ORGANIZER``.

        Byte-for-byte the rule ``cogno_host.invites._organizer`` applies to the booking invite:
        the declared ``from_email``, else the authenticated ``user``, else nothing."""
        return (self._smtp.get("from_email") or self._smtp.get("user") or "",
                self._smtp.get("from_name") or DEFAULT_ORGANIZER_NAME)

    async def send(self, *, to: str, subject: str, body: str, ics: str,
                   filename: str = "schedule.ics") -> bool:
        # ``Callable[..., Any]`` on purpose, and it is not laziness. The config travels as a
        # plain mapping because it arrives as one — from JSON in the environment, or from a
        # host that never imported herald — while ``send_email_with_ics`` declares herald's
        # ``SmtpConfig`` TypedDict. Narrowing the local to the typed function would make the
        # port refuse the very shape it exists to carry, and re-declaring the TypedDict here
        # would be a second copy of somebody else's contract. The transport is a SEAM: the
        # host may inject anything that accepts these six arguments.
        send = self._send_fn
        if send is None:
            from cogno_herald import send_email_with_ics
            send = cast("Callable[..., Any]", send_email_with_ics)
        result = await send(self._smtp, [to], subject, body, ics, filename)
        ok = bool(result.get("sent")) if isinstance(result, dict) else bool(result)
        if not ok:
            _log.warning("coordinator: the calendar mail was not accepted by the server")
        return ok


def declared_smtp(tenant_config: "Optional[dict]") -> "dict[str, Any]":
    """What THIS tenant declared, as a mapping — ``{}`` when it declared nothing.

    One reading of one shape (``schedule_config.smtp``), so "did this tenant declare a mailbox"
    and "which mailbox" can never be answered by two different pieces of code. The predicate is
    a non-empty ``host``, which is herald's own: a declaration without a server to talk to is
    not a declaration, and treating it as one is how a tenant gets a sender that cannot send.
    """
    if not tenant_config:
        return {}
    sched = tenant_config.get("schedule_config") or {}
    smtp = sched.get("smtp") or {}
    if not isinstance(smtp, dict) or not str(smtp.get("host") or "").strip():
        return {}
    return smtp


def sender_for_tenant(tenant_config: "Optional[dict]", *,
                      send_fn: "Optional[Callable[..., Any]]" = None
                      ) -> "Optional[SmtpCalendarSender]":
    """The mailer for ONE tenant, built from what THAT tenant declared — or ``None``.

    Pure: it reads its argument and nothing else. No ``os.environ``, so two tenants resolved in
    the same process cannot collide, and a rehearsal tenant cannot inherit a mailbox merely by
    running on a box that has one.

    ``None`` is the ONLY honest answer to "this tenant declared no SMTP": the alternative — a
    sender that swallows the message — is how a professor gets told their calendar is on the
    way and no mail ever leaves. The caller turns this ``None`` into a refusal, and the refusal
    is an ERROR result so nothing downstream can count the turn as a write.
    """
    smtp = declared_smtp(tenant_config)
    if not smtp:
        return None
    try:
        from cogno_herald import resolve_smtp_config
    except Exception:                          # noqa: BLE001 — optional extra, absent is normal
        _log.info("coordinator: cogno-herald is not installed — no calendar mail is configured")
        return None
    # Reached only with a declaration in hand, and herald returns its TENANT branch on exactly
    # this predicate — so the ``SMTP_*`` branch below it is unreachable from here, by
    # construction rather than by trusting a call order. What herald is used for is the
    # NORMALIZATION (port 587, ``from_email`` defaulting to ``user``, ``use_tls``), which is a
    # contract that belongs in one place and not copied into this file.
    resolved = resolve_smtp_config(tenant_config)
    if resolved is None:                       # pragma: no cover - unreachable given `declared_smtp`
        return None
    return SmtpCalendarSender(dict(resolved), send_fn=send_fn)


def sender_from_env() -> "Optional[SmtpCalendarSender]":
    """:func:`sender_for_tenant` over the declaration THIS process was handed, read NOW.

    The stdio child the host spawns for a turn has one configuration channel — its environment
    — so this is the adapter that reads it. It is a function and not a value for the reason the
    whole module exists: called per send, a host that stamps the variable per turn gets the
    turn's mailbox; frozen at import, every turn for the rest of the process gets whatever the
    box happened to be holding when it started.
    """
    return sender_for_tenant(_tenant_smtp_from_env())


def _tenant_smtp_from_env() -> "Optional[dict]":
    """``COGNO_COORDINATOR_SMTP`` (a JSON object) in the shape :func:`sender_for_tenant` takes.

    The seam a host injects a per-tenant mailbox through. Malformed JSON degrades to "nothing
    declared" with a warning rather than raising: a bad variable must not take the whole
    vertical down with it — and, since nothing is declared, nothing is sent."""
    raw = (os.environ.get(TENANT_SMTP_ENV) or "").strip()
    if not raw:
        return None
    import json
    try:
        parsed = json.loads(raw)
    except Exception:                          # noqa: BLE001 — a typo must not kill the server
        _log.warning("coordinator: %s is not valid JSON — ignored", TENANT_SMTP_ENV)
        return None
    if not isinstance(parsed, dict):
        _log.warning("coordinator: %s is not a JSON object — ignored", TENANT_SMTP_ENV)
        return None
    return {"schedule_config": {"smtp": parsed}}
