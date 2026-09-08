"""Uma remoção PERGUNTA — e a pergunta cita a linha que ela leu.

O EGO tem três portões de confirmação, e o terceiro (`cogno_anima/stages/ego.py`, "Fonte C")
**nunca teve um produtor**. Este ficheiro é o primeiro. A distinção que ele mede não é de estilo:

    portão B   `requires_confirmation` — por NOME de ferramenta, decidido ANTES de correr
    portão C   a própria chamada leu, e pergunta sobre ESTA linha, com os dados que leu

O `remove_by_search` é o caso porque **ele já lia antes de escrever** — uma skill que só escreve
não tem sobre o que basear a pergunta e nasceria a adivinhar, exactamente como o portão B. E o que
ele lê é precisamente o que o B não pode saber: o nome da ferramenta é sempre o mesmo, mas *qual*
linha a busca de substring apanhou, de que valor e de que data, só se sabe depois da leitura.

**O defeito medido que isto fecha:** `matches_query` é substring dobrada em acento/caixa
(`engine.py`), portanto `"internet"` casa a conta de Janeiro, a de Fevereiro e a de Março. O código
antigo removia a MAIS RECENTE em silêncio e ninguém — nem o utilizador, nem o modelo, nem o traço —
ficava a saber que existiam outras duas.

**E o TOCTOU, que é o segundo:** a confirmação chega por `confirm_tx_id`, o id da linha, não por um
sim/não. Entre a proposta e o "pode apagar" pode entrar um lançamento novo que também casa, e "a
mais recente" passaria a ser outra linha. Com o id, apaga-se o que foi proposto ou não se apaga nada.
"""

from __future__ import annotations

import pytest

from cogno_praxis.bookkeeper.server import build_server
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore

EU = "emp-1"
OUTRO = "emp-2"


def _svc() -> BookkeeperService:
    return BookkeeperService(InMemoryBookkeeperStore())


def _com_tres_internets() -> BookkeeperService:
    svc = _svc()
    svc.add_outcome("internet janeiro", 100, EU, tx_date="2026-01-10")
    svc.add_outcome("internet fevereiro", 110, EU, tx_date="2026-02-10")
    svc.add_outcome("internet março", 149.90, EU, tx_date="2026-03-10")
    return svc


def _quantas(svc: BookkeeperService, quem: str = EU) -> int:
    return int(svc.get_summary(quem, "EMPLOYEE")["outcome_count"])


# ── gémeo 1: SEM confirmação → não escreve, e a resposta cita o que leu ──────────────
def test_without_confirmation_it_writes_nothing_and_quotes_what_it_read():
    """A proposta tem de trazer DATA, DESCRIÇÃO e VALOR. Uma pergunta genérica ("confirma?")
    seria o portão B outra vez — é a fundamentação que separa os dois."""
    svc = _com_tres_internets()

    out = svc.remove_by_search("internet", EU)

    assert out.needs_confirmation is True
    assert out.removed is None and out.committed is False
    assert _quantas(svc) == 3, "nada pode desaparecer do livro numa proposta"

    p = out.proposal
    assert p is not None
    assert p.entry["date"] == "2026-03-10"            # a mais recente — a que ela removeria
    assert p.entry["description"] == "internet março"
    assert p.entry["amount"] == 149.90
    assert p.confirm_tx_id == p.entry["tx_id"]

    # e as irmãs que a mesma busca apanhou: a ambiguidade que o portão B não vê
    assert [o["description"] for o in p.others] == ["internet fevereiro", "internet janeiro"]


# ── gémeo 2: COM confirmação → executa, a linha desaparece ───────────────────────────
def test_with_confirmation_it_executes_and_the_row_leaves_the_store():
    svc = _com_tres_internets()
    proposta = svc.remove_by_search("internet", EU).proposal
    assert proposta is not None

    out = svc.remove_by_search("internet", EU, confirm_tx_id=proposta.confirm_tx_id)

    assert out.committed is True and out.needs_confirmation is False
    assert out.removed is not None and out.removed["description"] == "internet março"
    assert _quantas(svc) == 2, "a linha confirmada tem de sair do store"
    restantes = {t["description"] for t in svc.search("internet", EU, "EMPLOYEE")}
    assert restantes == {"internet janeiro", "internet fevereiro"}


# ── gémeo 3: nada corresponde → comportamento de hoje, INALTERADO ────────────────────
def test_no_match_asks_for_nothing_at_all():
    """Não há sobre o que perguntar. Este é o controlo que impede a leitura preguiçosa
    "toda a chamada sem `confirm_tx_id` pergunta" — essa versão passaria os dois gémeos
    acima e transformaria "não encontrei nada" numa pergunta."""
    svc = _com_tres_internets()

    out = svc.remove_by_search("nao-existe", EU)

    assert out.needs_confirmation is False and out.proposal is None
    assert out.removed is None
    assert _quantas(svc) == 3


# ── a promessa: `needs_confirmation=True` quer dizer que NADA foi comitado ───────────
@pytest.mark.parametrize("query,confirm", [("internet", ""), ("internet", "id-que-nao-existe"),
                                           ("nao-existe", ""), ("", "")])
def test_asking_and_committing_are_mutually_exclusive(query, confirm):
    """O contrato do núcleo (`cogno_anima.types.ToolResult`) conta com isto: um `True` é a
    PROMESSA de que nada foi comitado, e `committed_this_turn` exige `ok` E `side_effect`.
    Aqui a promessa é estrutural — o ramo que propõe é o ramo que não chama `store.remove` —
    mas quem a lê não vê a estrutura, vê o par."""
    svc = _com_tres_internets()
    antes = _quantas(svc)

    out = svc.remove_by_search(query, EU, confirm_tx_id=confirm)

    assert not (out.needs_confirmation and out.committed)
    if out.needs_confirmation:
        assert out.removed is None
        assert _quantas(svc) == antes, "uma proposta não pode mexer no livro"


def test_a_stale_confirm_id_proposes_again_instead_of_guessing():
    """Um `confirm_tx_id` que já não está entre as linhas do chamador NÃO recai em "a mais
    recente". Adivinhar que linha um id velho queria dizer é exactamente o erro que os dois
    passos existem para evitar — e é o TOCTOU de volta pela porta das traseiras."""
    svc = _com_tres_internets()
    p1 = svc.remove_by_search("internet", EU).proposal
    assert p1 is not None
    svc.remove_by_search("internet", EU, confirm_tx_id=p1.confirm_tx_id)   # já apagada

    out = svc.remove_by_search("internet", EU, confirm_tx_id=p1.confirm_tx_id)

    assert out.needs_confirmation is True and out.removed is None
    assert out.proposal is not None
    assert out.proposal.entry["description"] == "internet fevereiro"      # propõe o que HÁ
    assert _quantas(svc) == 2


def test_confirmation_never_crosses_identities():
    """A guarda que já existia continua de pé: um id de outra identidade não é confirmável.
    Sem este caso, `confirm_tx_id` seria um caminho de apagamento cruzado — a proposta lê
    `identity_id=EU`, mas o ramo que comita podia ter ido buscar a linha ao store por id."""
    svc = _svc()
    svc.add_outcome("internet", 100, EU)
    svc.add_outcome("internet", 999, OUTRO)
    alheia = [t for t in svc.search("internet", OUTRO, "EMPLOYEE")][0]

    out = svc.remove_by_search("internet", EU, confirm_tx_id=alheia["tx_id"])

    assert out.removed is None and out.needs_confirmation is True
    assert _quantas(svc, OUTRO) == 1, "a linha do outro não pode sair"


# ── a mesma coisa pela ferramenta MCP, que é o que o EGO vê ──────────────────────────
def _text(res) -> str:
    content = res[0] if isinstance(res, tuple) else res
    return "\n".join(getattr(b, "text", "") for b in content)


@pytest.mark.asyncio
async def test_the_mcp_tool_proposes_then_commits():
    """O texto é o transporte real hoje: o `MCPDispatcher` do cogno-mcp não carrega o campo
    `needs_confirmation` (medido — o nome não existe nesse repositório), portanto o que chega
    ao EGO é a saída da ferramenta. Ela tem de dizer três coisas: que não apagou, QUAL linha,
    e como confirmar.

    E o marcador: a proposta NÃO pode começar por `Removed: ` — é por esse prefixo que o
    `bookkeeper/grounding.py` distingue uma remoção real de uma afirmação inventada.
    """
    svc = _com_tres_internets()
    mcp = build_server(svc)

    proposta = _text(await mcp.call_tool("remove_by_search",
                                         {"query": "internet", "identity_id": EU}))
    assert not proposta.startswith("Removed: ")
    assert "NOT REMOVED" in proposta
    assert "internet março" in proposta and "149" in proposta and "2026-03-10" in proposta
    assert "internet fevereiro" in proposta and "internet janeiro" in proposta
    assert "confirm_tx_id=" in proposta
    assert _quantas(svc) == 3

    tx_id = svc.remove_by_search("internet", EU).proposal.confirm_tx_id   # type: ignore[union-attr]
    assert tx_id in proposta

    feito = _text(await mcp.call_tool(
        "remove_by_search", {"query": "internet", "identity_id": EU, "confirm_tx_id": tx_id}))
    assert feito.startswith("Removed: ") and "internet março" in feito
    assert _quantas(svc) == 2


@pytest.mark.asyncio
async def test_the_mcp_tool_keeps_the_no_match_marker_and_asks_instead_of_failing():
    """O terceiro gémeo pela ferramenta, e o que ele guarda mudou de nome mas não de função.

    A versão anterior fixava a frase BYTE A BYTE, e a razão que dava era o que se lê a jusante:
    `NO_MATCH_MARKER` — "nothing removed" — que o teste do servidor, o `test_bookkeeper_via_mcp`
    e o `hostbench` procuram como SUBSTRING. É essa a dependência real, e é ela que continua
    fixada aqui.

    O resto da frase mudou de propósito. Chegava ao modelo por `ToolResult.error`, o canal que
    um modelo lê como «aquilo que tentaste não resultou», e ele repetia-o: sobre a tabela
    `turn_traces` inteira, três turnos redigiram "Não consegui remover" / "Não foi possível
    remover", um deles a acrescentar "A despesa permanece registrada". Nada foi tentado, logo
    nada falhou — e a alegação por baixo, de que o lançamento não está nos livros, esta
    ferramenta não a pode fazer: procurou UMA grafia, sobre as linhas de UMA identidade.

    Então o que se fixa agora é o DEVER da frase: o marcador, as duas proibições, e o próximo
    passo ser uma PERGUNTA."""
    from mcp.server.fastmcp.exceptions import ToolError

    from cogno_praxis.bookkeeper.grounding import NO_MATCH_MARKER

    mcp = build_server(_com_tres_internets())
    with pytest.raises(ToolError) as erro:
        await mcp.call_tool("remove_by_search", {"query": "aluguel", "identity_id": EU})
    texto = str(erro.value)
    assert NO_MATCH_MARKER in texto            # a dependência a jusante, intacta
    assert "'aluguel'" in texto                # a razão continua a nomear o que se procurou
    assert "nothing was attempted and nothing failed" in texto
    assert "Do NOT tell the user the removal failed" in texto
    assert "not in the system" in texto        # a segunda proibição — a que desinforma
    assert "ASK the user which entry they mean" in texto
