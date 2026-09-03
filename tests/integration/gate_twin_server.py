"""O servidor GÉMEO: a MESMA função, exposta duas vezes, com UMA diferença — a anotação.

Existe para que a pre-empção do portão B sobre o portão C seja MEDIDA e não recordada. A
alternativa era descrever em prosa o que a anotação de ontem fazia, e uma prosa não fica
vermelha no dia em que deixa de ser verdade.

``remove_by_search``  o tool tal como é servido hoje: mutante, SEM ``destructiveHint``.
``purge_by_search``   o MESMO objecto-função — obtido do gestor de tools, não copiado — sob
                      ``destructiveHint=True``, que é a anotação que este tool tinha até #90.

Copiar o corpo teria sido a forma óbvia e teria destruído a experiência: duas cópias divergem, e
no dia em que divergissem o teste passaria a comparar duas coisas diferentes enquanto continuava
a chamar-se "gémeo". Aqui as duas entradas partilham a função e o serviço; a única variável é a
anotação, que é exactamente a variável em estudo.

Lançado por ``test_o_portao_C_dispara_sobre_a_cadeia.py`` sobre stdio. Cada processo nasce com o
seu próprio livro em memória, portanto um teste que apaga uma linha não decide o que o vizinho mede.
"""

from mcp.types import ToolAnnotations

from cogno_praxis.bookkeeper.server import build_server
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore

EU = "emp-1"

svc = BookkeeperService(InMemoryBookkeeperStore())
# Três linhas que a MESMA busca de substring apanha — é sobre elas que a pergunta fundamentada
# tem alguma coisa para dizer que o nome do tool nunca poderia dizer.
svc.add_outcome("internet janeiro", 100, EU, tx_date="2026-01-10")
svc.add_outcome("internet fevereiro", 110, EU, tx_date="2026-02-10")
svc.add_outcome("internet marco", 149.90, EU, tx_date="2026-03-10")

mcp = build_server(svc)

# O MESMO objecto-função que o servidor real regista, re-registado sob o outro nome e a outra
# anotação. `_tool_manager` é privado; usá-lo é deliberado e é o que torna o gémeo um gémeo.
_shipped = mcp._tool_manager.get_tool("remove_by_search").fn
mcp.add_tool(
    _shipped,
    name="purge_by_search",
    description="Same function as remove_by_search; the server declares the NAME destructive.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)


if __name__ == "__main__":
    mcp.run()
