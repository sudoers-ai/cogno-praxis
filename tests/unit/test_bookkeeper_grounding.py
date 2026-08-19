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


# ── recall de outro turno NÃO é afirmação deste ──────────────────────────────────────
# O defeito, medido 3/3 no caminho de PRODUÇÃO (ChatService + reparo): a resposta relembrava
# corretamente a escrita do turno anterior, `fabricated_entry` disparava, o veredito voltava
# `repairable`, e o reparo re-executava com a tool FORÇADA. Mesmo R$ 150 gravado duas vezes,
# `tx_id` diferentes, sem dedup, sob uma resposta que lê como correta.
#
# O guard de side-effect do turno não enxergava: a escrita estava no turno ANTERIOR. A
# docstring do reparo diz "double-commit impossible by construction" e está certa — DENTRO de
# um turno. A duplicata é entre turnos.

_WROTE = [ToolCall(tool="add_income", ok=True, side_effect=True,
                   result="Income recorded: Consulta (Maria) = R$ 150.00 on 2026-08-18.")]


def _verdict(reply, tools=(), locale="pt"):
    return ground_reply(reply, tools=list(tools), locale=locale)


def test_a_truthful_recall_of_an_earlier_write_is_not_rewritten():
    """O caso medido. Sem isto, dizer a verdade custa uma segunda escrita."""
    assert _verdict("Sim, o lançamento de R$ 150,00 da Maria já foi registrado ontem.") is None
    # sem o `já`, para provar que quem carrega a exclusão é a marca TEMPORAL — a versão
    # anterior deste teste só tinha a frase acima e passava pelo motivo errado.
    assert _verdict("O lançamento de R$ 150,00 foi registrado ontem.") is None
    assert _verdict("Yes, the R$ 150.00 entry was already recorded yesterday.",
                    locale="en") is None
    assert _verdict("Sí, el asiento de R$ 150,00 ya fue registrado ayer.", locale="es") is None
    # remoção tem a mesma forma e o mesmo risco (remover de novo remove OUTRA coisa)
    assert _verdict("Aquele lançamento de R$ 150,00 já foi removido na semana passada.") is None


def test_the_exclusion_needs_BOTH_marks_or_it_would_swallow_real_fabrication():
    """A precisão inteira está em exigir estativo E passado na mesma cláusula.

    Cada uma sozinha derrubaria a regra para casos que TÊM que reprovar:
    - estativo sozinho: "foi registrado com sucesso" é como se confirma AGORA em pt-BR;
    - passado sozinho: "já registrei" é primeira pessoa sobre ESTE turno.
    """
    for reply in ("Pronto! Registrei a entrada de R$ 150,00 da Maria.",     # performativo
                  "Registrado! R$ 150,00 da Maria.",                        # particípio nu
                  "A entrada de R$ 150,00 foi registrada com sucesso.",     # estativo, sem passado
                  "Já registrei a entrada de R$ 150,00."):                  # passado, sem estativo
        v = _verdict(reply)
        assert v is not None and v.rule == "fabricated_entry", reply
    assert _verdict("The R$ 150.00 entry was recorded successfully.",
                    locale="en") is not None
    assert _verdict("Ya registré el asiento de R$ 150,00.", locale="es") is not None


def test_a_mixed_reply_still_fires_because_the_check_is_per_CLAUSE():
    """Relembrar uma escrita não dá alvará para inventar outra na mesma frase."""
    v = _verdict("O de ontem já foi registrado, e registrei o novo de R$ 150,00 agora.")
    assert v is not None and v.rule == "fabricated_entry"


def test_a_real_write_this_turn_still_passes():
    """Controle: o caminho feliz não pode ter sido afetado."""
    assert _verdict("Registrei a entrada de R$ 150,00 da Maria.", tools=_WROTE) is None


def test_JA_is_not_a_past_marker_it_is_how_pt_BR_confirms_the_present():
    """A regressão que a exclusão de recall introduziu, e o motivo dela.

    `já foi registrado` / `já está lançado` é a forma CANÔNICA de confirmar em pt-BR o que se
    acabou de fazer — não uma referência ao passado. Enquanto `já` esteve na lista de marcas
    temporais, uma alucinação pura de PRIMEIRO turno passava batido, com zero tools. Isso é
    pior que a duplicata que a exclusão foi escrita para evitar: ali o dado ficava errado no
    banco; aqui uma confirmação financeira inventada chega ao usuário sem nada barrar.

    O teste original usava "já foi registrado ONTEM" e passava pelo motivo errado — `ontem`
    sozinho já bastava, e o `já` nunca foi isolado. Estes cinco isolam.

    Mutação: devolver `j[áa]`/`already`/`ya` às marcas temporais e cada um destes morre.
    """
    for reply in ("Pronto! Já foi registrado o valor de R$ 150,00.",
                  "Certo, já está lançado o valor de R$ 150,00."):
        v = _verdict(reply)
        assert v is not None and v.rule == "fabricated_entry", reply
    v = _verdict("Já foi removido o lançamento de R$ 150,00.")
    assert v is not None and v.rule == "fabricated_removal"
    assert _verdict("The amount of R$ 150.00 was already recorded.", locale="en") is not None
    assert _verdict("Ya fue registrado el monto de R$ 150,00.", locale="es") is not None
