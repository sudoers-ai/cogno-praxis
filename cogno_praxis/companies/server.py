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

Run the demo standalone (stdio):  ``python -m cogno_praxis.companies.server``
"""

from __future__ import annotations

import os
from typing import Optional, Sequence

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ToolAnnotations

from cogno_praxis.companies.service import (
    CompanyError,
    CompanyService,
    DeletionProposal,
    FieldChange,
)
from cogno_praxis.companies.store import Company, CompanyStore, InMemoryCompanyStore

# ── The gate-C channel: how this server tells cogno-anima "I ran, I read, I did not commit" ──
#
# These two keys are cogno-mcp's (``cogno_mcp.META_NEEDS_CONFIRMATION`` /
# ``META_CONFIRM_ARGUMENTS``) and they are DUPLICATED here rather than imported: this vertical
# has no runtime dependency on the bridge — a host may reach these tools in-process, or over a
# transport that is not MCP — and a skill that could only speak gate C by importing its client
# would have the dependency arrow backwards. Same literals, same reason, as
# ``bookkeeper/server.py``; a duplicated contract needs a pin in BOTH directions, which is what
# ``tests/integration/test_companies_via_mcp.py`` does.
_META_NEEDS_CONFIRMATION = "cogno-mcp/needs_confirmation"
_META_CONFIRM_ARGUMENTS = "cogno-mcp/confirm_arguments"


def _line(c: Company) -> str:
    """One company, as a line a model can read back to a person without inventing anything."""
    bits = [f"{c.name} (id: {c.company_id})"]
    if c.cnpj:
        bits.append(f"CNPJ {c.cnpj}")
    if c.segment:
        bits.append(f"segmento {c.segment}")
    for key, label in (("visual_identity", "identidade visual"), ("guidelines", "diretrizes")):
        value = str((c.visual_identity or {}).get(key) or "").strip()
        if value:
            bits.append(f"{label}: {value}")
    return " — ".join(bits)


def _change_lines(changes: "Sequence[FieldChange]") -> str:
    """The fields that MOVED, one per line, each naming the argument and both values.

    The company line beside this one renders the row as it now stands, and a row cannot be
    checked against a request: «corrige o segmento» answered with a correct-looking company
    line reads as success whether the segment changed or the brand guidelines were replaced.
    So the ARGUMENT name is what is printed — the model chose one, and this is the one thing
    it can compare against what the user said.

    Both values are ``repr``'d so an empty ``before`` shows as ``''`` instead of vanishing:
    "the guidelines went from nothing to X" and "the guidelines were replaced" are different
    facts, and the second is the one worth relaying.
    """
    return "\n".join(f"CHANGED {c.field}: {c.before!r} → {c.after!r}" for c in changes)


def _deletion_proposal_text(p: DeletionProposal) -> str:
    """A question GROUNDED in the row that was just read.

    It deliberately does NOT start with the ``Removed:`` marker the confirmed path uses:
    nothing was removed, and the marker is how the rest of the system tells the two apart.
    """
    return "\n".join([
        "NOT REMOVED — nothing was deleted yet. This is the company that would be removed:",
        f"  {_line(p.company)}",
        "Tell the user EXACTLY which company (name, and the CNPJ if it has one) you are about "
        "to remove and get their agreement. Only then call company_delete again with "
        f"confirm_company_id={p.confirm_company_id!r}.",
    ])


def build_server(service: Optional[CompanyService] = None, *,
                 name: str = "cogno-companies") -> FastMCP:
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
                             guidelines: str = "", segment: str = "",
                             identity_id: str = "") -> str:
        """Registers company brand parameters, visual identity, and artistic guidelines.

        company_name: the registered company or brand name (required).
        cnpj: the company's Brazilian CNPJ, if the user gave one (optional). Any format:
            '11.222.333/0001-81' or '11222333000181'. Send it ONLY as the user stated it —
            never invent or complete a number; an invalid CNPJ is refused and the whole
            registration fails.
        segment: WHAT THE COMPANY DOES — its line of business ('padaria artesanal',
            'clínica odontológica', 'varejo de moda'). This is the field for "segmento",
            "ramo", "área de atuação", "nicho".
        visual_identity: how the brand LOOKS — colours, logo, typography, design tokens.
        guidelines: how the brand SPEAKS — tone of voice, wording, what to avoid. This is
            the field for "diretrizes", "tom de voz", "comunicação".

        segment, visual_identity and guidelines are THREE separate records: a segment sent as
        guidelines replaces the brand's tone of voice and leaves the segment wrong.

        Registering a company that is already on file UPDATES its record — it does not create
        a second one — and a field you do not send is left exactly as it was.
        """
        row = svc.register(company_name, cnpj=cnpj, visual_identity=visual_identity,
                           guidelines=guidelines, segment=segment, identity_id=identity_id)
        return repr(svc.registration_payload(row))

    # ── reads ────────────────────────────────────────────────────────────────────────────
    #
    # These two are SEPARATE tools and that is a requirement, not a convenience. The host's
    # "which company are we talking about" rule is *"a search for a specific one puts that one
    # in focus; a listing chooses nothing"* — and a single tool cannot express the difference,
    # because a listing that happens to return one row would then be indistinguishable from a
    # search that found one. The intent has to be in the tool NAME or the rule cannot be
    # written. `cogno_host/company_focus.py` reads exactly this distinction.
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_companies(identity_id: str = "", role: str = "") -> str:
        """List the registered companies you can see. This CHOOSES nothing — to act on one,
        search for it by name or CNPJ first."""
        rows = svc.list_visible(identity_id=identity_id, role=role)
        note = svc.scope_note(identity_id, role)
        if not rows:
            return "\n".join(x for x in ["No companies are registered yet.", note] if x)
        return "\n".join([*(f"- {_line(c)}" for c in rows), *( [note] if note else [] )])

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def company_search(query: str, identity_id: str = "", role: str = "") -> str:
        """Find a registered company by name or CNPJ. Use this before updating or removing one.

        Matching ignores accents and case, so 'padaria sao joao' finds 'Padaria São João'.
        """
        rows = svc.search(query, identity_id=identity_id, role=role)
        note = svc.scope_note(identity_id, role)
        if not rows:
            # A limit, NOT an error: the tool worked and the answer is "none of the ones you
            # can see". Saying so in the same breath is what stops the model reporting a
            # capability failure ("não consegui acessar") for a boundary working as designed.
            return "\n".join(x for x in [f"No company you can see matches {query!r}.", note] if x)
        if len(rows) == 1:
            # EXACTLY ONE — and only this case answers with a mapping. See
            # `CompanyService.search_payload`: the count decides the SHAPE, so the host's
            # "a search for a specific one puts it in focus" needs no second count of its own.
            return repr(svc.search_payload(rows[0], note=note))
        return "\n".join([
            f"{len(rows)} companies match {query!r} — none was selected. Ask the user which "
            f"one they mean, then search again for that one:",
            *(f"- {_line(c)}" for c in rows), *( [note] if note else [] )])

    # ── writes ───────────────────────────────────────────────────────────────────────────
    #
    # Mutating, not destructive, on `_UNDOABLE`: call it again with the previous values. Same
    # shape of undo as the scheduler's `set_schedule_settings`, and performed there.
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def company_update(company_id: str, name: str = "", cnpj: str = "",
                       visual_identity: str = "", guidelines: str = "", segment: str = "",
                       identity_id: str = "", role: str = "") -> str:
        """Change a registered company's details. Send ONLY the field the user named.

        company_id: from company_search — never guessed.
        name: the registered company or brand name.
        cnpj: the Brazilian CNPJ, any format; an invalid one refuses the whole call.
        segment: WHAT THE COMPANY DOES — its line of business ('padaria artesanal',
            'clínica odontológica', 'varejo de moda'). This is the field for "segmento",
            "ramo", "área de atuação", "nicho".
        visual_identity: how the brand LOOKS — colours, logo, typography, design tokens.
        guidelines: how the brand SPEAKS — tone of voice, wording, what to avoid. This is
            the field for "diretrizes", "tom de voz", "comunicação".

        These three are SEPARATE records and writing the wrong one REPLACES it: a segment
        sent as guidelines wipes the brand's tone of voice and leaves the segment wrong.
        Read the company back with company_search first, then send only that one field.

        BEFORE calling this, tell the user WHICH field you are about to change, its current
        value and the new one ("o segmento passa de 'padaria' para 'padaria artesanal'; as
        diretrizes ficam como estão") and get their agreement. The confirmation the system
        asks for you cannot name the field — it stops the call before anything is read.

        An omitted field is LEFT AS IT IS; there is no way to blank a field here, so a
        correction can never wipe the brand guidelines you did not mention.
        """
        outcome = svc.update(company_id, name=name, cnpj=cnpj,
                             visual_identity=visual_identity, guidelines=guidelines,
                             segment=segment, identity_id=identity_id, role=role)
        return "\n".join([
            f"Updated: {_line(outcome.company)}.",
            _change_lines(outcome.changes),
            "No other field was touched. Tell the user WHICH field changed and to WHAT "
            "value — if it is not the field they named, say so and correct it.",
        ])

    # Mutating and NOT declared destructive, which for a DELETE needs saying: `destructiveHint`
    # would make gate B hold this by NAME, before it runs — and a tool gate B holds never
    # executes, so the grounded question below could never be asked. The hold is not dropped,
    # it is MOVED to the channel that can carry the per-CALL fact. The write path is
    # unreachable without `confirm_company_id`, an id the caller can only have learned from the
    # proposal, and `test_tool_annotations.py` measures that rather than believing it.
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def company_delete(company_id: str, identity_id: str = "", role: str = "",
                       confirm_company_id: str = ""):
        """Remove a registered company. TWO STEPS — destructive.

        Called with company_id alone it deletes NOTHING: it reads the record and answers with
        the company it would remove. Relay that to the user, get their agreement, then call
        this again with confirm_company_id=<the id it named>.
        """
        outcome = svc.delete(company_id, identity_id=identity_id, role=role,
                             confirm_company_id=confirm_company_id)
        if outcome.removed is not None:
            return f"Removed: {_line(outcome.removed)}."
        assert outcome.proposal is not None
        # The prose stays the text; the machine-readable half rides in the block's ``_meta``
        # beside it. ``confirm_arguments`` names the argument THIS tool needs in order to
        # commit — the vertical's own business, never invented by the layer above.
        return TextContent(
            type="text",
            text=_deletion_proposal_text(outcome.proposal),
            _meta={_META_NEEDS_CONFIRMATION: True,
                   _META_CONFIRM_ARGUMENTS: {
                       "confirm_company_id": outcome.proposal.confirm_company_id}},
        )

    # NO `help` tool, deliberately. The bookkeeper ships one and this vertical would collide
    # with it by NAME the day a persona carries both (`CompositeDispatcher` is first-wins, so
    # one of the two would silently answer for the other). The surface here is exactly the five
    # the role policy has a row for; `help_note()` stays on the service for a host that wants
    # to render it without a tool.
    return mcp


def _seeded_service() -> CompanyService:
    """Build a service from the injected per-tenant env (Postgres when a DSN is set)."""
    dsn = os.environ.get("COGNO_COMPANY_DSN") or os.environ.get("COGNO_PG_DSN")
    store: CompanyStore
    if dsn:
        from cogno_praxis.companies.stores.postgres import PgCompanyStore
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
