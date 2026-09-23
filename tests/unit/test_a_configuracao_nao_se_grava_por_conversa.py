"""A configuração não se grava por conversa — a resposta nomeia a CHAVE e diz onde se escreve.

## O turno medido

22/09, 15:39. O contacto escreve à coordenadora **"O valor é 120 reais por hora, bônus de
30,00…"**. Não está a perguntar nada: está a DECLARAR configuração por conversa. Nesse dia a
guarda de escopo bloqueou-o e devolveu um enlatado, portanto o turno nunca chegou ao executor e
a falha ficou invisível.

O que a abriu foi uma mudança noutro repositório: o host passou a deixar passar a EQUIPA que
fala da própria remuneração quando a ferramenta está na mesa. Replicadas as frases reais contra
esse predicado, **o turno deixa de ser bloqueado e passa a CHEGAR ao EGO** — e o EGO não tem
ferramenta nenhuma que escreva configuração. O risco que se abre é o pior da lista e não é uma
recusa: é um *"anotado, vou considerar"* que não gravou coisa nenhuma. Quem escreve não pode
escrever coisas que não sabe, e uma promessa que nenhuma chamada suporta é a única que o
contacto não tem como verificar — ele não volta a dizer o valor, e lê a estimativa seguinte
(correta, feita a partir do que a instituição declarou) como se fosse a errada.

As quatro chaves são as que o ``CoordinatorConfig`` lê de facto — ``PAY_RATE_PER_HOUR``,
``HOURS_PER_CLASS``, ``IBOPE_BONUS``, ``IBOPE_MIN_RESPONSE_PCT`` (``coordinator/config.py``) — e
é por isso que a regra as nomeia à letra: a pessoa que está do outro lado pode ser exactamente
quem administra a persona, e a chave é a linha que ela tem de acrescentar no painel.

## Porque é que uma asserção de presença não chegava aqui

``PAY_RATE_PER_HOUR`` **já estava** no ``system.txt`` antes desta mudança — no ramo
"NOT CONFIGURED", onde a ferramenta se queixa de a chave faltar. Um teste que procurasse a chave
no ficheiro inteiro passava sobre a MAIN, e a mutação que apaga a regra nova não o matava.
Daí o fatiamento por secção: tudo o que este ficheiro exige, exige-o DENTRO da secção nova, e
``test_uma_assercao_sobre_o_ficheiro_inteiro_teria_passado_antes`` é a prova contada de que a
distinção é carga e não enfeite.

Tudo aqui é uma asserção sobre o PROMPT, e este ficheiro não finge o contrário: pina que a
instrução existe, onde existe, e que nada no mesmo ficheiro diz o oposto. Se o modelo obedece é
medição viva, não teste unitário. O que compra é que uma edição futura não a apaga em silêncio
— que é exactamente como ela nunca chegou a ser escrita.

**A frase do turno está aqui sem nome de pessoa, de instituição ou de identificador** (não havia
nenhum nela); os números ficam porque são eles o teste, como em ``test_pay_declared_in_prose``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "coordinator" / "prompts"
SYSTEM = (PROMPTS / "system.txt").read_text(encoding="utf-8")
LIMITS = (PROMPTS / "limits.txt").read_text(encoding="utf-8")

#: O cabeçalho da regra, tal como está escrito. É por ele que se fatia — ver o docstring.
CABECALHO = "### The Figures Are Configuration — a Conversation Cannot Set Them"

#: As quatro chaves que o ``CoordinatorConfig`` lê. Escritas à letra, porque é à letra que
#: alguém as vai copiar para o painel.
CHAVES = ("PAY_RATE_PER_HOUR", "HOURS_PER_CLASS", "IBOPE_BONUS", "IBOPE_MIN_RESPONSE_PCT")

#: O turno t102, na letra em que foi escrito e cortado onde a citação corta.
T102 = "O valor é 120 reais por hora, bônus de 30,00"

#: As chaves que ESSA frase toca, uma por quantidade declarada — o valor à hora e o bónus.
#: Escritas à mão e não extraídas por regex da frase: uma extracção seria um segundo parser, e
#: um segundo parser erra por caminho próprio sem ninguém dar por isso.
T102_CHAVES = ("PAY_RATE_PER_HOUR", "IBOPE_BONUS")

#: O turno t99, o CONTROLO: um PEDIDO de valor, não uma declaração. A regra nova não o pode
#: transformar numa recusa — continua a mandar ESTIMAR, com a ferramenta.
T99 = "calculo o valor mensal que vou receber este mês"

#: As cinco frases que a resposta nunca pode produzir. "Registado" não entra na lista por
#: acidente de grafia: o prompt fala português do Brasil ao contacto, e é "registrado" que o
#: modelo escreveria.
MUZZLE = ("anotado", "guardado", "registrado", "vou considerar", "passará a valer")


# ── ler o prompt ───────────────────────────────────────────────────────────────────────
def _seccao(texto: str, cabecalho: str) -> str:
    """O corpo da secção `cabecalho`, até ao cabeçalho seguinte. "" se a secção não existe."""
    inicio = texto.find(cabecalho)
    if inicio < 0:
        return ""
    resto = texto[inicio + len(cabecalho):]
    fim = len(resto)
    for marca in ("\n## ", "\n### "):
        pos = resto.find(marca)
        if 0 <= pos < fim:
            fim = pos
    return resto[:fim]


def _paragrafo(texto: str, indice: int) -> str:
    """O bloco entre linhas em branco que contém `indice` — a unidade em que uma proibição e a
    palavra proibida têm de viajar juntas."""
    inicio = texto.rfind("\n\n", 0, indice)
    fim = texto.find("\n\n", indice)
    return texto[(0 if inicio < 0 else inicio): (len(texto) if fim < 0 else fim)]


def _desdobrado(texto: str) -> str:
    """As mudanças de linha DENTRO de um parágrafo viram espaço; as linhas em branco ficam.

    Sem isto o varrimento mente por causa da largura da coluna: o ``limits.txt`` embrulha
    ``that "vou\n  considerar"`` ao fim da linha, e uma procura por substring exacta declara
    que a proibição não existe — foi o que este ficheiro mediu à primeira corrida.
    """
    return re.sub(r"[ \t]*(?<!\n)\n(?!\n)[ \t]*", " ", texto)


def _ocorrencias(texto: str, palavra: str) -> "list[int]":
    saida, i = [], texto.find(palavra)
    while i >= 0:
        saida.append(i)
        i = texto.find(palavra, i + 1)
    return saida


def _sem_a_regra() -> str:
    """O ``system.txt`` com a secção nova apagada — A MUTAÇÃO, construída uma vez só."""
    inicio = SYSTEM.find(CABECALHO)
    assert inicio > 0, "o cabeçalho mudou: a mutação deixaria de mutar coisa nenhuma"
    fim = SYSTEM.find("\n## ", inicio)
    assert fim > inicio, "não há secção a seguir: a mutação apagaria o resto do ficheiro"
    return SYSTEM[:inicio] + SYSTEM[fim + 1:]


def _o_que_falta(texto: str) -> "list[str]":
    """As faltas da regra no ``system.txt`` dado. Lista vazia = está lá, e está na secção.

    Desdobrado pela mesma razão que o varrimento do muzzle: o que se exige é a regra, não a
    largura da coluna em que ela calhou ser escrita."""
    seccao = _desdobrado(_seccao(texto, CABECALHO))
    if not seccao.strip():
        return [f"a secção {CABECALHO!r} não existe"]
    faltas = [f"a secção não nomeia {chave}" for chave in CHAVES if chave not in seccao]
    if "in the panel" not in seccao:
        faltas.append("a secção não diz ONDE se escreve — falta o painel")
    if "persona's rules" not in seccao.lower():
        faltas.append("a secção não diz que as figuras vivem nas REGRAS da persona")
    faltas += [f"a secção não proíbe {p!r}" for p in MUZZLE if p not in seccao]
    return faltas


def _exige_proibicao(nome: str, texto: str) -> None:
    """Cada palavra do muzzle aparece no ficheiro, e SÓ dentro de um parágrafo que a proíbe.

    Varre o ficheiro inteiro de propósito: a regra que interessa não é "existe uma proibição
    algures", é "não existe nenhuma instrução em sentido contrário no mesmo prompt".
    """
    plano = _desdobrado(texto)
    for palavra in MUZZLE:
        indices = _ocorrencias(plano, palavra)
        assert indices, f"{nome} não proíbe {palavra!r} em lado nenhum"
        for i in indices:
            par = _paragrafo(plano, i)
            assert "NEVER" in par or "REJECT" in par, (
                f"{nome} escreve {palavra!r} num parágrafo que não a proíbe — uma instrução "
                f"em sentido contrário à regra, no mesmo ficheiro:\n{par.strip()}"
            )


# ── guardas sobre as guardas ───────────────────────────────────────────────────────────
def test_o_fatiador_encontra_a_seccao_e_para_no_cabecalho_seguinte():
    """Sem isto, um ``_seccao`` que devolvesse o ficheiro inteiro — ou "" — deixava tudo o que
    vem abaixo verde sobre nada."""
    seccao = _seccao(SYSTEM, CABECALHO)
    assert seccao.strip(), CABECALHO
    assert "## Scope" not in seccao, "o fatiador comeu a secção seguinte"
    assert "NOT CONFIGURED" not in seccao.split("estimate from what is declared today")[0], (
        "o fatiador começou antes do cabeçalho e apanhou o bloco anterior"
    )
    assert _seccao(SYSTEM, "### Uma secção que não existe") == ""


def test_as_chaves_do_prompt_sao_as_que_o_config_le():
    """O prompt manda alguém escrever estas linhas no painel. Se o código passar a ler outro
    nome, é o prompt que fica a mentir — e é aqui que isso tem de doer."""
    from cogno_praxis.coordinator import config as config_module

    fonte = Path(config_module.__file__).read_text(encoding="utf-8")
    for chave in CHAVES:
        assert f'"{chave}"' in fonte, f"{chave} não aparece em config.py — o prompt inventou-a"


# ── o gémeo ────────────────────────────────────────────────────────────────────────────
def test_gemeo_t102_a_declaracao_encontra_a_regra_no_prompt():
    """O turno real: o contacto DECLARA, e o prompt tem de ter a regra — e tem-na na secção."""
    assert _o_que_falta(SYSTEM) == [], _o_que_falta(SYSTEM)

    seccao = _desdobrado(_seccao(SYSTEM, CABECALHO))
    for chave in T102_CHAVES:
        assert chave in seccao, (
            f"{T102!r} declara o que {chave} guarda, e a regra não nomeia essa chave"
        )
    # A regra traz o PRÓPRIO turno como exemplo, e é isso que a prende a t102 em vez de a
    # deixar ser uma regra genérica sobre configuração.
    assert "o valor é 120 reais por hora" in seccao.lower(), T102
    assert "30,00" in seccao, T102
    assert "NAMING THE KEY" in seccao and "WHERE it is written" in seccao


def test_gemeo_t102_o_juiz_sabe_que_a_resposta_honesta_esta_completa():
    """O outro lado do mesmo turno. Um juiz fail-CLOSED que leia "não gravei nada, a chave é
    esta" como objectivo por cumprir rejeita a resposta certa e o laço esgota-se num handoff —
    a família que este repo já pagou. E rejeita a falsa."""
    plano = _desdobrado(LIMITS)
    bloco = [b for b in plano.split("\n\n") if "A figure the contact DECLARED" in b]
    assert len(bloco) == 1, bloco
    assert "COMPLETE and CORRECT answer" in bloco[0]
    assert "REJECT" in bloco[0]
    for chave in CHAVES:
        assert chave in bloco[0], chave
    assert "says a figure the contact declared was recorded as configuration" in plano


# ── o controlo ─────────────────────────────────────────────────────────────────────────
def test_controlo_t99_um_pedido_de_valor_continua_a_mandar_estimar():
    """t99 PEDE um valor, não o declara. A regra nova não o pode transformar numa recusa: as
    duas linhas que encaminham o pedido para a ferramenta continuam intactas, e a própria
    regra exclui-se de um pedido em vez de deixar a distinção ao acaso."""
    plano = _desdobrado(SYSTEM)
    assert '"quanto eu recebo/vou receber"' in plano
    assert "estimate_professor_pay(period?, turma?)" in plano
    assert ("A professor asking what THEY earn is asking a coordination question and you "
            "answer it, with estimate_professor_pay.") in plano

    seccao = _desdobrado(_seccao(SYSTEM, CABECALHO))
    assert "ASKING is not declaring" in seccao
    assert T99 in seccao, "a regra não nomeia o pedido que NÃO deve morder"
    assert "estimate_professor_pay exactly as above" in seccao


# ── o muzzle ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("nome,texto", [("system.txt", SYSTEM), ("limits.txt", LIMITS)],
                         ids=("system.txt", "limits.txt"))
def test_muzzle_twin_cada_palavra_proibida_viaja_com_a_sua_proibicao(nome: str, texto: str):
    _exige_proibicao(nome, texto)


def test_o_varrimento_do_muzzle_sabe_produzir_a_ausencia():
    """«Correr apagar antes de abrir.» Uma asserção de presença que nunca viu a falha não sabe
    falhar, e o varrimento acima seria verde sobre um prompt que mandasse dizer "anotado"."""
    contrario = SYSTEM + "\n\nSe o contacto declarar um valor, diga que ficou anotado.\n"
    with pytest.raises(AssertionError, match="parágrafo que não a proíbe"):
        _exige_proibicao("system.txt (mutado)", contrario)

    calado = SYSTEM.replace('"anotado", "guardado" or "registrado"', '"guardado"')
    with pytest.raises(AssertionError, match="não proíbe 'anotado'"):
        _exige_proibicao("system.txt (mutado)", calado)


# ── a mutação ──────────────────────────────────────────────────────────────────────────
def test_mutacao_remover_a_regra_mata_o_gemeo():
    sem_a_regra = _sem_a_regra()
    assert CABECALHO not in sem_a_regra
    assert "## Scope" in sem_a_regra, "a mutação levou mais do que a secção"
    assert _o_que_falta(sem_a_regra) == [f"a secção {CABECALHO!r} não existe"]


def test_uma_assercao_sobre_o_ficheiro_inteiro_teria_passado_antes():
    """A razão contada de o gémeo se fatiar por secção em vez de procurar no ficheiro.

    ``PAY_RATE_PER_HOUR`` já estava no ``system.txt`` antes desta mudança, no ramo
    "NOT CONFIGURED". Um teste que procurasse a chave no ficheiro inteiro passava sobre a MAIN
    e não morria com a mutação — seria uma asserção verdadeira por acidente de vizinhança.
    """
    sem_a_regra = _sem_a_regra()
    assert "PAY_RATE_PER_HOUR" in sem_a_regra, (
        "a chave já não vive fora da regra nova — este controlo deixou de ter assunto"
    )
    assert "PAY_RATE_PER_HOUR" not in _seccao(sem_a_regra, CABECALHO)
    assert SYSTEM.count("PAY_RATE_PER_HOUR") > sem_a_regra.count("PAY_RATE_PER_HOUR")
