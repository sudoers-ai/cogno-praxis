"""The ``company`` (brand registration) vertical as a FastMCP server.

A thin MCP wrapper over :class:`CompanyService`. The host connects via ``cogno-mcp``
(``MCPDispatcher``), so the EGO sees this as an ordinary tool. Tool ``annotations``
(readOnlyHint / destructiveHint) flow through cogno-mcp into the EGO's read-only mask +
confirmation gate.

## The tool NAME is a contract with the host, not a label

``company_registration`` was a host-native cortex skill until 2026-09-06. It moved here whole,
and the name did NOT move with it by accident: ``cogno_host/company_focus.py`` decides which
company a session is talking about by scanning the turn's executions for exactly this name
(``_TOCAM``) and reading ``company_id``/``company_name`` out of the answer. A rename fails
NOTHING — the focus simply stops moving, and a later planning turn is built for the wrong
company while the text still reads plausibly.

## Why this tool RAISES where its siblings return ``"ERROR: ..."``

The bookkeeper and coordinator answer a refusal with a string starting ``ERROR:``. Measured
2026-09-06 through the real chain: a returned string is a NORMAL return, so the MCP result
carries no ``isError`` and ``cogno_mcp`` builds ``ToolResult(ok=True, side_effect=mutating)``.
For a read that is harmless. For THIS tool it would be a regression with two victims at once:

* the host's focus guard is ``if not ex.ok`` (``company_focus.focus_from_executions``) — a
  refused registration would pass it;
* ``side_effect=True`` with ``ok=True`` is precisely what ``committed_this_turn`` counts, so a
  registration that wrote NOTHING would be recorded as a write and every anti-fabrication net
  downstream would be reading a commit that never happened.

The host-native skill it replaces returned ``status="error"`` → ``ToolResult(ok=False)``. So
this one raises, the SDK marks ``isError``, and ``cogno_mcp`` reports ``ok=False`` — the same
answer, preserved across the move. The message still reaches the model (as ``ToolResult.error``,
fed back so it can self-correct), which is why the refusals name the offending FIELD.

## Why the answer is a ``repr``, and not prose or JSON

The payload is rendered with :func:`repr` of the mapping and returned as a plain string, which
is byte-for-byte what the cortex dispatcher produced before the move (``str(SkillResult.payload)``).
That is what ``company_focus._payload`` parses with ``ast.literal_eval``.

The alternative was measured rather than argued, and the measurement is more interesting than
the conclusion. Annotating this tool ``-> dict`` makes FastMCP serialise the mapping with
``pydantic_core.to_json``. **Today that would still work** — every value in this payload is a
string, and JSON strings ARE Python literals, so ``literal_eval`` reads the JSON form fine. What
it costs is the guarantee: the day a value is a bool or a ``None`` — ``"was_update": true``, the
obvious next key — the JSON stops being a Python literal, ``literal_eval`` raises, ``_payload``
fails CLOSED, and the focus stops moving with nothing red anywhere. Measured 2026-09-06 through
the real chain: with one boolean added, ``ValueError``; without it, parsed.

So ``repr`` is not chosen because JSON is broken here. It is chosen because ``repr`` is correct
for EVERY value the payload might ever carry, and the JSON form is correct only for the values
it happens to carry today — and the failure is silent, which is the kind that gets found by a
contact receiving a plan for the wrong company. ``test_the_answer_is_a_repr_and_not_json``
pins the mechanism rather than the current key set.

The other near-miss: returning a SECOND content block would put a ``"\n"`` and more text after
the mapping, and ``literal_eval`` fails the same way. One block, one mapping, one repr.

``build_server(service)`` is the only injection seam (the host builds a service over its own
store adapter).

Run the demo standalone (stdio):  ``python -m cogno_praxis.company.server``
"""

from __future__ import annotations

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cogno_praxis.company.service import CompanyError, CompanyService
from cogno_praxis.company.store import CompanyStore, InMemoryCompanyStore


def build_server(service: Optional[CompanyService] = None, *,
                 name: str = "cogno-company") -> FastMCP:
    """Build a FastMCP server bound to a service (inject a store-backed one in prod/tests)."""
    svc = service or CompanyService()
    mcp = FastMCP(name)

    # Mutating, and NOT declared destructive. It is on ``_UNDOABLE`` in
    # ``tests/unit/test_tool_annotations.py``: the row's key is DERIVED from the accent-folded
    # name, so registering the same company again with corrected values UPDATES that row — the
    # same shape of undo as the scheduler's ``set_auto_confirm`` ("call it again with the other
    # value"), and it is performed there rather than believed.
    #
    # The residual is named rather than implied: a typo in the NAME keys a DIFFERENT row, so
    # the stray registration stays. Nothing here removes it — the store port carries ``delete``
    # and no tool exposes it, deliberately, because a delete tool on this surface is a new
    # destructive capability and this move was a move.
    #
    # The host's own policy is the layer that HOLDS this call: ``readOnlyHint=False`` reaches
    # ``cogno_mcp``'s ``is_mutating``, and the host wraps every module source in
    # ``WriteConfirmingDispatcher`` ("every write asks before it commits" — ``write_policy.py``),
    # which is where ``company_registration`` was already gated as a cortex skill. Same gate,
    # same answer, a different source.
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def company_registration(company_name: str, cnpj: str = "", visual_identity: str = "",
                             guidelines: str = "", identity_id: str = "") -> str:
        """Registers company brand parameters, visual identity, and artistic guidelines.

        company_name: the registered company or brand name (required).
        cnpj: the company's Brazilian CNPJ, if the user gave one (optional). Any format:
            '11.222.333/0001-81' or '11222333000181'. Send it ONLY as the user stated it —
            never invent or complete a number; an invalid CNPJ is refused and the whole
            registration fails.
        visual_identity: visual identity guidelines or design tokens (optional).
        guidelines: tone of voice or brand communication guidelines (optional).

        Registering a company that is already on file UPDATES its record — it does not create
        a second one.
        """
        row = svc.register(company_name, cnpj=cnpj, visual_identity=visual_identity,
                           guidelines=guidelines, identity_id=identity_id)
        return repr(svc.registration_payload(row, visual_identity=visual_identity,
                                             guidelines=guidelines))

    return mcp


def _seeded_service() -> CompanyService:
    """Build a service from the injected per-tenant env (Postgres when a DSN is set)."""
    dsn = os.environ.get("COGNO_COMPANY_DSN") or os.environ.get("COGNO_PG_DSN")
    store: CompanyStore
    if dsn:
        from cogno_praxis.company.stores.postgres import PgCompanyStore
        store = PgCompanyStore(dsn, os.environ.get("COGNO_COMPANY_SCOPE", "default"))
    else:
        store = InMemoryCompanyStore()
    return CompanyService(store)


if __name__ == "__main__":
    # Build the server ONLY when run as the stdio entrypoint — the scheduler's shape, and for
    # its reason: building at module level runs on a mere `from ... import build_server` AND
    # again under `python -m` (the module executes twice: package import + __main__), opening
    # two Postgres connections per subprocess.
    build_server(_seeded_service()).run()


__all__ = ["CompanyError", "build_server"]
