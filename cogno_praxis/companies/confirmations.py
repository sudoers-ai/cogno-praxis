"""The one-time secret that makes ``company_delete``'s second step a SECOND step.

## Why a token exists at all

Until 2026-09-06 the confirmed removal was decided by comparing ``confirm_company_id`` with
the row's own ``company_id`` — **two arguments of the same call**, the second of which the
caller had to send anyway. So the "two steps" were one: a single call with the id on both
ends removed the company with nothing ever proposed to anybody, and ``company_id`` is DERIVED
from the accent-folded name, so anyone who knows a company is called "Acme" can write ``acme``
without having read a thing. Measured through the real chain (EGO → host write policy →
this vertical): one call, row gone, no question asked.

A second step is only a second step if it carries something **the first step produced and the
caller could not have invented**. That is the whole definition of a nonce, and it is the only
property this module implements.

## Why a STORE and not a dict on the service

The companies vertical is spawned as a **subprocess per turn** (``cogno_host/modules.py``:
``_companies_source`` over stdio; ``pooled_registry`` pools only the scheduler and says so —
*"the bookkeeper, coordinator + companies stay per-turn"*). The proposal and the confirmation
are therefore produced by two DIFFERENT processes. A token held in the service's memory dies
with the turn that minted it, and the confirmation could never arrive — which is the failure
mode a nonce must not introduce: *a removal without confirmation traded for a confirmation
that never comes.* So the token goes where the rows go, behind a port with an in-memory default
(tests, the standalone demo) and a Postgres adapter (production).

## Why the TTL is 1800 s

It is the host's own ``Host(confirm_ttl_s=1800.0)`` — the window inside which an affirmative is
still allowed to release a held confirmation at all (``_hold_is_fresh``). Shorter and this
vertical becomes the binding constraint, refusing a contact the host would still have accepted;
longer buys nothing, because the host drops the hold first. The number is aligned rather than
invented, and it is injectable for a host that runs another one.

## What the token is bound to

The pair ``(identity, company)`` — the SUBJECT. A token minted while proposing to remove Acme
for one identity is refused for Initech, and refused for another identity: a nonce that any
call can spend is a shared secret, not a nonce. And it is spent ONCE: consuming deletes it, so
the same confirmation cannot commit twice.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

__all__ = [
    "DEFAULT_CONFIRMATION_TTL_S",
    "ConfirmationStore",
    "InMemoryConfirmationStore",
    "confirmation_subject",
    "mint_token",
]

# The host's `Host(confirm_ttl_s=...)` default, matched on purpose — see the module docstring.
DEFAULT_CONFIRMATION_TTL_S = 1800.0

# 24 bytes of `secrets` entropy, URL-safe. Not derived from the company id, the name, the CNPJ,
# the identity or the turn: every one of those is a value the caller already holds or can guess,
# and a token derived from what the caller has is the defect this module was written to remove.
_TOKEN_BYTES = 24


def mint_token() -> str:
    """A fresh, unguessable confirmation token."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def confirmation_subject(identity_id: str, company_id: str) -> str:
    """What a token may be spent ON: this identity, removing this company.

    ``\\x1f`` (unit separator) rather than a printable joiner: neither half is escaped, and a
    separator that can occur inside an id makes two different pairs collide into one subject.
    """
    return f"{(identity_id or '').strip()}\x1f{(company_id or '').strip()}"


@runtime_checkable
class ConfirmationStore(Protocol):
    """Where a pending confirmation lives between the proposal and the answer."""

    def issue(self, subject: str, token: str, expires_at: float) -> None:
        """Record ``token`` as spendable on ``subject`` until ``expires_at``."""

    def consume(self, subject: str, token: str, *, now: float) -> bool:
        """Spend ``token`` on ``subject``. ``True`` exactly once, and never after expiry."""


@dataclass
class InMemoryConfirmationStore:
    """Process-local store — unit tests and the standalone demo.

    Production injects the Postgres adapter for the reason in the module docstring: in the
    real deployment the two steps run in two processes and this class would answer ``False``
    to every confirmation.
    """

    tokens: "dict[str, tuple[str, float]]" = field(default_factory=dict)

    def issue(self, subject: str, token: str, expires_at: float) -> None:
        self.tokens[token] = (subject, expires_at)

    def consume(self, subject: str, token: str, *, now: float) -> bool:
        found: "Optional[tuple[str, float]]" = self.tokens.get(token)
        if found is None or found[0] != subject or found[1] <= now:
            # A failed attempt does NOT remove the row. Popping on mismatch would let anyone
            # who can call the tool burn a pending confirmation by guessing at it, which turns
            # a nonce into a denial of the confirmation it exists to carry.
            return False
        del self.tokens[token]              # single use: spent is gone
        return True

    def purge_expired(self, *, now: "Optional[float]" = None) -> int:
        """Drop expired rows; returns how many. Housekeeping, not part of the port."""
        cutoff = time.time() if now is None else now
        dead = [t for t, (_, exp) in self.tokens.items() if exp <= cutoff]
        for token in dead:
            del self.tokens[token]
        return len(dead)
