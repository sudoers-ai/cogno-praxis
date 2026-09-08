"""O portão C dispara — sobre a CADEIA real, não sobre a função.

O `#89` entregou o primeiro produtor do terceiro portão de confirmação do EGO: uma remoção que
LÊ o livro, não apaga, e devolve a linha que apagaria — com data, descrição e valor — mais as
irmãs que a mesma busca de substring apanhou. Ficou **entregue, servido, e não dispararia**.

A causa não estava no produtor. Estava numa palavra da anotação:

    portão B   ``destructiveHint`` → ``requires_confirmation``, decidido por NOME, ANTES de correr
    portão C   a chamada CORREU, LEU, e diz sobre ESTA chamada "não comitei — pergunta primeiro"

**O B pre-empte o C por construção**: `cogno_anima/stages/ego.py` retém e faz ``continue`` antes
de ``dispatcher.execute``, portanto uma tool que ele segura NUNCA corre — e a pergunta
fundamentada nunca chega a existir. O `remove_by_search` estava anotado assim.

Nada aqui é um duplo a não ser o modelo: o servidor do bookkeeper corre no seu próprio processo
sobre stdio, o ``MCPDispatcher`` do cogno-mcp mapeia a resposta, e o ``EgoStage`` — o estágio a
sério — decide o que fazer com ela. É a cadeia que o host corre.

O que fica pinado, e o que cada um custaria se partisse:

  1. com a anotação de ONTEM a tool não corre de todo (gémeo byte-a-byte em
     ``gate_twin_server.py``, que partilha o objecto-função e difere só na anotação);
  2. com a de HOJE ela corre, o C levanta-se, e o EGO PARA — sem escrever nada, e com a prosa
     que só um leitor poderia ter escrito;
  3. a VOLTA fecha: repetida com o argumento que a própria tool nomeou, a escrita aterra;
  4. o mesmo turno não se auto-confirma — e a razão é estrutural, não uma regra a mais.

Cada teste abre a SUA sessão em vez de partilhar uma fixture: uma fixture assíncrona entra no
cancel scope do transporte numa task e sai noutra, o que o anyio recusa; e um processo novo é um
livro novo, portanto um teste que apaga uma linha não decide o que o vizinho mede.
"""

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp SDK not installed")
pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")
pytest.importorskip("cogno_anima", reason="cogno-anima not installed")

from cogno_anima import metakeys as mk                                        # noqa: E402
from cogno_anima.stages.ego import EgoStage                                   # noqa: E402
from cogno_anima.types import (                                               # noqa: E402
    IntentResult, NoumenoResult, PipelineContext, StageMetrics, committed_this_turn)
from cogno_mcp import MCPDispatcher, stdio_session                            # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
TWIN = str(Path(__file__).resolve().parent / "gate_twin_server.py")
# O subprocesso tem de importar ESTE checkout, não o editable install que de outro modo o
# ensombra — senão este ficheiro mede a árvore de outra pessoa. Mesmo bloco, mesma razão, que
# em test_bookkeeper_via_mcp.py.
_ENV = {**os.environ, "PYTHONPATH": os.pathsep.join(
    [str(_ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}

EU = "emp-1"
SYS = "You are an executor. Use the tools to manage the ledger."


@asynccontextmanager
async def _live():
    async with stdio_session(sys.executable, args=[TWIN], env=_ENV) as session:
        yield await MCPDispatcher.create(session)


class ScriptedTextBackend:
    """Um modelo só-de-texto: ``generate`` + ``model``, portanto nunca satisfaz
    ``ToolCallingBackend``.

    Deliberado — põe o EGO no caminho de fallback ``<TOOL_CALL>``, que é o que o
    ``OllamaBackend`` por omissão corre. O portão não pode depender de function calling nativo.
    """

    model = "scripted"

    def __init__(self, turns):
        self.turns = list(turns)

    async def generate(self, system, prompt):
        turn = self.turns.pop(0) if self.turns else {"content": "done"}
        text = turn.get("content", "")
        for name, args in turn.get("calls", []):
            text += f'\n<TOOL_CALL>{{"tool": "{name}", "args": {json.dumps(args)}}}</TOOL_CALL>'
        return text, 5, 3


def _m(stage):
    return StageMetrics(stage=stage, elapsed_ms=0.0, tokens_in=0, tokens_out=0, model="stub")


def _ctx(user="remove the internet entry", **meta):
    ctx = PipelineContext(
        user_input=user,
        noumeno=NoumenoResult(
            original=user, rewritten=user, context_turn="", language="en", drift_score=0.0,
            drift_tag="PASS_THROUGH", changed=False, confidence=0.9, change_subject=False,
            subject_similarity=1.0, context_used=False, preserved_terms=[],
            rewrite_warnings=[], metrics=_m("noumeno")),
        intent=IntentResult(
            intent_class="ACTION_REQUEST", sentiment="NEUTRAL", confidence=0.9,
            temporal_class="PRESENT", triad_signal="EGO", goal="remove a ledger entry",
            domains=["FINANCE"], entities_objects=["entry"], metrics=_m("ner")))
    ctx.metadata.update(meta)
    return ctx


async def _rows(disp) -> int:
    out = (await disp.execute("get_summary", {"identity_id": EU, "role": "ADMIN"})).output
    return out.count("- 2026-")


# ── gémeo 0: a premissa, para não a assumir ────────────────────────────────────────────
async def test_the_twin_differs_only_in_the_annotation():
    """Se os dois nomes não estiverem ligados à MESMA função, tudo abaixo compara duas coisas."""
    async with _live() as disp:
        assert disp.requires_confirmation("purge_by_search") is True    # a anotação de ontem
        assert disp.requires_confirmation("remove_by_search") is False  # a de hoje
        assert disp.is_mutating("remove_by_search") is True             # continua a ser escrita
        # a mesma pergunta, o mesmo livro, a mesma resposta — só o portão muda
        a = await disp.execute("purge_by_search", {"query": "internet", "identity_id": EU})
        b = await disp.execute("remove_by_search", {"query": "internet", "identity_id": EU})
        assert a.output == b.output
        assert a.needs_confirmation is True and b.needs_confirmation is True


# ── gémeo 1: a anotação de ONTEM — o B retém, e o C nunca corre ────────────────────────
async def test_under_yesterdays_annotation_the_tool_never_runs():
    """O estado que este PR fecha, MEDIDO em vez de recordado.

    O portão B faz o seu trabalho — nada é escrito — e é precisamente por o fazer *antes* de
    correr que a pergunta fundamentada não existe. O texto que chega ao traço é a frase por
    NOME, igual para toda a remoção: não diz qual linha, nem de que valor, nem que a busca
    apanhou outras duas."""
    async with _live() as disp:
        before = await _rows(disp)
        backend = ScriptedTextBackend(
            [{"calls": [("purge_by_search", {"query": "internet", "identity_id": EU})]}])
        ctx = await EgoStage().process(_ctx(), backend, disp, system_prompt=SYS)
        res = ctx.ego_result

        assert [h.tool for h in res.pending_confirmation] == ["purge_by_search"]
        held = res.pending_confirmation[0]
        assert held.ok is False and held.side_effect is False
        # a tool NÃO correu: a frase é a do portão, não a do livro
        assert "PENDING CONFIRMATION" in held.result
        assert "NOT REMOVED" not in held.result       # a prosa do produtor nunca foi produzida
        assert "149,90" not in held.result            # nem o valor que só uma leitura sabe
        assert "also match" not in held.result        # nem as irmãs
        assert await _rows(disp) == before
        assert committed_this_turn(ctx) is False


# ── gémeo 2: a anotação de HOJE — corre, o C levanta-se, e nada foi escrito ────────────
async def test_the_shipped_annotation_lets_the_grounded_question_be_asked():
    """A entrega. A chamada executa, a skill lê, recusa comitar, e o EGO segura-a — com a
    proposta citada na linha que ela leu."""
    async with _live() as disp:
        before = await _rows(disp)
        backend = ScriptedTextBackend(
            [{"calls": [("remove_by_search", {"query": "internet", "identity_id": EU})]}])
        ctx = await EgoStage().process(_ctx(), backend, disp, system_prompt=SYS)
        res = ctx.ego_result

        # (1) SEGURADA, e o laço parou nela
        assert [h.tool for h in res.pending_confirmation] == ["remove_by_search"]
        held = res.pending_confirmation[0]
        assert held.ok is False and held.side_effect is False

        # (2) a prosa que só um LEITOR poderia ter escrito — a diferença toda entre B e C
        assert "NOT REMOVED" in held.result
        assert "2026-03-10" in held.result and "149,90" in held.result   # data e valor
        assert "2 other entry(ies) also match" in held.result            # as irmãs
        # O id NÃO está na prosa — só no canal. Ver `server._removal_proposal_text`.
        assert "confirm_tx_id" not in held.result

        # (3) nada leu como escrita, em nenhuma das fontes que o predicado une
        assert await _rows(disp) == before
        assert committed_this_turn(ctx) is False
        assert res.has_side_effects is False


async def test_the_proposal_is_never_recorded_as_a_write():
    """Sem o ``_meta`` esta é a linha que fica errada, e em silêncio.

    Medido 2026-09-03: tirar a anotação e NÃO emitir o ``_meta`` deixa a proposta chegar como
    ``ok=True, side_effect=True`` — o ``side_effect`` do dispatcher é ``mutating and not asks``,
    e sem a chave ``asks`` é falso. O turno passa a declarar uma escrita que não houve, e uma
    declaração dessas encaminha o turno para um humano. As duas metades não podiam aterrar
    separadas, e é isto que o diz."""
    async with _live() as disp:
        r = await disp.execute("remove_by_search", {"query": "internet", "identity_id": EU})
        assert r.needs_confirmation is True
        assert r.side_effect is False          # ← a que estaria a True sem o ``_meta``
        assert r.ok is True                    # correu bem; simplesmente não comitou
        # e nomeia o argumento de que precisa — o nome é da TOOL, nunca inventado por cima
        assert set(r.confirm_arguments) == {"confirm_tx_id"}
        # …e o valor NÃO viaja no texto: o canal é a única via da proposta ao commit.
        assert r.confirm_arguments["confirm_tx_id"] not in r.output


# ── gémeo 3: a VOLTA fecha — a confirmação continua a apagar a linha certa ─────────────
async def test_the_confirmed_replay_removes_exactly_the_row_that_was_proposed():
    """O portão só vale se a porta abrir do outro lado. Aqui vai pelo caminho que o host corre:
    ``ego_confirmed_calls`` com os argumentos que a própria tool nomeou."""
    async with _live() as disp:
        before = await _rows(disp)
        proposal = await disp.execute("remove_by_search", {"query": "internet",
                                                           "identity_id": EU})
        # O que um host apanha da resposta do dispatcher. Não pode vir do ``ToolExecution``
        # segurado: esse leva tool/arguments/result e mais nada, portanto o argumento que a tool
        # pediu cai na fronteira do estágio — é por isso que a volta se liga onde o resultado
        # ainda está inteiro.
        confirmed = {"query": "internet", "identity_id": EU, **proposal.confirm_arguments}

        ctx = await EgoStage().process(
            _ctx(**{mk.EGO_CONFIRMED: True,
                    mk.EGO_CONFIRMED_CALLS: [{"tool": "remove_by_search",
                                              "arguments": confirmed}]}),
            ScriptedTextBackend([{"content": "done"}]), disp, system_prompt=SYS)
        res = ctx.ego_result

        done = [e for s in res.steps for e in s.tool_calls]
        assert [e.tool for e in done] == ["remove_by_search"]
        assert done[0].ok is True and done[0].side_effect is True
        assert "Removed:" in done[0].result and "149,90" in done[0].result
        assert res.pending_confirmation == []
        assert await _rows(disp) == before - 1
        assert committed_this_turn(ctx) is True


async def test_a_confirmed_replay_that_drops_the_argument_fails_loudly():
    """O gémeo vermelho do anterior: a mesma repetição SEM o argumento que a tool nomeou.

    A skill volta a perguntar, e não há a quem — o utilizador já disse que sim. O EGO recusa-o
    em voz alta em vez de despachar um "feito" sobre um turno que não escreveu nada. É o que
    torna a ligação da volta carga, e não decoração."""
    async with _live() as disp:
        before = await _rows(disp)
        ctx = await EgoStage().process(
            _ctx(**{mk.EGO_CONFIRMED: True,
                    mk.EGO_CONFIRMED_CALLS: [{"tool": "remove_by_search",
                                              "arguments": {"query": "internet",
                                                            "identity_id": EU}}]}),
            ScriptedTextBackend([{"content": "done"}]), disp, system_prompt=SYS)

        done = [e for s in ctx.ego_result.steps for e in s.tool_calls]
        assert [e.tool for e in done] == ["remove_by_search"]
        assert done[0].ok is False and done[0].side_effect is False
        assert "Do NOT report this as done" in (done[0].error or "")
        assert await _rows(disp) == before          # e o livro ficou intacto
        assert committed_this_turn(ctx) is False


# ── gémeo 4: o mesmo turno não se auto-confirma ────────────────────────────────────────
async def test_the_model_cannot_confirm_its_own_proposal_in_the_same_turn():
    """A pergunta que qualquer revisor faz a seguir: sem o portão B, o que impede o modelo de
    propor e confirmar sozinho?

    Duas coisas, e nenhuma é uma regra acrescentada. O ``confirm_tx_id`` é um id que ele só pode
    ter aprendido da PRIMEIRA resposta, portanto não cabe no mesmo passo; e assim que a resposta
    chega o portão C levanta-se e o laço PARA, portanto não há passo seguinte. O modelo aqui
    tenta as duas coisas — o passo 2 nunca acontece."""
    async with _live() as disp:
        before = await _rows(disp)
        backend = ScriptedTextBackend([
            {"calls": [("remove_by_search", {"query": "internet", "identity_id": EU})]},
            # o que ele faria se o laço continuasse; nem sequer é chamado
            {"calls": [("remove_by_search", {"query": "internet", "identity_id": EU,
                                             "confirm_tx_id": "whatever"})]},
        ])
        ctx = await EgoStage().process(_ctx(), backend, disp, system_prompt=SYS)

        assert len(ctx.ego_result.steps) == 1              # o laço parou no primeiro
        assert len(backend.turns) == 1                     # o segundo guião nunca foi pedido
        assert await _rows(disp) == before
        assert committed_this_turn(ctx) is False


async def test_a_guessed_id_is_not_a_way_into_the_write_path():
    """E se ele adivinhar? Um id que não está entre as linhas do próprio chamador não cai para
    "a mais recente" — volta a propor. Adivinhar qual linha um id velho queria dizer é
    exactamente o erro que os dois passos existem para impedir."""
    async with _live() as disp:
        before = await _rows(disp)
        r = await disp.execute("remove_by_search", {"query": "internet", "identity_id": EU,
                                                    "confirm_tx_id": "deadbeefcafe"})
        assert r.needs_confirmation is True and "NOT REMOVED" in r.output
        assert await _rows(disp) == before
