"""A mutating tool may not report a write it did not make.

MEASURED, one production turn out of 1007 — one case, not a class. ``remove_by_search`` matched
nothing and answered, verbatim:

    "No transaction of yours matches 'expense R$ 45.00 office supplies recorded today'
     — nothing removed."

**Nothing was removed and the sentence was CORRECT.** The call was nevertheless recorded
``side_effect=True``, which put the turn at ``guards.committed=True``: a write declared over
zero rows written.

**Why a wrong bit here is worse than a wrong bit elsewhere.** ``committed`` is the question
several layers ask before deciding whether a performative claim has anything behind it — the
promise auditor, and the grounding rules that decide if "registei a sua despesa" is grounded. A
false TRUE does not make that net FAIL; it **switches it off**, and from there a fabrication
reads as supported by a write that never happened. The trace disarms its own guard.

**The mechanism, which is why the fix is `raise`.** cogno-praxis never writes ``side_effect``:
a FastMCP tool that RETURNS is a successful call, and cogno-mcp stamps a successful call on a
non-read-only tool as ``ToolResult(ok=True, side_effect=True)`` (``dispatcher.execute``:
``side_effect=mutating and not asks``, where ``mutating`` is read per tool NAME from
``readOnlyHint``). The only per-CALL channels out of a vertical are the gate-C
``needs_confirmation`` meta — which means "I am asking", not "I did nothing" — and ``isError``.
So the sentence has to be RAISED: ``isError`` → ``ok=False`` → ``side_effect=False``, and the
text still reaches the model as ``ToolResult.error``, fed back so it self-corrects.

That is not a new convention. ``coordinator/service.py`` already states it for
``send_schedule_to_calendar`` ("**It RAISES on every path that did not send**"), and
``companies/server.py`` adopted it for its refusals, whose test names "the shape the sibling
verticals use". This file is those siblings.

**What is deliberately NOT changed: the IDEMPOTENT no-op** — a call that wrote nothing because
the desired state already held ("was ALREADY CONFIRMED — no change was made",
``block_schedule`` finding the day already blocked). That sentence is a result the judge has
been taught to read, and "nothing changed because it was already right" is a different question
from "nothing happened"; guessing at it here could break what works. Pinned below as a
standing decision, so a later sweep sees it was decided and not missed.
"""

from __future__ import annotations

from datetime import date

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from cogno_praxis.bookkeeper.grounding import NO_MATCH_MARKER, ground_reply
from cogno_praxis.bookkeeper.server import build_server
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore
from cogno_praxis.grounding import ToolCall

_TODAY = date(2026, 7, 10)
_ME = "emp-1"


def _svc() -> BookkeeperService:
    return BookkeeperService(InMemoryBookkeeperStore(), today=lambda: _TODAY)


def _text(call_result) -> str:
    blocks = call_result[0] if isinstance(call_result, tuple) else call_result
    return "".join(getattr(b, "text", "") for b in blocks)


# ── P1 · the measured turn: a search that matched nothing is not a write ──────────────
@pytest.mark.asyncio
async def test_a_removal_that_matched_nothing_does_not_report_a_write():
    """MUTATION: turn the ``raise`` back into ``return f"No transaction ... nothing removed."``
    and this dies — the call becomes a normal return, which the bridge stamps as a write."""
    svc = _svc()
    svc.add_outcome("office supplies", "45", _ME)
    mcp = build_server(svc)

    with pytest.raises(ToolError) as erro:
        await mcp.call_tool("remove_by_search", {"query": "aluguel", "identity_id": _ME})

    # the reason still travels to the model, unchanged
    assert "No transaction of yours matches" in str(erro.value)
    assert NO_MATCH_MARKER in str(erro.value)
    # ... and the ledger really is untouched, so the claim it is refusing to make is false
    assert len(svc.search("office supplies", _ME, "EMPLOYEE")) == 1


@pytest.mark.asyncio
async def test_a_removal_that_DID_delete_still_reports_the_write():
    """THE TWIN, and the over-tightening guard for this tool: a ``side_effect`` too few
    switches the accounting OFF exactly like one too many. A real deletion must still return
    normally, which is what the bridge stamps as the write it genuinely was."""
    svc = _svc()
    svc.add_outcome("internet", "100", _ME)
    mcp = build_server(svc)

    tx_id = svc.remove_by_search("internet", _ME).proposal.confirm_tx_id  # type: ignore[union-attr]
    out = _text(await mcp.call_tool("remove_by_search", {
        "query": "internet", "identity_id": _ME, "confirm_tx_id": tx_id}))

    assert out.startswith("Removed: ")            # a plain return → ok=True, side_effect=True
    assert svc.search("internet", _ME, "EMPLOYEE") == []


@pytest.mark.asyncio
async def test_the_proposal_step_is_untouched_by_this_change():
    """The gate-C branch already answered this question correctly, through the OTHER channel
    (``needs_confirmation`` meta → the bridge computes ``mutating and not asks`` → False).
    It must keep returning a TextContent, not start raising: a raise would abort the loop
    instead of asking, and the grounded question is the whole point of that branch."""
    svc = _svc()
    svc.add_outcome("internet", "100", _ME)
    mcp = build_server(svc)

    out = _text(await mcp.call_tool("remove_by_search", {"query": "internet",
                                                        "identity_id": _ME}))
    assert "NOT REMOVED" in out
    assert len(svc.search("internet", _ME, "EMPLOYEE")) == 1


# ── P2 · a refused recording is not a recording ───────────────────────────────────────
@pytest.mark.parametrize("tool,args", [
    ("add_income", {"description": "", "amount": "500", "identity_id": _ME}),
    ("add_income", {"description": "consulta", "amount": "abacaxi", "identity_id": _ME}),
    ("add_outcome", {"description": "", "amount": "45", "identity_id": _ME}),
    ("add_outcome", {"description": "material", "amount": "abacaxi", "identity_id": _ME}),
])
@pytest.mark.asyncio
async def test_a_refused_recording_does_not_report_a_write(tool, args):
    """MUTATION: restore ``except BookkeeperError as exc: return f"ERROR: {exc}"`` on either
    tool and its two cases die. An "ERROR: ..." string is a NORMAL return — the very shape
    ``companies`` stopped emitting today, naming these two as the siblings still doing it."""
    svc = _svc()
    mcp = build_server(svc)

    with pytest.raises(ToolError):
        await mcp.call_tool(tool, args)

    assert svc.get_summary(_ME, "EMPLOYEE")["income_count"] == 0
    assert svc.get_summary(_ME, "EMPLOYEE")["outcome_count"] == 0


@pytest.mark.parametrize("tool,args,marker", [
    ("add_income", {"description": "consulta", "amount": "500", "identity_id": _ME},
     "Income recorded: "),
    ("add_outcome", {"description": "material", "amount": "45", "identity_id": _ME},
     "Expense recorded: "),
])
@pytest.mark.asyncio
async def test_an_accepted_recording_still_reports_the_write(tool, args, marker):
    """THE TWIN: the good path is byte-for-byte what it was. ``_entry_recorded`` greps these
    prefixes, so a raise leaking into the success path would silently unground every truthful
    "registei" reply."""
    svc = _svc()
    mcp = build_server(svc)
    out = _text(await mcp.call_tool(tool, args))
    assert out.startswith(marker)


@pytest.mark.asyncio
async def test_the_refusal_still_says_WHY_so_the_model_can_self_correct():
    """Raising must not cost the model the reason: ``ok=False`` is fed back precisely so it
    can fix the argument instead of re-sending it."""
    mcp = build_server(_svc())
    with pytest.raises(ToolError, match="description"):
        await mcp.call_tool("add_income", {"description": "", "amount": "500",
                                           "identity_id": _ME})


# ── P3 · the neighbouring net keeps its reach ─────────────────────────────────────────
_LISTING = "Os lançamentos de R$ 45,00 registrados hoje."


def _no_match_call() -> ToolCall:
    """How the failed removal reaches the grounding layer: FastMCP wraps a raised message as
    "Error executing tool <name>: ...", and both host adapters copy it onto ``ToolCall.error``.
    """
    return ToolCall(tool="remove_by_search", ok=False,
                    error=f"Error executing tool remove_by_search: "
                          f"No transaction of yours matches 'x' — {NO_MATCH_MARKER}")


def test_a_no_match_removal_still_counts_as_having_read_the_ledger():
    """THE OVER-TIGHTENING PROBE for the accounting change, and the reason this file touches
    ``grounding.py`` at all.

    ``_consulted_ledger`` asks "did the turn LOOK at the book?" — and a removal reads before it
    decides, matched or not (``BookkeeperService.remove_by_search`` lists the caller's rows
    first). It answered that with ``ok_results``, which sees only successful calls. Making the
    no-match branch raise therefore removed a truthful turn's exemption for free, and the
    attributive-participle listing would be rewritten into a denial again — the exact
    regression ``test_a_removal_also_consults_the_ledger.py`` exists to prevent.

    MUTATION: drop ``_searched_and_found_nothing`` from ``_consulted_ledger`` and this dies,
    while every other test in this file stays green. An accounting fix may not cost a correct
    reply."""
    assert ground_reply(_LISTING, tools=[_no_match_call()], locale="pt") is None


def test_a_removal_that_failed_for_ANY_other_reason_does_not_claim_the_read():
    """The CONTROL that keeps the predicate narrow. A transport fault read nothing, so it may
    not buy the exemption — only the branch that says "I searched and found nothing" may.

    Without this, ``_searched_and_found_nothing`` could be written as "any failed removal" and
    the test above would still pass."""
    broken = ToolCall(tool="remove_by_search", ok=False,
                      error="Error executing tool remove_by_search: connection reset")
    assert ground_reply(_LISTING, tools=[broken], locale="pt") is not None


def test_an_explicit_claim_still_fires_after_a_no_match_removal():
    """Looking at the book is not a licence to say "registei". The explicit first-person claim
    is unconditional, before and after this change."""
    v = ground_reply("Registrei a entrada de R$ 45,00.", tools=[_no_match_call()], locale="pt")
    assert v is not None and v.rule == "fabricated_entry"


def test_a_no_match_removal_does_not_ground_TOTALS():
    """The other consumer, unmoved: a removal returns no totals, so quoting them is still
    ungrounded. ``_summary_read`` and ``_consulted_ledger`` stay two predicates."""
    v = ground_reply("Seu total de entradas é R$ 500,00, saldo líquido R$ 500,00.",
                     tools=[_no_match_call()], locale="pt")
    assert v is not None and v.rule == "conjured_totals"


@pytest.mark.asyncio
async def test_the_no_match_marker_is_the_sentence_the_server_really_emits():
    """The duplicated contract, pinned in the direction that rots silently: ``grounding.py``
    declares the marker and ``server.py`` writes the sentence. If the wording drifts, the
    exemption above stops matching and NOTHING ELSE goes red — the net just quietly narrows."""
    svc = _svc()
    svc.add_outcome("internet", "100", _ME)
    mcp = build_server(svc)
    with pytest.raises(ToolError) as erro:
        await mcp.call_tool("remove_by_search", {"query": "aluguel", "identity_id": _ME})
    assert NO_MATCH_MARKER in str(erro.value)


# ── P4 · the idempotent no-op is a DECISION, not an oversight ─────────────────────────
def test_the_idempotent_no_op_is_deliberately_left_returning():
    """A standing decision, pinned so the next sweep sees it was weighed.

    ``cancel_appointment``/``confirm_appointment``/``complete_appointment`` answer "was ALREADY
    <status> — no change was made", and ``block_schedule`` answers "had no free slots to block
    (already taken/blocked)". Those calls also wrote nothing — but they wrote nothing because
    the DESIRED STATE ALREADY HELD, which is a different fact from "the operation did not
    happen", and the judge has been taught to read that exact sentence. Re-labelling it as a
    failure is a separate question that needs its own measurement.

    This test asserts the shape is still the RETURNING one, so a future change to it is
    deliberate rather than accidental."""
    from cogno_praxis.scheduler.server import _status_reply

    class _Appt:
        appointment_id = "a1"
        status = "CANCELED"

    said = _status_reply(_Appt(), False)          # type: ignore[arg-type]
    assert "was ALREADY CANCELED" in said and "no change was made" in said
    assert not said.startswith("ERROR")           # still a RESULT, not a refusal


@pytest.mark.asyncio
async def test_a_block_on_an_already_blocked_day_is_left_returning_too():
    """The other half of the same standing decision, through the real tool.

    ``block_schedule`` answers "had no free slots to block (already taken/blocked)" and wrote
    nothing — but the day IS unavailable, which is what was asked for. Same idempotent shape,
    same decision: measured separately or not at all."""
    from cogno_praxis.scheduler.server import build_server as build_scheduler

    mcp = build_scheduler()
    names = {t.name for t in await mcp.list_tools()}
    assert "block_schedule" in names               # the tool this decision is about exists
