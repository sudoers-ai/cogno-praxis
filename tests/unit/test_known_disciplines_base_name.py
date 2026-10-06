"""The ``NO SUCH DISCIPLINE`` list names each discipline ONCE — by its base name.

The shape of a real trace, with invented names: one professor, one discipline, three rows on the
sheet — the class itself, the class with « - Aula Adiada» appended, and its make-up with
« - reposição do dia 22/09». ``_known_disciplines`` listed the three cells as three disciplines,
and the host's «Você quis dizer: A / B / C?» (VQD-2(a)), which may only copy names from this
list, offered the SAME discipline three times.

The cut is a CLOSED list of status notes — the tenant's ``POSTPONED_LABELS`` (the comparison
``_is_postponed`` makes), the make-up note and the cancelled note — matched against the WHOLE
annotation. Any other spaced dash is part of a name: «Laboratório - Redes» is a discipline.
"""

from __future__ import annotations

from datetime import date

from cogno_praxis.coordinator import (CoordinatorConfig, CoordinatorService,
                                      InMemorySpreadsheetStore, ReadReport,
                                      parse_unmatched_discipline, unmatched_discipline_line)
from tests.unit.test_coordinator_turma import RULES, _ID_A, _ID_B, _grid, _row
from tests.unit.test_coordinator_turma import _tool as _tool_as_supervisor

_TODAY = date(2026, 9, 6)
PROF = "Otávio Brandão"
ASKED = "MBA em Engenharia de Dados"
BASE = "Arquitetura Lambda"


def _service(rows_a: "list[list[str]]", rows_b: "list[list[str]]" = (),  # type: ignore[assignment]
             rules: str = RULES) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(_ID_A, "Secretaria", _grid(list(rows_a)))
    store.put(_ID_B, "Secretaria", _grid(list(rows_b)))
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: _TODAY)


def _known(svc: CoordinatorService) -> "tuple[str, ...]":
    report = ReadReport()
    svc.get_professor_schedule(role="EMPLOYEE", identity_label=PROF, discipline=ASKED,
                               report=report)
    assert report.unmatched_discipline == ASKED, "the read must take the M6-c branch"
    return report.known_disciplines


def _footer(svc: CoordinatorService) -> str:
    out = _tool_as_supervisor(svc, role="EMPLOYEE", identity_label=PROF, discipline=ASKED)
    lines = [ln for ln in out.splitlines() if ln.startswith("NO SUCH DISCIPLINE")]
    assert len(lines) == 1, out
    return lines[0]


#: The trace's shape: the base row and two annotated rows of the SAME discipline.
_SHAPE = [_row("2026-09-10", f"{BASE} - Aula Adiada", PROF),
          _row("2026-09-17", BASE, PROF),
          _row("2026-09-24", f"{BASE} - reposição do dia 22/09", PROF)]


# ── o gémeo ──────────────────────────────────────────────────────────────────────────────

def test_gemeo_uma_disciplina_com_duas_linhas_anotadas_e_um_nome_so():
    """On praxis main ad8df30 (measured): the three cells, as three «disciplines»."""
    assert _known(_service(_SHAPE)) == (BASE,)


def test_gemeo_o_rodape_lista_o_nome_base_uma_vez_e_o_leitor_le_o():
    svc = _service(_SHAPE)
    line = _footer(svc)
    assert parse_unmatched_discipline(line) == (ASKED, (BASE,))
    assert line == unmatched_discipline_line(ASKED, [BASE]), \
        "the asked value and the rest of the footer are the line this module always wrote"
    assert "Aula Adiada" not in line and "reposição" not in line


def test_gemeo_a_nota_de_cancelamento_tambem_e_de_estado():
    rows = [_row("2026-09-10", BASE, PROF), _row("2026-09-17", f"{BASE} - Cancelada", PROF),
            _row("2026-09-24", f"{BASE} - aula cancelada", PROF),
            _row("2026-10-01", f"{BASE} - Reposição", PROF)]
    assert _known(_service(rows)) == (BASE,)


def test_gemeo_a_palavra_do_tenant_em_POSTPONED_LABELS_corta_como_no_pagamento():
    """Derived from the config, not copied: a tenant who declares its own postponed wording
    gets it read here exactly as ``_is_postponed`` reads it for the pay."""
    rules = RULES + 'POSTPONED_LABELS: "Transferida"\n'
    rows = [_row("2026-09-10", BASE, PROF), _row("2026-09-17", f"{BASE} - Transferida", PROF)]
    assert _known(_service(rows, rules=rules)) == (BASE,)
    assert _known(_service(rows)) == (BASE, f"{BASE} - Transferida"), \
        "control: without the declaration the word is not a status note"


def test_gemeo_um_nome_com_traco_proprio_perde_so_a_nota_de_estado():
    lab = "Laboratório - Redes"
    rows = [_row("2026-09-10", lab, PROF), _row("2026-09-17", f"{lab} - Aula adiada", PROF)]
    assert _known(_service(rows)) == (lab,), "the LAST spaced dash is the note's, not the name's"


def test_gemeo_duas_disciplinas_cada_uma_com_a_sua_nota_continuam_duas():
    rows = _SHAPE + [_row("2026-09-11", "Bancos NoSQL", PROF)]
    known = _known(_service(rows, [_row("2026-09-18", "Bancos NoSQL - Aula adiada", PROF)]))
    assert known == (BASE, "Bancos NoSQL")


# ── os controlos (verdes nos DOIS mundos) ────────────────────────────────────────────────

def test_controlo_um_traco_que_faz_parte_do_nome_fica_inteiro():
    rows = [_row("2026-09-10", "Laboratório - Redes", PROF),
            _row("2026-09-24", "Oficina - Reposição de Conteúdos", PROF),
            _row("2026-10-01", "Ética - Cancelamentos Contratuais", PROF)]
    assert _known(_service(rows)) == (
        "Ética - Cancelamentos Contratuais", "Laboratório - Redes",
        "Oficina - Reposição de Conteúdos"), \
        "a note is cut only when it is a status note, WHOLE"


def test_controlo_duas_disciplinas_distintas_continuam_duas():
    rows = [_row("2026-09-10", BASE, PROF), _row("2026-09-11", "Bancos NoSQL", PROF)]
    assert _known(_service(rows)) == (BASE, "Bancos NoSQL")
    assert parse_unmatched_discipline(_footer(_service(rows)))[1] == (BASE, "Bancos NoSQL")


def test_controlo_a_linha_adiada_continua_adiada_no_pagamento():
    """The refactor of ``_is_postponed`` moved no verdict: the annotated row is still put off,
    the make-up row is not, and a whole-cell label is still postponed."""
    svc = _service(_SHAPE)
    assert svc._is_postponed(f"{BASE} - Aula Adiada")
    assert svc._is_postponed("Aula adiada")
    assert not svc._is_postponed(f"{BASE} - reposição do dia 22/09")
    assert not svc._is_postponed(BASE)
