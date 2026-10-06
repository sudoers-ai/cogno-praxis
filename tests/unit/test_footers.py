"""VQD-2(a) — the ``NO SUCH DISCIPLINE`` list is a CLOSED alphabet the host can read back.

The host's «Não encontrei X. Você quis dizer: A / B?» names only disciplines this list holds.
The list was joined with ``", "``, so a name with a comma of its own came back as several names
that are on no sheet. Every name is now a JSON literal and :func:`parse_unmatched_discipline` is
the one reader. Invented names throughout.
"""

from __future__ import annotations

import json

import pytest

from cogno_praxis.coordinator import (NO_SUCH_DISCIPLINE, parse_unmatched_discipline,
                                      unmatched_discipline_line)
from tests.unit.test_coordinator_unmatched_discipline import PROGRAMA, _tool

COMMA = "Ética, Política e Sociedade"
QUOTED = 'Seminário "Dados" \\ Avançado'


def _old_line(asked: str, known: "list[str]") -> str:
    """The rendering before this change, byte for byte (praxis main da698cd)."""
    joined = ", ".join(known) or "(none in this schedule)"
    return (f'NO SUCH DISCIPLINE: "{asked}" does not match any discipline '
            f"in this schedule — it may be the name of a programme or course, not of a "
            f"discipline — so the list above is the upcoming classes WITHOUT that filter. The "
            f"disciplines here are: {joined}. If the user meant one of them, call again with "
            f"`discipline` set to it.")


@pytest.mark.parametrize("known", [
    ["Bancos NoSQL", "Spark Distribuído"],
    [COMMA, "Bancos NoSQL"],
    [QUOTED],
    ["Só uma"],
    [],
])
def test_o_rodape_le_se_de_volta_exactamente_como_foi_escrito(known):
    line = unmatched_discipline_line(PROGRAMA, known)
    assert parse_unmatched_discipline("08/09 · DE_09 · Bancos NoSQL\n" + line) == (
        PROGRAMA, tuple(known))


def test_gemeo_a_virgula_dentro_do_nome_partia_o_nome_em_tres():
    """The broken world: the old line, split the only way a comma list can be, gives names that
    are on no sheet. The new line gives the two names back."""
    old = _old_line(PROGRAMA, [COMMA, "Bancos NoSQL"])
    split = old.split("The disciplines here are: ")[1].split(". If the user")[0].split(", ")
    assert split == ["Ética", "Política e Sociedade", "Bancos NoSQL"]      # 2 names not on a sheet
    assert parse_unmatched_discipline(old) is None, "o leitor não aceita a forma ambígua"
    assert parse_unmatched_discipline(unmatched_discipline_line(PROGRAMA, [COMMA, "Bancos NoSQL"]))[1] \
        == (COMMA, "Bancos NoSQL")


def test_controlo_um_nome_simples_tem_os_mesmos_bytes_de_hoje_no_valor_pedido():
    """The asked value and every plain name read as before — only the list gained its quotes."""
    new = unmatched_discipline_line(PROGRAMA, ["Bancos NoSQL"])
    old = _old_line(PROGRAMA, ["Bancos NoSQL"])
    assert new == old.replace("are: Bancos NoSQL.", 'are: "Bancos NoSQL".')
    assert f'{NO_SUCH_DISCIPLINE}: "{PROGRAMA}"' in new


def test_a_ferramenta_escreve_o_rodape_que_o_leitor_le():
    """Through the real tool: the footer parses, and every name is a JSON literal."""
    out = _tool(discipline=PROGRAMA)
    asked, known = parse_unmatched_discipline(out)
    assert asked == PROGRAMA and known == ("Bancos NoSQL", "Spark Distribuído")
    for k in known:
        assert json.dumps(k, ensure_ascii=False) in out


@pytest.mark.parametrize("text", [None, 3, "", "No classes found.",
                                  "NO SUCH DISCIPLINE: but not the line",
                                  'NO SUCH DISCIPLINE: "x" does not match any discipline in this '
                                  'schedule. The disciplines here are: "a", "b. If the user meant'])
def test_o_que_nao_e_o_rodape_e_none(text):
    assert parse_unmatched_discipline(text) is None
