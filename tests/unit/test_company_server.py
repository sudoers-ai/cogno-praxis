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

from cogno_praxis.company import CompanyService, InMemoryCompanyStore
from cogno_praxis.company.server import build_server

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
    """``cogno_host/company_focus.py`` reads the turn's executions BY THIS NAME (``_TOCAM``).
    A rename breaks nothing loudly: the focus just stops moving."""
    assert [t.name for t in await _server().list_tools()] == ["company_registration"]


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
    assert [t.name for t in await build_server().list_tools()] == ["company_registration"]


def test_the_seeded_service_is_in_memory_without_a_dsn(monkeypatch):
    from cogno_praxis.company.server import _seeded_service

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
