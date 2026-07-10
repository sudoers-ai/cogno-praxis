"""Bookkeeper grounding rules — money is the worst place to fabricate.

Modelled on the scheduler's live failure class: the voice claiming a write that never
happened, or quoting figures no read produced. Includes the behavioural marker contract:
the rules grep the REAL server's output strings (same repo — drift caught here).
"""

from __future__ import annotations

from cogno_praxis.grounding import ToolCall
from cogno_praxis.bookkeeper.grounding import (
    CHECK_TOTALS_MSG,
    NO_ENTRY_MSG,
    NO_REMOVAL_MSG,
    ground_reply,
)


def _income(ok: bool = True) -> ToolCall:
    res = "Income recorded: Consulta = R$ 500,00 on 2026-07-10." if ok else ""
    return ToolCall(tool="add_income", ok=ok, side_effect=True, result=res)


def _summary() -> ToolCall:
    return ToolCall(tool="get_summary", ok=True,
                    result="Income:  R$ 500,00 (1 entries)\nExpense: R$ 0,00 (0 entries)\n"
                           "Net:     R$ 500,00")


def _removed(ok: bool = True) -> ToolCall:
    res = "Removed: 2026-07-10 [income] Consulta = R$ 500,00." if ok else \
        "No transaction of yours matches 'consulta' — nothing removed."
    return ToolCall(tool="remove_by_search", ok=True, side_effect=True, result=res)


# ── (1) fabricated entry ─────────────────────────────────────────────────────────────
def test_claims_recorded_without_write_is_rewritten():
    fixed = ground_reply("Prontinho! Registrei a consulta de R$ 500,00 pra você. ✅")
    assert fixed is not None and fixed.message == NO_ENTRY_MSG
    assert fixed.rule == "fabricated_entry" and fixed.repairable and fixed.critique


def test_claims_recorded_with_failed_write_is_rewritten():
    fixed = ground_reply("Lançado: R$ 500,00 de consulta!", tools=[_income(ok=False)])
    assert fixed is not None and fixed.rule == "fabricated_entry"


def test_real_recorded_entry_is_never_touched():
    reply = "Registrei a consulta de R$ 500,00 pra você. ✅"
    assert ground_reply(reply, tools=[_income(ok=True)]) is None


def test_recorded_claim_without_money_anchor_is_kept():
    # book-keeping small talk with no figure — nothing concrete fabricated.
    assert ground_reply("Tudo anotado por aqui! Qualquer coisa me chama.") is None


def test_negated_recorded_claim_is_kept():
    assert ground_reply("Ainda não registrei o valor de R$ 500,00 — me confirma?") is None


# ── (2) fabricated removal ───────────────────────────────────────────────────────────
def test_claims_removed_without_removal_is_rewritten():
    fixed = ground_reply("Removi o lançamento da consulta pra você!")
    assert fixed is not None and fixed.message == NO_REMOVAL_MSG
    assert fixed.rule == "fabricated_removal" and fixed.repairable


def test_removed_claim_with_nothing_removed_result_is_rewritten():
    # remove_by_search ran but matched nothing ("nothing removed") — the claim is false.
    fixed = ground_reply("Excluí o lançamento!", tools=[_removed(ok=False)])
    assert fixed is not None and fixed.rule == "fabricated_removal"


def test_real_removal_is_never_touched():
    assert ground_reply("Removi o lançamento da consulta (R$ 500,00).",
                        tools=[_removed(ok=True)]) is None


# ── (3) conjured totals ──────────────────────────────────────────────────────────────
def test_totals_without_summary_read_is_rewritten():
    fixed = ground_reply("Seu saldo do mês é R$ 12.340,00 (entradas R$ 15.000,00).")
    assert fixed is not None and fixed.message == CHECK_TOTALS_MSG
    assert fixed.rule == "conjured_totals" and fixed.repairable and fixed.critique


def test_totals_backed_by_summary_read_is_kept():
    reply = "Seu total de entradas é R$ 500,00, saldo líquido R$ 500,00."
    assert ground_reply(reply, tools=[_summary()]) is None


def test_recorded_entry_echoing_amount_is_not_conjured_totals():
    # "registrei R$ 500" legitimately echoes the amount without a summary read; and the
    # recorded-entry write itself must satisfy a totals-ish phrasing about that entry.
    reply = "Registrei! Sua entrada de R$ 500,00 já está no total do mês."
    assert ground_reply(reply, tools=[_income(ok=True)]) is None


def test_plain_money_mention_without_totals_noun_is_kept():
    assert ground_reply("A consulta custa R$ 300,00, quer que eu registre?") is None


# ── behavioural marker contract: the REAL server emits what the rules grep ───────────
def test_server_result_markers_match_the_rules():
    import asyncio

    from cogno_praxis.bookkeeper.grounding import (
        EXPENSE_RECORDED_PREFIX, INCOME_RECORDED_PREFIX, REMOVED_PREFIX, SUMMARY_HEAD_RE)
    from cogno_praxis.bookkeeper.server import build_server

    mcp = build_server()

    def _text(res):
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")

    async def run():
        inc = _text(await mcp.call_tool("add_income", {"description": "Consulta",
                                                       "amount": "500", "identity_id": "u1"}))
        assert inc.startswith(INCOME_RECORDED_PREFIX)
        out = _text(await mcp.call_tool("add_outcome", {"description": "Luz",
                                                        "amount": "100", "identity_id": "u1"}))
        assert out.startswith(EXPENSE_RECORDED_PREFIX)
        summ = _text(await mcp.call_tool("get_summary", {"identity_id": "u1",
                                                         "role": "ADMIN"}))
        assert SUMMARY_HEAD_RE.match(summ)
        rem = _text(await mcp.call_tool("remove_by_search", {"query": "Luz",
                                                             "identity_id": "u1"}))
        assert rem.startswith(REMOVED_PREFIX)
    asyncio.run(run())
