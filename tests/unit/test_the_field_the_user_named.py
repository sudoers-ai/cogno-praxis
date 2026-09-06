"""«Corrige o SEGMENTO» must not arrive as ``guidelines`` — and must not take a neighbour with it.

The measured turn: the contact asked for the segment to be corrected, the model called
``company_update(guidelines='artisanal bakery')``, and the brand guidelines that were on file
were REPLACED. The contact asked to correct one field and lost another.

Three halves, and they are proved by different things — said plainly here because only one of
them is a gate:

* **which COLUMN a given argument writes** is code, and it is pinned below in both directions.
  ``segment`` reaching the segment was already true on the base commit; the twin is a
  regression pin, not a repair, and the mutation section of the PR says so.
* **which ARGUMENT the model picks** is the model's, and the only lever this repo owns is the
  tool description — which is why the description is pinned per field, with the Portuguese
  words a contact actually uses attached to the field they mean. A description that does not
  distinguish "segmento" from "diretrizes" cannot be obeyed, however good the model.
* **what a REGISTRATION leaves behind** is code, and it was broken: registering a company
  already on file — the documented way to correct one — rebuilt the row from the arguments
  given and blanked the rest.

The third is the one that loses data with no model in the loop at all.
"""

from __future__ import annotations

import re

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from cogno_praxis.companies import CompanyError, CompanyService, InMemoryCompanyStore
from cogno_praxis.companies.server import build_server

_CNPJ_OK = "11.222.333/0001-81"


def _svc() -> CompanyService:
    """One company on file with every field populated — so a wipe has something to wipe."""
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Padaria Sol", cnpj=_CNPJ_OK, segment="padaria",
                 visual_identity="azul e branco", guidelines="tom informal e caloroso",
                 identity_id="u1")
    return svc


async def _update(svc: CompanyService, **args) -> str:
    blocks = await build_server(svc).call_tool(
        "company_update", {"company_id": "padaria-sol", "identity_id": "u1",
                           "role": "ADMIN", **args})
    blocks = blocks[0] if isinstance(blocks, tuple) else blocks
    return blocks[0].text


def _brand(svc: CompanyService, key: str) -> str:
    return str((svc.get("padaria-sol").visual_identity or {}).get(key) or "")


# ── the two twins: the named field moves, and ONLY it ───────────────────────────────────
async def test_correcting_the_SEGMENT_writes_the_segment_and_leaves_the_guidelines_alone():
    svc = _svc()
    await _update(svc, segment="padaria artesanal")
    assert svc.get("padaria-sol").segment == "padaria artesanal"
    assert _brand(svc, "guidelines") == "tom informal e caloroso"
    assert _brand(svc, "visual_identity") == "azul e branco"


async def test_correcting_the_GUIDELINES_writes_the_guidelines_and_leaves_the_segment_alone():
    """The negative twin, and it is not decoration: without it, a fix that routed every
    correction to ``segment`` would trade one wrong field for the opposite wrong field and the
    twin above would still be green."""
    svc = _svc()
    await _update(svc, guidelines="tom formal e técnico")
    assert _brand(svc, "guidelines") == "tom formal e técnico"
    assert svc.get("padaria-sol").segment == "padaria"
    assert _brand(svc, "visual_identity") == "azul e branco"


# ── the answer NAMES the field and the value ────────────────────────────────────────────
async def test_the_answer_names_the_FIELD_and_the_NEW_VALUE():
    """A company line rendered after the write reads the same whether the right field moved or
    the wrong one did. The field name is the only part of the answer that can be checked
    against what the contact asked for."""
    text = await _update(_svc(), segment="padaria artesanal")
    assert "CHANGED segment:" in text
    assert "'padaria artesanal'" in text
    assert "'padaria'" in text            # …and what it was, so a replacement is visible
    assert text.startswith("Updated:")    # the commit marker the rest of the system reads


async def test_the_answer_names_the_WRONG_field_just_as_plainly():
    """The measured call. The answer has to make the mistake legible to the model that must
    read it back — «CHANGED guidelines» beside a request about the segment is the whole point,
    and a summary that named only the company would hide it."""
    text = await _update(_svc(), guidelines="artisanal bakery")
    assert "CHANGED guidelines: 'tom informal e caloroso' → 'artisanal bakery'" in text
    assert "segment" not in text.split("CHANGED")[1]


async def test_only_the_fields_that_MOVED_are_reported():
    text = await _update(_svc(), segment="padaria artesanal", guidelines="tom informal e caloroso")
    assert text.count("CHANGED ") == 1, "the guidelines were re-sent unchanged — nothing moved"
    assert "CHANGED segment:" in text


async def test_what_is_REPORTED_is_what_is_WRITTEN():
    """The report and the write must read the arguments ONCE. They used to read them twice, and
    a whitespace-only ``segment`` fell through the gap: not reported (it strips to nothing) and
    written anyway (it is truthy) — an unreported write, which is a quieter version of the
    defect this answer exists to make loud."""
    svc = _svc()
    text = await _update(svc, name="Padaria Sol Nascente", segment="   ")
    assert svc.get("padaria-sol").segment == "padaria", "whitespace was written unreported"
    assert "CHANGED segment" not in text
    assert "CHANGED name: 'Padaria Sol' → 'Padaria Sol Nascente'" in text


# ── a call that changes nothing must not report a write ─────────────────────────────────
async def test_an_update_with_no_field_is_REFUSED_rather_than_reported_as_a_write():
    """A mutating tool that RETURNS comes back as ``ToolResult(ok=True, side_effect=True)`` —
    a write that never happened, counted by the host's ``committed_this_turn``."""
    with pytest.raises(CompanyError) as exc:
        _svc().update("padaria-sol", identity_id="u1", role="ADMIN")
    assert "`segment`" in str(exc.value) and "`guidelines`" in str(exc.value)


async def test_an_update_to_the_value_already_on_file_is_REFUSED_and_says_so():
    with pytest.raises(CompanyError) as exc:
        _svc().update("padaria-sol", segment="padaria", identity_id="u1", role="ADMIN")
    assert "já está assim" in str(exc.value)
    assert "`segment` já é 'padaria'" in str(exc.value)


async def test_the_no_op_update_RAISES_through_the_MCP_surface():
    """The property #104 established for the bookkeeper, on this tool: a refusal that RETURNS
    carries no ``isError``, so cogno-mcp builds ``ToolResult(ok=True, side_effect=True)`` and
    the turn is stamped as having committed. Raising is what keeps ``committed_this_turn``
    honest about a call that touched nothing."""
    svc = _svc()
    with pytest.raises(ToolError):
        await build_server(svc).call_tool(
            "company_update", {"company_id": "padaria-sol", "segment": "padaria",
                               "identity_id": "u1", "role": "ADMIN"})
    assert svc.get("padaria-sol").segment == "padaria"


# ── (a) the segment gets a writer on the REGISTRATION path ──────────────────────────────
async def test_a_registration_can_state_the_SEGMENT():
    """The column existed and only ``company_update`` could fill it: a company registered in
    one turn had no segment until somebody corrected it in another."""
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Padaria Sol", segment="padaria artesanal", identity_id="u1")
    assert svc.get("padaria-sol").segment == "padaria artesanal"


async def test_the_registration_answer_carries_the_segment_it_stored():
    svc = CompanyService(InMemoryCompanyStore())
    row = svc.register("Padaria Sol", segment="padaria artesanal", identity_id="u1")
    assert svc.registration_payload(row)["segment"] == "padaria artesanal"


async def test_a_store_that_fails_the_MERGE_read_still_refuses_recoverably():
    """The merge added a READ to a method whose whole error contract was written around the
    write. A raw store exception escaping here is wrapped in ``ToolExecutionError`` by the EGO
    and PROPAGATED — a Postgres blip would kill the turn instead of letting the model say it
    could not register right now."""
    class _Broken(InMemoryCompanyStore):
        def get(self, company_id):                     # type: ignore[override]
            raise RuntimeError("connection reset by peer at 10.0.0.1")

    with pytest.raises(CompanyError) as exc:
        CompanyService(_Broken()).register("Padaria Sol", identity_id="u1")
    assert "RuntimeError" in str(exc.value)            # the CLASS travels…
    assert "10.0.0.1" not in str(exc.value)            # …and the message does not


# ── (a′) the loss that needs no model: a re-registration correcting ONE field ────────────
@pytest.mark.parametrize("corrected,survivors", [
    ("guidelines", ("cnpj", "segment", "visual_identity")),
    ("visual_identity", ("cnpj", "segment", "guidelines")),
    ("segment", ("cnpj", "visual_identity", "guidelines")),
])
async def test_re_registering_to_correct_ONE_field_keeps_the_others(corrected, survivors):
    """``company_registration`` PROMISES that registering a company already on file updates its
    record. On the base commit it rebuilt the row from the arguments given, so the store's
    ``ON CONFLICT ... SET cnpj = EXCLUDED.cnpj`` (and segment, and visual_identity) wrote the
    defaults over what was there. Correcting the tone of voice cost the CNPJ, the segment and
    the visual identity at once — no model involved, and nothing red anywhere."""
    svc = _svc()
    svc.register("Padaria Sol", identity_id="u1", **{corrected: "corrigido"})
    row = svc.get("padaria-sol")
    stored = {"cnpj": row.cnpj, "segment": row.segment,
              "visual_identity": str((row.visual_identity or {}).get("visual_identity") or ""),
              "guidelines": str((row.visual_identity or {}).get("guidelines") or "")}
    assert stored[corrected] == "corrigido"
    for field in survivors:
        assert stored[field], f"{field} was wiped by a correction to {corrected}"


async def test_the_registration_answer_reports_what_is_ON_FILE_not_what_was_sent():
    """It used to echo the two brand ARGUMENTS. Once a correction stops blanking the fields it
    was not given, echoing the arguments says ``visual_identity: ''`` about a company that has
    one — and the model reads that back to the contact."""
    svc = _svc()
    row = svc.register("Padaria Sol", guidelines="tom formal", identity_id="u1")
    payload = svc.registration_payload(row)
    assert payload["visual_identity"] == "azul e branco"
    assert payload["guidelines"] == "tom formal"
    assert payload["segment"] == "padaria"


# ── (b) the description is the promise: three fields, three meanings ────────────────────
def _blocks(description: str) -> "dict[str, str]":
    """The description split into its per-argument paragraphs, keyed by argument name.

    Read off the rendered description rather than the source: the description is what the model
    receives, and a gloss that exists only in a comment promises nothing.
    """
    out: "dict[str, str]" = {}
    current = ""
    for line in description.splitlines():
        if not line.strip():
            current = ""            # a blank line ends the argument list; the prose after it
            continue                # belongs to the tool, not to the last field named
        head = re.match(r"^\s{0,8}(\w+): ", line)
        if head and head.group(1) in {"company_name", "company_id", "name", "cnpj", "segment",
                                      "visual_identity", "guidelines"}:
            current = head.group(1)
            out[current] = ""
        if current:
            out[current] += line + "\n"
    return out


@pytest.mark.parametrize("tool", ["company_registration", "company_update"])
async def test_the_description_says_what_each_of_the_three_fields_IS(tool):
    tools = {t.name: t for t in await build_server(_svc()).list_tools()}
    blocks = _blocks(tools[tool].description or "")
    for field in ("segment", "visual_identity", "guidelines"):
        assert field in blocks, f"{tool} does not describe `{field}`"
    # The words a contact actually uses, attached to the field they mean — and NOT to its
    # neighbour, which is the whole distinction the measured turn got wrong.
    assert "segmento" in blocks["segment"] and "segmento" not in blocks["guidelines"]
    assert "diretrizes" in blocks["guidelines"] and "diretrizes" not in blocks["segment"]
    assert "tom de voz" in blocks["guidelines"]


async def test_the_update_description_tells_the_model_to_NAME_the_field_before_calling():
    """The hold that asks the contact for permission stops the call BEFORE anything is read, so
    the only question it can ask is «posso atualizar o cadastro?» — which names no field. The
    coordinator's calendar preview reached the same wall (#103) and answered it with a read-only
    preview tool; this vertical cannot, its surface is fixed by the host's per-tool RBAC table.
    What is left is the description, and this pins that it says it."""
    tools = {t.name: t for t in await build_server(_svc()).list_tools()}
    # One line: the description is wrapped source, and a phrase that straddles a newline is
    # still one phrase to the model reading it.
    text = " ".join((tools["company_update"].description or "").split())
    assert "BEFORE calling this" in text
    assert "tell the user WHICH field you are about to change" in text
    assert "its current value and the new one" in text
    assert "cannot name the field" in text
