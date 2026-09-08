"""The ``company`` MCP surface, and the CONTRACT it owes a host it cannot import.

Two of these tests are not about this repo at all, and that is why they are here rather than in
the host. ``cogno_host/company_focus.py`` decides which company a session is talking about by

  1. matching the tool NAME ``company_registration`` (its ``_TOCAM`` tuple), and
  2. parsing the tool's ANSWER with ``ast.literal_eval`` and reading ``company_id`` /
     ``company_name`` out of it.

Neither of those fails loudly when it breaks. A rename or a re-shaped answer leaves every test
in both repos green, the reply to the contact stays plausible, and the NEXT turn plans for the
wrong company. The host cannot guard it alone — the change that breaks it happens HERE — so the
pin lives on this side too, written in the host's own terms (``literal_eval``, those two keys).
"""

from __future__ import annotations

import ast

import pytest
from mcp.types import TextContent

from cogno_praxis.companies import CompanyService, InMemoryCompanyStore  # noqa: F401
from cogno_praxis.companies.server import build_server

_CNPJ_OK = "11.222.333/0001-81"
_CNPJ_BAD = "11.222.333/0001-99"


def _server():
    return build_server(CompanyService(InMemoryCompanyStore()))


async def _call(mcp, **args) -> str:
    blocks, _ = await mcp.call_tool("company_registration", args)
    assert len(blocks) == 1, (
        "ONE content block: cogno-mcp joins several with '\\n', and anything after the mapping "
        "makes the host's ast.literal_eval raise — which fails CLOSED and silently drops the focus")
    assert isinstance(blocks[0], TextContent)
    return blocks[0].text


# ── the NAME is a contract with the host ────────────────────────────────────────────────
async def test_the_tool_is_named_company_registration():
    """``cogno_host/company_focus.py`` reads the turn's executions BY THESE NAMES (``_TOCAM``).
    A rename breaks nothing loudly: the focus just stops moving."""
    names = {t.name for t in await _server().list_tools()}
    assert "company_registration" in names, "the write the host's focus watches"
    assert "company_search" in names, "the read the host's focus watches"


async def test_the_tool_is_declared_mutating_and_not_destructive():
    """``readOnlyHint=False`` is where this tool is classified as a WRITE: it reaches cogno-mcp's
    ``is_mutating``, and the host wraps every module source in ``WriteConfirmingDispatcher`` —
    the same gate that held it as a cortex skill. No ``destructiveHint``: it is on ``_UNDOABLE``
    in ``test_tool_annotations.py`` (register again → the row UPDATES)."""
    ann = (await _server().list_tools())[0].annotations
    assert ann is not None and ann.readOnlyHint is False
    assert getattr(ann, "destructiveHint", None) is not True


# ── the ANSWER is a contract with the host ──────────────────────────────────────────────
async def test_the_answer_is_a_python_literal_the_host_can_parse():
    """The host parses this with ``ast.literal_eval``, so the answer must be a Python literal.

    JSON is NOT automatically one: ``true``/``false``/``null`` raise. Annotating this tool
    ``-> dict`` would make FastMCP serialise with ``pydantic_core.to_json`` and produce exactly
    that — which starts with ``{``, passes the host's guard, and then fails closed."""
    text = await _call(_server(), company_name="Padaria Sol Nascente")
    assert text.startswith("{"), "the host's guard is `texto.startswith('{')`"
    assert isinstance(ast.literal_eval(text), dict)


async def test_the_answer_carries_the_two_keys_the_focus_reads():
    payload = ast.literal_eval(await _call(_server(), company_name="Padaria Sol Nascente"))
    assert payload["company_id"] == "padaria-sol-nascente"
    assert payload["company_name"] == "Padaria Sol Nascente"


async def test_the_answer_grounds_the_read_back_on_what_LANDED():
    """``cnpj`` is the stored, normalised form — the difference between confirming a record and
    repeating the argument the contact typed."""
    payload = ast.literal_eval(await _call(_server(), company_name="Acme", cnpj=_CNPJ_OK))
    assert payload["cnpj"] == "11222333000181"


async def test_the_payload_keys_are_exactly_the_ones_the_native_skill_produced():
    """Frozen against ``cogno_host/company_registration.py`` as it stood before the move. A key
    ADDED here is harmless; a key RENAMED or DROPPED is how the focus dies quietly."""
    payload = ast.literal_eval(await _call(_server(), company_name="Acme"))
    assert set(payload) >= {"company_id", "company_name", "cnpj", "visual_identity",
                            "guidelines", "message"}


# ── a refusal must be ok=False, not a string that reads like success ─────────────────────
@pytest.mark.parametrize("args", [
    {"company_name": ""},
    {"company_name": "Acme", "cnpj": _CNPJ_BAD},
])
async def test_a_refusal_RAISES_instead_of_returning_an_ERROR_string(args):
    """Measured through the real chain 2026-09-06: a RETURNED ``"ERROR: ..."`` is a normal
    return, so cogno-mcp builds ``ToolResult(ok=True, side_effect=True)`` — the shape the
    sibling verticals use, and the shape that would record a refused registration as a
    committed write. The host-native skill this replaces answered ``ok=False``; raising is how
    that survives the move.

    ``tests/integration/test_company_via_mcp.py`` performs the other half — that a raise really
    does arrive as ``ok=False`` at the dispatcher."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await _server().call_tool("company_registration", args)


async def test_a_refused_registration_stored_nothing():
    svc = CompanyService(InMemoryCompanyStore())
    mcp = build_server(svc)
    with pytest.raises(Exception):
        await mcp.call_tool("company_registration", {"company_name": "Acme", "cnpj": _CNPJ_BAD})
    assert svc.list_companies() == []


async def test_the_refusal_text_still_reaches_the_model_naming_the_field():
    """It travels as ``ToolResult.error``, fed back so the model can self-correct — which only
    works if it says WHICH argument is wrong."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match="cnpj"):
        await _server().call_tool("company_registration",
                                  {"company_name": "Acme", "cnpj": _CNPJ_BAD})


# ── the seam ────────────────────────────────────────────────────────────────────────────
async def test_build_server_without_a_service_still_works():
    """The standalone demo path: an in-memory service is built when none is injected."""
    assert "company_registration" in {t.name for t in await build_server().list_tools()}


def test_the_seeded_service_is_in_memory_without_a_dsn(monkeypatch):
    from cogno_praxis.companies.server import _seeded_service

    monkeypatch.delenv("COGNO_COMPANY_DSN", raising=False)
    monkeypatch.delenv("COGNO_PG_DSN", raising=False)
    assert isinstance(_seeded_service().store, InMemoryCompanyStore)


async def test_the_answer_is_a_repr_and_not_json():
    """The MECHANISM, pinned — not the current key set.

    Both forms parse today, because every value in this payload is a string and a JSON string is
    also a Python literal. They stop agreeing the moment a value is not: ``repr`` renders
    ``True``, ``pydantic_core.to_json`` renders ``true``, and only one of those is something
    ``ast.literal_eval`` will read. Asserting "the host can parse it" therefore does NOT
    discriminate — it passes under both — so this asserts the form itself.
    """
    text = await _call(_server(), company_name="Acme")
    assert text == repr(ast.literal_eval(text)), (
        "the answer must be repr(mapping). A JSON rendering (what annotating the tool `-> dict` "
        "produces) parses only while every value is a string; add one bool and the host's "
        "ast.literal_eval raises and the company focus dies silently.")


def test_a_boolean_is_what_separates_the_two_renderings():
    """Why the paragraph above is not hypothetical, performed on the two renderings directly."""
    import json

    payload = {"company_id": "acme", "was_update": True}
    assert ast.literal_eval(repr(payload)) == payload
    with pytest.raises(ValueError):
        ast.literal_eval(json.dumps(payload))


# ══════════════════════════════════════════════════════════════════════════════════════════
#  THE FOCUS RULE, encoded in the SHAPE of an answer
#
#  The owner's rule: *"registered one just now, use it; searched for a SPECIFIC one, use it;
#  more than one, ask which."* The host reads the turn's tool answers to decide
#  (`cogno_host.company_focus`), parsing them with `ast.literal_eval` and failing CLOSED.
#
#  So the count decides the SHAPE here, once, and no second count has to agree with it across
#  two repositories: exactly one match answers with a mapping; zero, several and every listing
#  answer in prose, which the host's parser rejects on its own.
#
#  Four twins, one per branch, because a read that moved the focus by accident would give a
#  LOOKUP the effect of a WRITE on session state.
# ══════════════════════════════════════════════════════════════════════════════════════════

def _parses_as_a_company(text: str):
    """The host's rule, in the host's own terms — it cannot be imported from here."""
    text = (text or "").strip()
    if not text.startswith("{"):
        return None
    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None
    return data if isinstance(data, dict) and data.get("company_id") else None


async def _peopled_server():
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Padaria Sol Nascente", identity_id="u1")
    svc.register("Padaria Central", identity_id="u1")
    svc.register("Acme", identity_id="outro")
    return build_server(svc), svc


async def _text(mcp, tool, **args) -> str:
    blocks, _ = await mcp.call_tool(tool, args)
    return blocks[0].text


async def test_TWIN_1_a_listing_chooses_nothing_even_when_it_has_one_row():
    """The branch that would be easiest to get wrong: with a single company on file, a listing
    and a one-hit search return the same INFORMATION and must not return the same SHAPE."""
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Padaria Sol Nascente", identity_id="u1")
    mcp = build_server(svc)
    listed = await _text(mcp, "list_companies", identity_id="u1", role="ADMIN")
    assert _parses_as_a_company(listed) is None, "a listing must never move the focus"
    found = await _text(mcp, "company_search", query="Sol", identity_id="u1", role="ADMIN")
    assert _parses_as_a_company(found) is not None, "one hit must move it"


async def test_TWIN_2_a_search_with_exactly_one_hit_selects_that_company():
    mcp, _ = await _peopled_server()
    got = _parses_as_a_company(
        await _text(mcp, "company_search", query="Sol", identity_id="u1", role="ADMIN"))
    assert got is not None and got["company_id"] == "padaria-sol-nascente"


async def test_TWIN_3_a_search_with_several_hits_selects_nothing_and_says_to_ask():
    mcp, _ = await _peopled_server()
    text = await _text(mcp, "company_search", query="Padaria", identity_id="u1", role="ADMIN")
    assert _parses_as_a_company(text) is None
    assert "which one" in text.lower() or "none was selected" in text.lower()


async def test_TWIN_3b_a_search_with_no_hits_selects_nothing():
    mcp, _ = await _peopled_server()
    assert _parses_as_a_company(
        await _text(mcp, "company_search", query="Nada", identity_id="u1", role="ADMIN")) is None


async def test_TWIN_4_a_scoped_caller_cannot_focus_a_company_by_REACHING_for_it():
    """The one that matters: a visitor who searches for someone else's company must not end
    the turn with it in focus for having tried. It is not refused — it is not THERE."""
    mcp, _ = await _peopled_server()
    text = await _text(mcp, "company_search", query="Acme", identity_id="u1", role="GUEST")
    assert _parses_as_a_company(text) is None
    # The query is ECHOED — the visitor typed "Acme" themselves, and repeating it back is not
    # disclosure. What must not appear is anything only the STORE knows, which is the id.
    assert "(id:" not in text, "no record of a company outside the caller's scope may leak"
    assert "cadastrou" in text, "and the boundary is stated, not left as an empty result"


async def test_the_limit_travels_INSIDE_the_mapping_not_after_it():
    """A note appended as a trailing line would put text after the mapping, and the host parses
    the WHOLE answer as one Python literal — the limit would silently kill the focus."""
    mcp, _ = await _peopled_server()
    got = _parses_as_a_company(
        await _text(mcp, "company_search", query="Sol", identity_id="u1", role="GUEST"))
    assert got is not None and "cadastrou" in got.get("note", "")


# ── the surface the role policy has a row for, and nothing else ──────────────────────────
async def test_the_vertical_offers_exactly_five_tools():
    """No `help`: the bookkeeper ships one and `CompositeDispatcher` is first-wins, so a
    persona carrying both would have one silently answer for the other."""
    assert {t.name for t in await _server().list_tools()} == {
        "company_registration", "list_companies", "company_search",
        "company_update", "company_delete"}


@pytest.mark.parametrize("tool,read_only", [
    ("company_registration", False), ("list_companies", True), ("company_search", True),
    ("company_update", False), ("company_delete", False)])
async def test_every_tool_declares_whether_it_writes(tool, read_only):
    ann = {t.name: t.annotations for t in await _server().list_tools()}[tool]
    assert ann is not None and ann.readOnlyHint is read_only
    # None of them is gate-B destructive: the delete asks for itself (gate C) and the two
    # others are undoable. `test_tool_annotations.py` owns that claim for every vertical.
    assert getattr(ann, "destructiveHint", None) is not True


async def test_the_delete_proposal_carries_the_gate_C_meta():
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Acme", identity_id="u1")
    # `company_delete` carries no return annotation (it answers a bare content block on the
    # proposal path), so `call_tool` hands back the blocks alone rather than a pair.
    result = await build_server(svc).call_tool(
        "company_delete", {"company_id": "acme", "identity_id": "u1", "role": "ADMIN"})
    blocks = result[0] if isinstance(result, tuple) else result
    meta = getattr(blocks[0], "meta", None) or getattr(blocks[0], "_meta", None) or {}
    assert meta.get("cogno-mcp/needs_confirmation") is True
    # The named argument is a one-time TOKEN this call minted, not the id the caller sent.
    asked = meta.get("cogno-mcp/confirm_arguments") or {}
    assert set(asked) == {"confirm_token"} and asked["confirm_token"]
    assert "NOT REMOVED" in blocks[0].text
    # THE TOKEN IS NOT IN THE TEXT, and this is the load-bearing half: the text is what the
    # MODEL reads, so a token printed there is a token the model can put straight back into a
    # second call without anybody being asked — which is exactly how the previous version
    # taught the shortcut it was meant to close.
    assert asked["confirm_token"] not in blocks[0].text
    assert "confirm_token" not in blocks[0].text
    assert svc.get("acme") is not None


# ── the tool answers a person will read, and the failure paths behind them ───────────────
async def test_a_company_line_names_everything_the_record_holds():
    """The read tools' whole job is to let the model say something TRUE about a company. A line
    that dropped the CNPJ or the brand guidelines would make it guess or omit."""
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Acme", cnpj=_CNPJ_OK, visual_identity="azul", guidelines="tom formal",
                 identity_id="u1")
    svc.update("acme", segment="varejo", identity_id="u1", role="ADMIN")
    line = await _text(build_server(svc), "list_companies", identity_id="u1", role="ADMIN")
    for expected in ("Acme", "acme", "11222333000181", "varejo", "azul", "tom formal"):
        assert expected in line, expected


async def test_an_empty_store_says_so_rather_than_answering_with_nothing():
    text = await _text(build_server(CompanyService(InMemoryCompanyStore())),
                       "list_companies", identity_id="u1", role="ADMIN")
    assert "No companies are registered yet." in text
    assert _parses_as_a_company(text) is None


async def test_the_update_tool_reports_what_it_wrote():
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Acme", identity_id="u1")
    text = await _text(build_server(svc), "company_update", company_id="acme",
                       segment="varejo", identity_id="u1", role="ADMIN")
    assert text.startswith("Updated:") and "varejo" in text


async def test_the_confirmed_delete_reports_the_row_that_LEFT():
    """The `Removed:` marker is how the rest of the system tells a commit from a proposal —
    the proposal deliberately does not carry it."""
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Acme", identity_id="u1")
    server = build_server(svc)
    proposal = await server.call_tool(
        "company_delete", {"company_id": "acme", "identity_id": "u1", "role": "ADMIN"})
    first = proposal[0] if isinstance(proposal, tuple) else proposal
    meta = getattr(first[0], "meta", None) or getattr(first[0], "_meta", None) or {}
    token = (meta.get("cogno-mcp/confirm_arguments") or {})["confirm_token"]
    result = await server.call_tool(
        "company_delete", {"company_id": "acme", "identity_id": "u1", "role": "ADMIN",
                           "confirm_token": token})
    blocks = result[0] if isinstance(result, tuple) else result
    assert blocks[0].text.startswith("Removed:")
    assert svc.get("acme") is None
