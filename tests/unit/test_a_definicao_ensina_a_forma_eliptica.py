"""A definição da remuneração própria ensina a forma ELÍPTICA, não só a ancorada.

## O que estava escrito, e o que faltava

O parágrafo do ``scope.txt`` que autoriza um professor a perguntar pela PRÓPRIA remuneração
dava três exemplos — «quanto eu recebo», «qto eu receberia por mês», «baseado nesse cálculo
quanto tenho a receber». **Os três com pronome.** A definição ensinava a forma ANCORADA e nunca
a elíptica, e é por isso que «me traga os totais até o final do ano» era bloqueada com a
autorização escrita a três linhas de distância: o classificador lê a definição, e uma definição
que só exemplifica o pedido com sujeito não cobre o pedido sem ele.

Esta mudança acrescenta três exemplos à MESMA lista — «me traga os totais até o final do ano»,
«traga os valores», «quanto dá» — e **nada mais**. Sem frase justificativa nova: a lista já é
justificada pelo parágrafo onde vive, e uma justificação seria uma afirmação nossa sobre o mundo
metida dentro de um prompt.

## A medição (do consultor, citada e não repetida aqui)

Duas corridas de n=5 intercaladas (união n=10), ``served_model`` 90/90
``gpt-4o-mini-2024-07-18``, em BLOQUEIOS, A = a definição de hoje e B = a emendada::

    me traga os totais até o final do ano   DENTRO   5/10 → 0/10
    traga os valores até o final do ano     DENTRO   9/10 → 0/10
    Quanto recebo pelas aulas de setembro?  DENTRO   0/10 → 0/10
    calculo o valor mensal que vou receber… DENTRO   0/10 → 0/10
    não recebi o link da reunião            FORA     0/10 → 0/10
    ganhei o processo                       FORA    10/10 → 10/10
    qual o valor do dólar hoje?             FORA    10/10 → 10/10
    qual a previsão do tempo?               FORA    10/10 → 10/10
    me traga os totais de alunos por turma  ALCANCE  0/10 → 0/10

Fecha tudo o que fechava, sem perder nenhuma das de dentro; e **não generalizou** — a frase de
alcance já era ALLOW nos dois braços, não é a emenda que a abre.

O limite, tal como o consultor o escreveu: houve **três** ``system_fingerprint`` distintos na
corrida (``fp_894e7baa82`` ×80, ``fp_f240edfbb6`` ×6, ``fp_0c03eba41c`` ×4) — o backend mudou
duas vezes em seis minutos com o mesmo ``served_model`` — e o fingerprint **não foi registado
por braço**, logo não se pode excluir assimetria. O que sustenta o resultado é a reprodução em
duas corridas separadas com misturas diferentes, não a homogeneidade do backend.

## Porque é que uma asserção sobre o ficheiro inteiro não servia

O ``scope.txt`` tem sete parágrafos e **três** deles falam de dinheiro: o da remuneração
PRÓPRIA, o da coordenação a perguntar pela FACULDADE e o do BLOCK, que é onde vive a lista do
que continua fechado. Um exemplo elíptico que caísse num destes dois últimos ensinaria
exactamente a coisa errada — e uma procura pelo ficheiro inteiro dava verde na mesma, porque a
palavra lá estaria. Daí o fatiamento: tudo o que este ficheiro exige, exige-o DENTRO do
parágrafo onde a lista vive, e ``test_o_fatiamento_nao_e_o_ficheiro_inteiro`` é a prova contada
de que a distinção é carga e não enfeite.

Tudo aqui é uma asserção sobre o PROMPT, e este ficheiro não finge o contrário: pina que os
exemplos existem, ONDE existem, e que a prosa à volta deles não cresceu. Se o modelo obedece foi
medido em cima, contra o modelo servido, e não é o que um teste unitário mede. O que compra é
que uma edição futura não os apaga em silêncio.
"""

from __future__ import annotations

import re
from pathlib import Path

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "coordinator" / "prompts"
SCOPE = (PROMPTS / "scope.txt").read_text(encoding="utf-8")

#: A âncora por onde se fatia. Não é o parágrafo do BLOCK nem o da coordenação a perguntar pela
#: faculdade: é o da remuneração PRÓPRIA, e é a maiúscula que o diz. Contada a =1 mais abaixo.
ANCORA = "THEIR OWN remuneration"

#: Os três que já lá estavam. Todos com pronome — a forma ANCORADA.
ANCORADOS = (
    "quanto eu recebo",
    "qto eu receberia por mês",
    "baseado nesse cálculo quanto tenho a receber",
)

#: Os três que esta mudança acrescenta. Nenhum tem sujeito — é essa a forma que faltava.
ELIPTICOS = (
    "me traga os totais até o final do ano",
    "traga os valores",
    "quanto dá",
)

#: A PROSA do parágrafo: tudo o que não é exemplo citado, com a corrida de exemplos colapsada
#: num só marcador. Escrita à letra e comparada INTEIRA — uma frase justificativa nova muda-a,
#: um sétimo exemplo não. É esta a asserção que diz «mais nada mudou».
PROSA = (
    "Allow a professor asking about THEIR OWN remuneration for teaching here: what they earn or "
    "will earn, the hourly rate, the IBOPE bonus rules, the invoice/payment dates, <ex>. Their "
    "own pay for their own classes is part of their working relationship with this institution "
    "and is a coordination question, not an outside one."
)


# ── ler o prompt ───────────────────────────────────────────────────────────────────────
def _achatado(texto: str) -> str:
    """As quebras de linha viram espaço.

    Uma quebra de linha no ``scope.txt`` é TIPOGRAFIA — a coluna foi escolhida para o diff
    caber num ecrã — e o modelo lê a frase, não a coluna. Sem isto a procura por
    ``"me traga os totais até o final do ano"`` falha só porque o exemplo embrulha ao fim da
    linha, que é exactamente onde ele embrulha.
    """
    return " ".join(texto.split())


def _paragrafo_da_remuneracao() -> str:
    """O parágrafo onde a lista vive — e a prova, contada, de que só há um.

    A unidade de secção do ``scope.txt`` é o PARÁGRAFO: o ficheiro não tem cabeçalhos, tem
    linhas em branco. Se um dia a âncora aparecer em dois sítios, este teste morre em vez de
    escolher um deles em silêncio.
    """
    assert _achatado(SCOPE).count(ANCORA) == 1, (
        f"a âncora {ANCORA!r} tem de aparecer exactamente uma vez no scope.txt — com duas, "
        "este ficheiro estaria a fatiar por adivinhação"
    )
    hits = [_achatado(p) for p in SCOPE.split("\n\n") if ANCORA in p]
    assert len(hits) == 1
    return hits[0]


# ── as asserções ───────────────────────────────────────────────────────────────────────
def test_os_seis_exemplos_vivem_na_lista_da_remuneracao_propria() -> None:
    """Os três antigos e os três novos, na MESMA lista e no MESMO parágrafo.

    Os antigos viajam com os novos de propósito: sem eles a asserção não distingue «a lista
    ganhou a forma elíptica» de «a lista foi substituída pela forma elíptica».
    """
    paragrafo = _paragrafo_da_remuneracao()
    for exemplo in ANCORADOS + ELIPTICOS:
        assert f'"{exemplo}"' in paragrafo, exemplo


def test_a_seccao_nao_ganhou_frase_justificativa_nova() -> None:
    """A prosa à volta da lista é a que já era — byte a byte, com os exemplos colapsados.

    Uma justificação dentro de um prompt é uma afirmação nossa sobre o mundo que o modelo passa
    a tratar como facto. A mudança era acrescentar exemplos; esta é a asserção de que foi só
    isso.
    """
    paragrafo = _paragrafo_da_remuneracao()
    esqueleto = re.sub(r'"[^"]*"', "<ex>", paragrafo)
    esqueleto = re.sub(r"<ex>(, <ex>)*", "<ex>", esqueleto)
    assert esqueleto == PROSA


def test_o_fatiamento_nao_e_o_ficheiro_inteiro() -> None:
    """O CONTROLO: o parágrafo é uma parte própria do ficheiro, e os outros existem.

    Sem isto, ``_paragrafo_da_remuneracao`` podia devolver o ficheiro todo — ou o ficheiro
    podia encolher até ao parágrafo — e as duas asserções acima passavam a ser sobre o
    ficheiro inteiro sem ninguém dar por isso. É a armadilha da vizinhança, contada.
    """
    paragrafo = _paragrafo_da_remuneracao()
    inteiro = _achatado(SCOPE)
    assert paragrafo in inteiro and len(paragrafo) < len(inteiro)
    assert len([p for p in SCOPE.split("\n\n") if p.strip()]) > 1
