"""Uma proposta de confirmação tem a forma da sua FONTE — e há duas fontes, não uma.

## Contadas, antes de se escrever uma linha

* **gate B** — o HOST segura, decidido pelo NOME da ferramenta, **ANTES** de ela correr, e monta
  a frase a partir dos ARGUMENTOS da chamada. Não vive aqui: vive no ``cogno-host``
  (``assembler._confirm_gate`` → ``voice_traits.confirmation_text``), e é lá que a conformidade
  dela é pinada — um teste que atravessa repositórios fica vermelho sozinho.
* **gate C** — a SKILL segura, decidido por ESTA chamada, **DEPOIS** de ela ler, e a proposta é o
  ``output`` dela própria, fundamentado no que acabou de ver. Vive aqui, e tem hoje **duas
  instâncias numa só forma**: ``companies.company_delete`` (segredo ``confirm_token``) e
  ``bookkeeper.remove_by_search`` (segredo ``confirm_tx_id``).

E há uma **terceira** forma no pacote, que não é um portão e é por isso que aparece neste
ficheiro: o ``coordinator.preview_schedule_to_calendar``. É uma LEITURA — não segura nada, não
tem ``_meta``, não tem segredo — que existe para o modelo poder pôr os números ao contacto antes
de o gate B segurar o envio. Responde à mesma pergunta por outro mecanismo, e a confusão entre
ela e o gate C é a que este ficheiro impede.

## Porque as três não se achatam numa forma só

**As instruções que dão ao modelo são OPOSTAS, e têm de ser.** Uma proposta de gate C diz «*Do
NOT call this again yourself*»: quem repete a chamada é o host, com o segredo que veio pelo
``_meta``. O preview diz o contrário — «*only after an explicit yes, call ...*» — porque ali
não há retenção nenhuma e é o modelo que tem de fazer a segunda chamada.

Trocá-las é um defeito medido dos dois lados. Dar ao gate C a instrução do preview põe o modelo
a re-chamar a ferramenta sozinho, sem segredo: é o par de traços 1417→1420 (2026-09-08), em que
o ``_refuse_if_still_asking`` do EGO mata o turno e o contacto é perguntado uma SEGUNDA vez
depois de já ter dito que sim. Dar ao preview a instrução do gate C deixa o envio por fazer,
porque ninguém o vai repetir.

## E o pino do segredo — o que já havia, medido, e o que este ficheiro acrescenta

**Um segredo impresso não é um segredo, é uma sugestão.** As DUAS instâncias já o guardam, cada
uma à sua maneira: ``test_um_segredo_impresso_nao_e_um_segredo.py`` para o bookkeeper (com a
medição que o obrigou — traços 1380 e 1420, o modelo a pôr um VALOR no campo do id, uma das
vezes com o id certo no texto que acabara de receber) e
``test_companies_server.py::test_the_delete_proposal_carries_the_gate_C_meta`` para o
``company_delete``. Medido, e não suposto: repondo o token no texto de qualquer das duas, a
suíte que já existia fica vermelha.

**O que falta não é o pino, é a REGRA.** Os dois são asserções escritas à mão, uma por vertical,
sobre a instância que o autor tinha à frente — logo o TERCEIRO vertical a falar gate C nasce sem
nenhuma, em silêncio, que é o modo por defeito de uma família crescer torta. Aqui a lista de
casos é DESCOBERTA na árvore e comparada com os condutores: quem chegar sem condutor chega
vermelho, com o nome do ficheiro na mensagem. E a direcção que faltava aos dois é a de trás —
nada guardava que uma proposta NÃO pudesse nascer fora da forma.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from cogno_praxis.bookkeeper.server import build_server as build_bookkeeper
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore
from cogno_praxis.companies import CompanyService, InMemoryCompanyStore
from cogno_praxis.companies.server import build_server as build_companies
from cogno_praxis.coordinator.server import build_server as build_coordinator

_PKG = pathlib.Path(__file__).resolve().parents[2] / "cogno_praxis"

# Os literais do canal do gate C, tal como o `cogno-mcp` os lê. Estão DUPLICADOS em cada
# vertical de propósito (nenhum depende do bridge em runtime); que sejam os do bridge é pinado
# em `tests/integration/test_bookkeeper_via_mcp.py`. O que se pina AQUI é a outra metade: que os
# verticais não divergem UNS DOS OUTROS.
META_ASKS = "cogno-mcp/needs_confirmation"
META_ARGS = "cogno-mcp/confirm_arguments"

EU = "emp-1"


# ── DESCOBERTA: quem produz uma proposta de gate C, lido da árvore e não de uma lista ────


def _modulos() -> "list[pathlib.Path]":
    return sorted(p for p in _PKG.rglob("*.py") if "__pycache__" not in p.parts)


def _blocos_com_meta() -> "dict[str, str]":
    """``{ficheiro: função}`` para cada ``TextContent(..., _meta=...)`` do pacote."""
    achados: "dict[str, str]" = {}
    for path in _modulos():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        pais = {id(filho): no for no in ast.walk(tree) for filho in ast.iter_child_nodes(no)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "TextContent"):
                continue
            envolvente, corrente = "", node
            while id(corrente) in pais:
                corrente = pais[id(corrente)]
                if isinstance(corrente, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    envolvente = corrente.name
                    break
            achados[str(path.relative_to(_PKG))] = envolvente
    return achados


# ── OS CONDUTORES: cada produtor descoberto tem de ter um, e é a lista que fecha ─────────


def _bookkeeper():
    svc = BookkeeperService(InMemoryBookkeeperStore())
    svc.add_outcome("material de escritório", "45,00", EU, tx_date="2026-09-08")
    return build_bookkeeper(svc), "remove_by_search", {"query": "material", "identity_id": EU}


def _companies():
    svc = CompanyService(InMemoryCompanyStore())
    svc.register("Acme", identity_id=EU)
    return (build_companies(svc), "company_delete",
            {"company_id": "acme", "identity_id": EU, "role": "ADMIN"})


CONDUTORES = {
    "bookkeeper/server.py": ("remove_by_search", _bookkeeper),
    "companies/server.py": ("company_delete", _companies),
}


def _partes(call):
    return call[0] if isinstance(call, tuple) else call


def _texto(call) -> str:
    return "\n".join(b.text for b in _partes(call) if getattr(b, "type", None) == "text")


def _meta(call) -> dict:
    for b in _partes(call):
        m = getattr(b, "meta", None) or getattr(b, "_meta", None) or {}
        if m:
            return dict(m)
    return {}


async def _propoe(ficheiro: str):
    mcp, tool, args = CONDUTORES[ficheiro][1]()
    return await mcp.call_tool(tool, args)


# ── DIRECÇÃO 1: toda proposta usa a forma da sua fonte ───────────────────────────────────


@pytest.mark.parametrize("ficheiro", sorted(CONDUTORES))
async def test_a_proposta_do_gate_C_tem_a_forma_do_gate_C(ficheiro):
    """Um bloco de texto, e o segredo ao lado no ``_meta`` — as duas metades, sempre as duas.

    Levantar a bandeira sem dizer o que se quer de volta deixa o host a perguntar «posso?» sem
    ter com que comitar; nomear o argumento sem levantar a bandeira faz a proposta passar por
    escrita feita. Nenhuma das duas metades se aterra sozinha."""
    call = await _propoe(ficheiro)
    meta = _meta(call)

    assert meta.get(META_ASKS) is True, f"{ficheiro}: a proposta não levanta a bandeira do gate C"
    args = meta.get(META_ARGS)
    assert isinstance(args, dict) and args, f"{ficheiro}: não diz o que precisa de volta"
    assert all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in args.items())


@pytest.mark.parametrize("ficheiro", sorted(CONDUTORES))
async def test_a_proposta_ABRE_a_dizer_que_nada_aconteceu(ficheiro):
    """A convenção partilhada: a primeira linha nega o commit, e não é o marcador do commit.

    O resto do sistema distingue proposta de execução pelo marcador (``Removed: ``); uma
    proposta que o carregasse seria lida por toda a gente como uma escrita que aconteceu."""
    texto = _texto(await _propoe(ficheiro))
    assert texto.startswith("NOT "), f"{ficheiro}: {texto[:60]!r}"
    assert not texto.startswith("Removed: ")


@pytest.mark.parametrize("ficheiro", sorted(CONDUTORES))
async def test_a_proposta_manda_o_modelo_NAO_repetir_a_chamada(ficheiro):
    """A instrução que separa o gate C do preview. Quem repete a chamada é o HOST."""
    tool = CONDUTORES[ficheiro][0]
    texto = _texto(await _propoe(ficheiro))
    assert f"Do NOT call {tool} again yourself" in texto, f"{ficheiro}: {texto!r}"


@pytest.mark.parametrize("ficheiro", sorted(CONDUTORES))
async def test_o_segredo_que_COMITA_nao_esta_no_texto(ficheiro):
    """O pino, nas DUAS instâncias — a razão de este ficheiro existir e não bastar o do #122.

    Nem o VALOR (a chave que comita) nem o NOME do argumento: nomeá-lo já é convidar a cópia, e
    a cópia foi medida duas vezes com o campo preenchido a partir do texto."""
    call = await _propoe(ficheiro)
    texto, args = _texto(call), _meta(call).get(META_ARGS) or {}
    for nome, segredo in args.items():
        assert segredo not in texto, f"{ficheiro}: o segredo foi impresso — {texto!r}"
        assert nome not in texto, f"{ficheiro}: o texto nomeia {nome} e convida a cópia"


@pytest.mark.parametrize("ficheiro", sorted(CONDUTORES))
async def test_a_proposta_continua_a_NOMEAR_o_que_o_contacto_tem_de_verificar(ficheiro):
    """O gémeo do que FICA: tirar o segredo não pode custar a linha que identifica o objecto.

    Uma proposta que o contacto não consegue verificar não é uma confirmação, é uma
    formalidade — e «esta ação — 45.00» é exactamente isso."""
    texto = _texto(await _propoe(ficheiro))
    esperado = {"bookkeeper/server.py": ("material de escritório", "45,00", "2026-09-08"),
                "companies/server.py": ("Acme",)}[ficheiro]
    for facto in esperado:
        assert facto in texto, f"{ficheiro}: a proposta deixou de nomear {facto!r}"


# ── DIRECÇÃO 2: nada produz uma proposta fora dessas formas ──────────────────────────────


def test_todo_produtor_descoberto_tem_um_CONDUTOR():
    """A guarda por MECANISMO: a lista de casos é DERIVADA da árvore, não escrita à mão.

    Um terceiro vertical que passe a falar gate C chega aqui vermelho, com o nome do ficheiro
    na mensagem, em vez de herdar em silêncio o silêncio de ninguém o ter testado — que foi
    exactamente o que aconteceu ao ``company_delete``."""
    assert set(_blocos_com_meta()) == set(CONDUTORES)


def test_nenhum_bloco_de_texto_do_pacote_sai_SEM_o_canal_do_gate_C():
    """A outra direcção: um ``TextContent`` é a forma do gate C, e só dela.

    Devolver um bloco sem ``_meta`` é a maneira silenciosa de nascer uma segunda forma — o
    ``cogno-mcp`` carimba a chamada como bem sucedida e a proposta viaja como escrita feita."""
    for path in _modulos():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "TextContent"):
                continue
            chaves = {kw.arg for kw in node.keywords}
            assert "_meta" in chaves, (
                f"{path.relative_to(_PKG)}:{node.lineno} devolve um bloco sem o canal do gate C")


def test_os_verticais_nao_divergem_no_NOME_das_chaves():
    """O contrato está duplicado por desenho; o que não pode é divergir entre cópias."""
    literais: "dict[str, set[str]]" = {}
    for path in _modulos():
        texto = path.read_text(encoding="utf-8")
        achadas = {k for k in (META_ASKS, META_ARGS) if f'"{k}"' in texto}
        if achadas:
            literais[str(path.relative_to(_PKG))] = achadas
    assert literais, "as chaves do canal desapareceram do pacote"
    for ficheiro, achadas in literais.items():
        assert achadas == {META_ASKS, META_ARGS}, f"{ficheiro} declara metade do canal: {achadas}"


# ── O GÉMEO DA DISTINÇÃO: o PREVIEW não é um gate C, e as instruções são opostas ─────────


async def test_o_preview_do_coordinator_NAO_finge_ser_um_gate_C():
    """A terceira forma, mantida distinta: uma LEITURA que propõe, sem reter nada.

    Se o preview levantasse a bandeira do gate C, o host reteria uma leitura e pediria de volta
    um segredo que ninguém cunhou. Se o gate C perdesse a bandeira, a proposta viajava como
    escrita feita. É a mesma pergunta com duas respostas certas e diferentes."""
    ferramentas = {t.name: t for t in await build_coordinator().list_tools()}
    preview = ferramentas["preview_schedule_to_calendar"]

    assert (preview.annotations and preview.annotations.readOnlyHint is True), \
        "o preview deixou de ser uma leitura — passou a poder ser segurado pelo gate B"
    assert "coordinator/server.py" not in _blocos_com_meta(), \
        "o preview passou a falar pelo canal do gate C: são mecanismos diferentes"
    assert preview.name not in {tool for tool, _ in CONDUTORES.values()}, \
        "o preview entrou na lista dos produtores de gate C"


async def test_as_instrucoes_das_duas_formas_sao_OPOSTAS_e_e_assim_que_tem_de_ser():
    """Achatá-las numa forma só derruba isto — que é a única razão de estar escrito.

    O gate C manda NÃO repetir (o host repete, com o segredo do ``_meta``); o preview manda
    repetir depois do sim (não há retenção, e o envio é do modelo). Uma instrução no lugar da
    outra parte um dos dois fluxos, e os dois já foram medidos partidos."""
    do_gate_c = " ".join(_texto(await _propoe("bookkeeper/server.py")).split())
    ferramentas = {t.name: t for t in await build_coordinator().list_tools()}
    # O texto do preview é a sua própria descrição — é o que o modelo lê antes de decidir.
    do_preview = " ".join((ferramentas["preview_schedule_to_calendar"].description or "").split())

    assert "Do NOT call remove_by_search again yourself" in do_gate_c
    assert "call remove_by_search again with" not in do_gate_c

    assert "Call this FIRST" in do_preview
    assert "before send_schedule_to_calendar" in do_preview
    assert "Do NOT call" not in do_preview, \
        "o preview ganhou a instrução do gate C — e ninguém repetiria a chamada"
