"""The SMTP adapter behind :class:`~cogno_praxis.coordinator.ics.CalendarSender`.

The delivery half is NOT new code: it is ``cogno_herald.send_email_with_ics``, the same
function ``cogno_host.invites`` mails every booking invite with, and the same
``resolve_smtp_config`` chain behind it (tenant override → ``SMTP_*`` environment → ``None``).
What this module adds is the port shape, so the vertical's domain never imports a transport.

``cogno-herald`` is an OPTIONAL dependency (extra ``calendar``): a deployment that never sends
a calendar should not have to install a mail library, and a missing one degrades to
:func:`sender_from_env` returning ``None`` — which the tool reads as "no e-mail is configured
here", refuses honestly, and sends nothing. The import is lazy for the same reason every other
optional adapter in this package imports lazily.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

_log = logging.getLogger(__name__)

#: ``from_name`` when the SMTP config declares none — the same default
#: ``cogno_herald.resolve_smtp_config`` writes for the environment chain.
DEFAULT_ORGANIZER_NAME = "Cogno"


class SmtpCalendarSender:
    """Mail one built ``.ics`` over the tenant's (or the deployment's) SMTP.

    ``smtp`` is a ``cogno_herald.SmtpConfig`` mapping. ``send_fn`` exists so the branch a
    server REFUSES can be exercised without a mail server; production leaves it ``None`` and
    the real ``cogno_herald.send_email_with_ics`` is resolved at call time.
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
        send = self._send_fn
        if send is None:
            from cogno_herald import send_email_with_ics
            send = send_email_with_ics
        result = await send(self._smtp, [to], subject, body, ics, filename)
        ok = bool(result.get("sent")) if isinstance(result, dict) else bool(result)
        if not ok:
            _log.warning("coordinator: the calendar mail was not accepted by the server")
        return ok


def sender_from_env() -> "Optional[SmtpCalendarSender]":
    """An SMTP sender built from the environment, or ``None`` when nothing is configured.

    ``None`` is the ONLY honest answer to "no SMTP": the alternative — a sender that swallows
    the message — is how a professor gets told their calendar is on the way and no mail ever
    leaves. The caller turns this ``None`` into a refusal, and the refusal is an ERROR result
    so nothing downstream can count the turn as a write.
    """
    try:
        from cogno_herald import resolve_smtp_config
    except Exception:                          # noqa: BLE001 — optional extra, absent is normal
        _log.info("coordinator: cogno-herald is not installed — no calendar mail is configured")
        return None
    # The tenant half of herald's chain rides in as JSON when the host has one to declare; the
    # environment half (``SMTP_*``) is read by herald itself and needs nothing here.
    tenant_cfg = _tenant_smtp_from_env()
    smtp = resolve_smtp_config(tenant_cfg)
    if smtp is None:
        return None
    return SmtpCalendarSender(dict(smtp))


def _tenant_smtp_from_env() -> "Optional[dict]":
    """``COGNO_COORDINATOR_SMTP`` (a JSON object) in the shape ``resolve_smtp_config`` takes.

    The seam a host injects a per-tenant mailbox through, matching what the booking invite
    already resolves per tenant. Malformed JSON degrades to "no override" with a warning rather
    than raising: a bad variable must not take the whole vertical down with it."""
    raw = (os.environ.get("COGNO_COORDINATOR_SMTP") or "").strip()
    if not raw:
        return None
    import json
    try:
        parsed = json.loads(raw)
    except Exception:                          # noqa: BLE001 — a typo must not kill the server
        _log.warning("coordinator: COGNO_COORDINATOR_SMTP is not valid JSON — ignored")
        return None
    if not isinstance(parsed, dict):
        _log.warning("coordinator: COGNO_COORDINATOR_SMTP is not a JSON object — ignored")
        return None
    return {"schedule_config": {"smtp": parsed}}
