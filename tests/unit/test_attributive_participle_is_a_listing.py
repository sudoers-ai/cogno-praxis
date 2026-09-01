"""O particípio ATRIBUTIVO é uma descrição, não um acto — e a rede negava a verdade.

Medido ao vivo em 2026-09-01, com um supervisor do outro lado:

    pedido:   "Liste todos os lançamentos financeiros registrados hoje."
    tool:     get_summary ok=True  ->  "Expense: R$ 45.00 — office supplies"
    modelo:   "temos os seguintes lançamentos registrados: Despesas R$ 45,00…"   VERDADE
    a rede:   "Na verdade, esse lançamento ainda não foi registrado no sistema."  MENTIRA

**O modelo disse a verdade e o guarda pôs a mentira.**

**A causa não é o classificador.** O `is_read_query` é aceite por simetria e **nunca lido**
neste backstop — medido: o veredicto é idêntico com `True` e com `False`; as três decisões que
dependem dele estão todas no scheduler.

**A causa é gramatical.** O padrão apanhava o particípio NU (`registrad[oa]s?`), e a isenção de
lembrança (`recalled`) exige a construção ESTATIVA — a cópula que uma frase atributiva não tem.
Por isso `ontem` e `na semana passada` eram reescritos na mesma: **o marcador temporal nunca
chegava a ser consultado, porque o estativo já tinha falhado.**

**Custo, sobre 7 listagens VERDADEIRAS com uma leitura em mão: 3 eram negadas** — e o
discriminador era a gramática, não o conteúdo. *A mesma verdade passava ou era negada conforme
a forma que o modelo escolheu*, o que torna o defeito irreproduzível para quem só olhe ao texto.

**A saída é a mesma que `cogno-host#612` já usa na regra genérica**, e isso importa: as duas
regras resolviam a MESMA ambiguidade em sentidos opostos, e a da praxis corre primeiro.
"""

from __future__ import annotations

import pytest

from cogno_praxis.bookkeeper.grounding import ground_reply
from cogno_praxis.grounding import ToolCall

LEITURA = [ToolCall(tool="get_summary", ok=True, result="Expense: R$ 45.00 — office supplies")]
ESCRITA = [ToolCall(tool="add_outcome", ok=True, side_effect=True,
                    result="Expense recorded: R$ 45.00 — material")]


def _rule(reply, tools=()):
    v = ground_reply(reply, tools=list(tools), had_executor=True, locale="pt")
    return v.rule if v else None


@pytest.mark.parametrize("reply", [
    "Temos os seguintes lançamentos registrados hoje: Despesas R$ 45,00.",
    "Hoje há 1 lançamento registrado: Despesa de R$ 45,00 — material de escritório.",
    "Consta uma despesa de R$ 45,00 (material de escritório) lançada hoje.",
])
def test_a_truthful_listing_backed_by_a_read_is_KEPT(reply):
    """SABOTAGEM: tirar `and not _summary_read(tools)` da regra (1) -> os três morrem.

    É o caso vivo. A leitura correu, os números são os do sistema, e a resposta descreve-os.
    """
    assert _rule(reply, LEITURA) is None


@pytest.mark.parametrize("reply", [
    "Registrado! R$ 150,00 da Maria.",
    "Lançado: R$ 500,00 de consulta!",
])
def test_the_SAME_grammar_with_nothing_read_is_still_caught(reply):
    """O PAR do teste acima, e é ele que separa este conserto de "deixa passar tudo".

    A frase é a mesma forma — particípio nu, sem cópula. O que muda é o turno não ter
    consultado nada: aí não há listagem a descrever, e um recibo sem escrita é fabricação.
    """
    assert _rule(reply) == "fabricated_entry"


@pytest.mark.parametrize("reply", [
    "Pronto! Registrei a entrada de R$ 150,00 da Maria.",
    "A entrada de R$ 150,00 foi registrada com sucesso.",
    "Já registrei a entrada de R$ 150,00.",
    "Pronto! Já foi registrado o valor de R$ 150,00.",
    "Certo, já está lançado o valor de R$ 150,00.",
])
def test_an_EXPLICIT_claim_fires_even_with_a_read_in_hand(reply):
    """A alegação explícita — primeira pessoa ou cópula + particípio — **não** é condicionada.

    Uma leitura bem-sucedida não dá alvará para dizer *"registrei"*. Sem esta distinção, o
    conserto teria aberto a porta que a regra existe para fechar: consultar o resumo e depois
    inventar uma escrita.
    """
    assert _rule(reply, LEITURA) == "fabricated_entry"


def test_the_temporal_marker_was_never_the_discriminator():
    """A hipótese que a medição REFUTOU, guardada porque explica a causa.

    A primeira leitura foi *"'hoje' não é marcador de passado, por isso a lembrança não é
    reconhecida"*. Falso: `ontem` e `na semana passada` eram reescritos na mesma — o estativo
    falha primeiro e o marcador nunca é consultado. Estas frases têm marcador de passado E
    continuam a ser apanhadas quando nada foi lido.
    """
    for quando in ("ontem", "na semana passada"):
        assert _rule(f"Lançamentos registrados {quando}: Despesas R$ 45,00.") == "fabricated_entry"
        assert _rule(f"Lançamentos registrados {quando}: Despesas R$ 45,00.", LEITURA) is None


def test_a_real_write_still_exempts_everything():
    """Controlo do caminho feliz, intocado: quem escreveu pode dizer que escreveu."""
    assert _rule("Registrei a entrada de R$ 45,00.", ESCRITA) is None
    assert _rule("Lançamento registrado: R$ 45,00.", ESCRITA) is None


def test_is_read_query_still_does_not_participate():
    """A causa que foi DESCARTADA, fixada para não voltar como diagnóstico.

    O backstop aceita `is_read_query` por simetria de assinatura e não o lê. Se um dia passar
    a lê-lo, este teste morre e obriga a rever esta explicação inteira — em vez de deixar a
    docstring a afirmar algo que deixou de ser verdade.
    """
    D = "Temos os seguintes lançamentos registrados hoje: Despesas R$ 45,00."
    a = ground_reply(D, tools=[], had_executor=True, locale="pt", is_read_query=False)
    b = ground_reply(D, tools=[], had_executor=True, locale="pt", is_read_query=True)
    assert (a.rule if a else None) == (b.rule if b else None) == "fabricated_entry"


def test_the_copula_exclusion_is_anchored_at_a_WORD_boundary():
    """SABOTAGEM: tirar o `\\b` de `_COPULA_LOOKBEHIND` -> este teste morre, e SÓ ele.

    Sem `\\b`, cada exclusão casa a CAUDA de qualquer palavra terminada nesse sufixo. `café`
    termina em `é`, portanto `(?<!é )` passaria a engolir *"Café lançado"* — e uma despesa de
    café inventada, com zero chamadas, **escaparia à regra**.

    É o mesmo defeito que `cogno-host#612` cometeu e corrigiu, e escrevo o caso aqui porque a
    primeira versão deste ficheiro NÃO o discriminava: a sabotagem do `\\b` passava os 31
    testes. Uma exclusão que casa de mais desarma a guarda e parece apenas silêncio.
    """
    assert _rule("Café lançado: R$ 45,00.") == "fabricated_entry"
    assert _rule("Compreensao registrada: despesa de R$ 45,00.") == "fabricated_entry"
    # E o par: com leitura em mão continuam a ser listagem, como qualquer atributivo.
    assert _rule("Café lançado: R$ 45,00.", LEITURA) is None
