"""A proposta da remoção diz tudo o que o contacto precisa — e não diz o que comita.

**Um segredo impresso não é um segredo, é uma sugestão.** Até 2026-09-08 o texto da proposta
terminava em ``confirm_tx_id='a1b2c3…'`` e mandava o modelo chamar a ferramenta outra vez, isto
é, entregava-lhe a chave do commit e dizia-lhe para a usar.

O que o modelo fez com ela está medido, duas vezes, na tabela `turn_traces` de produção — e as
duas vezes ele pôs um **valor** no campo do id:

    traço 1380 (turno 8)   confirm_tx_id="45.00"
    traço 1420 (turno 8)   confirm_tx_id="45"     <- com o id CERTO no texto que acabara de receber

O segundo é o que decide o desenho. Não é o modelo a falhar uma cópia: é o texto a convidar uma
cópia de que ninguém precisava. O id passa a viajar só no ``_meta`` do bloco
(``cogno-mcp/confirm_arguments``), para a camada que pergunta ao humano e repete a chamada — a
mesma forma, e pela mesma razão, do ``company_delete`` em ``companies/server.py``.

**O que este ficheiro guarda é a outra metade:** tirar o id não pode deixar a frase a nomear
menos do que o contacto precisa para decidir. Uma proposta que o contacto não consegue verificar
não é uma confirmação, é uma formalidade — e «*esta ação — 45.00*» é exactamente isso.

Limite dito em vez de implícito: duas linhas com a MESMA data, MESMA descrição e MESMO valor
continuam indistinguíveis no texto, porque não há nada honesto que as distinga sem imprimir um
id. O que o sistema garante nesse caso não é a legibilidade — é o determinismo: comita-se a
linha que foi PROPOSTA, pelo id que só o canal transporta, nunca "a mais recente".
"""

import pytest

from cogno_praxis.bookkeeper.server import build_server
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore

EU = "emp-1"


def _svc() -> BookkeeperService:
    return BookkeeperService(InMemoryBookkeeperStore())


def _blocks(call):
    return call[0] if isinstance(call, tuple) else call


def _text(call) -> str:
    return "\n".join(b.text for b in _blocks(call) if getattr(b, "type", None) == "text")


def _confirm(call) -> dict:
    """O que a proposta pede de volta — do ``_meta``, que é o único sítio onde existe."""
    for b in _blocks(call):
        meta = getattr(b, "meta", None) or getattr(b, "_meta", None) or {}
        args = meta.get("cogno-mcp/confirm_arguments")
        if args:
            return dict(args)
    return {}


async def _propor(mcp, query):
    return await mcp.call_tool("remove_by_search", {"query": query, "identity_id": EU})


pytestmark = pytest.mark.asyncio


async def test_a_proposta_nomeia_data_descricao_e_valor():
    """O gémeo do que FICA. Uma proposta tem de ser verificável pelo contacto."""
    svc = _svc()
    svc.add_outcome("material de escritório", "45,00", EU, tx_date="2026-09-08")
    proposta = _text(await _propor(build_server(svc), "material"))

    assert "material de escritório" in proposta          # descrição
    assert "45,00" in proposta                           # valor, na gramática do contacto
    assert "2026-09-08" in proposta                      # data
    assert "NOT REMOVED" in proposta                     # e que nada foi apagado


async def test_duas_despesas_do_MESMO_valor_ficam_distinguiveis():
    """O gémeo que o «esta ação — 45.00» reprova: com duas de 45, qual é?

    A proposta nomeia a linha seleccionada E a irmã que a mesma busca apanhou, cada uma com a
    sua data e a sua descrição. É esta linha que desaparece quando a pergunta é montada a
    partir dos argumentos da chamada em vez do que a ferramenta leu.
    """
    svc = _svc()
    svc.add_outcome("almoço com cliente", "45,00", EU, tx_date="2026-09-07")
    svc.add_outcome("material de escritório", "45,00", EU, tx_date="2026-09-08")
    proposta = _text(await _propor(build_server(svc), "45"))

    assert "almoço com cliente" in proposta and "material de escritório" in proposta
    assert "2026-09-07" in proposta and "2026-09-08" in proposta
    assert "also match" in proposta                      # a ambiguidade é DITA, não escondida


async def test_o_id_que_COMITA_nao_esta_no_texto():
    """O gémeo do que SAI — e a mutação deste PR é repô-lo."""
    svc = _svc()
    svc.add_outcome("material de escritório", "45,00", EU, tx_date="2026-09-08")
    call = await _propor(build_server(svc), "material")

    tx_id = _confirm(call)["confirm_tx_id"]
    assert tx_id, "a proposta tem de pedir alguma coisa de volta"
    assert tx_id not in _text(call), "o id que comita foi impresso — é uma sugestão, não um segredo"
    assert "confirm_tx_id" not in _text(call), "o texto nomeia o argumento e convida a cópia"


async def test_nem_com_varias_irmas_o_id_escapa_para_o_texto():
    """O ramo com `others` renderiza mais linhas — nenhuma delas pode trazer um id."""
    svc = _svc()
    for dia, desc in (("2026-09-06", "internet janeiro"), ("2026-09-07", "internet fevereiro"),
                      ("2026-09-08", "internet março")):
        svc.add_outcome(desc, "149,00", EU, tx_date=dia)
    call = await _propor(build_server(svc), "internet")
    texto = _text(call)

    assert "internet janeiro" in texto and "internet fevereiro" in texto
    assert "confirm_tx_id" not in texto
    for linha in svc.get_summary(EU, "ADMIN")["outcomes"]:
        assert linha["tx_id"] not in texto


async def test_a_volta_pelo_CANAL_remove_exactamente_a_linha_proposta():
    """E o fluxo fecha: o que o `_meta` trouxe comita a linha que foi proposta, e só ela."""
    svc = _svc()
    svc.add_outcome("almoço com cliente", "45,00", EU, tx_date="2026-09-07")
    svc.add_outcome("material de escritório", "45,00", EU, tx_date="2026-09-08")
    mcp = build_server(svc)

    call = await _propor(mcp, "45")
    proposta, confirm = _text(call), _confirm(call)
    assert svc.get_summary(EU, "ADMIN")["outcome_count"] == 2      # propor não apaga

    feito = _text(await mcp.call_tool("remove_by_search",
                                      {"query": "45", "identity_id": EU, **confirm}))
    assert feito.startswith("Removed: ")
    restantes = svc.get_summary(EU, "ADMIN")["outcomes"]
    assert len(restantes) == 1
    # a que ficou é a que a proposta NÃO seleccionou — a selecção foi a primeira linha do texto
    assert restantes[0]["description"] not in proposta.splitlines()[1]


async def test_o_texto_manda_NAO_chamar_outra_vez():
    """A instrução que substituiu «call this again with confirm_tx_id=…».

    Sem ela o modelo fica com um texto que descreve uma segunda chamada e nenhum id para a
    fazer — que é a pior das duas leituras: tenta na mesma, e inventa o argumento."""
    svc = _svc()
    svc.add_outcome("material de escritório", "45,00", EU, tx_date="2026-09-08")
    proposta = _text(await _propor(build_server(svc), "material"))

    assert "Do NOT call remove_by_search again yourself" in proposta
    assert "call remove_by_search again with" not in proposta
