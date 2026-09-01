"""Uma remoção CONSULTA o livro — e a listagem que a descreve não é fabricação.

O `#86` condicionou o particípio atributivo a *"nada foi lido"*, usando o `_summary_read`. Esse
predicado responde a outra pergunta: **"o turno tem FIGURAS fundamentadas?"** — e por isso conta
o `math`, que calcula sem ler nada, e não conta o `remove_by_search`, que procura no livro para
remover.

**Resultado medido no traço vivo: o `#86` cobria 1 dos 2 casos reais.** O que escapava é uma
listagem verdadeira num turno cuja única chamada foi uma remoção bem-sucedida.

**A saída NÃO é alargar o `_summary_read`**, e a razão é o seu outro consumidor: o
`conjured_totals`. Uma resposta que cita TOTAIS depois de uma remoção continua sem fundamento,
porque **uma remoção não devolve totais** — alargar o predicado partilhado enfraqueceria essa
regra de uma vez. Dois predicados, dois consumidores:

    _summary_read      get_summary · search · math              "há figuras em mão?"
    _consulted_ledger  get_summary · search · remove_by_search  "o turno olhou para o livro?"

**Os dois conjuntos não se contêm** — `math` está só no primeiro, `remove_by_search` só no
segundo — **e é essa a prova de que são perguntas diferentes**, não uma versão larga da outra.
"""

from __future__ import annotations

import pytest

from cogno_praxis.bookkeeper.grounding import ground_reply
from cogno_praxis.grounding import ToolCall

LISTAGEM = "Os lançamentos de R$ 45,00 registrados hoje."
TOTAIS = "Seu total de entradas é R$ 500,00, saldo líquido R$ 500,00."

REMOCAO = [ToolCall(tool="remove_by_search", ok=True, result="Removed: R$ 45,00")]
SUMARIO = [ToolCall(tool="get_summary", ok=True, result="Expense: R$ 45.00")]
BUSCA = [ToolCall(tool="search", ok=True, result="Expense: R$ 45.00")]
CONTA = [ToolCall(tool="math", ok=True, result="45")]


def _rule(reply, tools=()):
    v = ground_reply(reply, tools=list(tools), had_executor=True, locale="pt")
    return v.rule if v else None


@pytest.mark.parametrize("tools,nome", [(REMOCAO, "remoção"), (SUMARIO, "sumário"), (BUSCA, "busca")])
def test_a_listing_after_a_ledger_lookup_is_kept(tools, nome):
    """SABOTAGEM: trocar `_consulted_ledger` de volta por `_summary_read` -> morre o caso da
    remoção, e SÓ ele. É o caso vivo que o `#86` não cobria.
    """
    assert _rule(LISTAGEM, tools) is None, nome


def test_math_alone_does_NOT_exempt_the_listing():
    """O CONTROLO que separa as duas perguntas. `math` está no `_summary_read` e **não** aqui:
    calcular não é consultar o livro, e uma listagem que ninguém leu continua infundada.

    Sem este caso, `_consulted_ledger` podia ser escrito como *"qualquer chamada ok"* e passava
    os testes acima — que é a versão larga que este ficheiro existe para recusar.
    """
    assert _rule(LISTAGEM, CONTA) == "fabricated_entry"
    assert _rule(LISTAGEM) == "fabricated_entry"


def test_a_removal_does_NOT_exempt_conjured_totals():
    """O OUTRO consumidor, e a razão de não alargar o predicado partilhado.

    SABOTAGEM: acrescentar `remove_by_search` ao `_summary_read` (em vez de criar o segundo
    predicado) -> este teste morre, e o `conjured_totals` passa a aceitar totais que ninguém
    leu. **Uma remoção não devolve totais.**
    """
    assert _rule(TOTAIS, REMOCAO) == "conjured_totals"
    assert _rule(TOTAIS, SUMARIO) is None          # o par: uma leitura real isenta


def test_the_two_predicates_do_not_contain_each_other():
    """A asserção que nomeia o desenho: nenhum é a versão larga do outro.

    Se um dia passarem a conter-se, um deles é redundante e alguém deve dizê-lo — em vez de
    manter dois nomes para a mesma pergunta.
    """
    from cogno_praxis.bookkeeper.grounding import _LEDGER_READS
    assert "math" not in _LEDGER_READS, "calcular não é consultar o livro"
    assert "remove_by_search" in _LEDGER_READS
    assert _rule(LISTAGEM, CONTA) is not None and _rule(LISTAGEM, REMOCAO) is None


def test_an_explicit_claim_still_fires_after_a_removal():
    """A alegação explícita continua sem condição: consultar o livro não dá alvará para dizer
    *"registrei"*. Sem isto, o conserto teria aberto a porta que a regra existe para fechar."""
    assert _rule("Registrei a entrada de R$ 45,00.", REMOCAO) == "fabricated_entry"
