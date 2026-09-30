"""M6-c — a ``discipline`` that names nothing in the schedule is DROPPED and SAID, never «No classes found».

The trace-2056 shape, with invented names: a professor asks for his classes «do MBA em Engenharia
de Dados», and the executor fills ``discipline`` with the PROGRAMME's name. No subject in his
schedule is called that, the fuzzy match drops every row, and the tool answered «No classes
found.» — a false sentence about a professor who has classes next week.

The fix follows the ``unmatched_turma`` precedent: ``report.unmatched_discipline`` records the
miss, ``report.known_disciplines`` the names his read DOES hold (scoped to what he may see), and
the list is his upcoming classes WITHOUT the discipline filter — the default window included,
because with the filter gone nothing names a lookup any more. A discipline that exists but not in
the month asked is not a miss; a caller that passes no ``report`` keeps today's empty list.
"""

from __future__ import annotations

from datetime import date

from cogno_praxis.coordinator import (CoordinatorConfig, CoordinatorService,
                                      InMemorySpreadsheetStore, ReadReport)
from tests.unit.test_coordinator_turma import RULES, _ID_A, _ID_B, _ID_C, _ID_D, _grid, _row
from tests.unit.test_coordinator_turma import _tool as _tool_as_supervisor

_TODAY = date(2026, 9, 6)
PROF = "Otávio Brandão"
PROGRAMA = "MBA em Engenharia de Dados"


def _service() -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(_ID_A, "Secretaria", _grid([_row("2026-09-10", "Bancos NoSQL", PROF),
                                          _row("2026-08-20", "Bancos NoSQL", PROF),   # past
                                          _row("2026-09-10", "Redes", "Ana")]))       # not his
    store.put(_ID_B, "Secretaria", _grid([_row("2026-09-17", "Spark Distribuído", PROF),
                                          _row("2026-11-19", "Spark Distribuído", PROF)]))  # far
    store.put(_ID_C, "Secretaria", _grid([_row("2026-09-12", "Livre", PROF)]))       # free slot
    store.put(_ID_D, "Secretaria", _grid([]))
    return CoordinatorService(store, CoordinatorConfig(RULES), today=lambda: _TODAY)


def _read(**kw):
    report = ReadReport()
    got = _service().get_professor_schedule(role="EMPLOYEE", identity_label=PROF,
                                            report=report, **kw)
    return got, report


def _tool(**kw) -> str:
    return _tool_as_supervisor(_service(), **{"role": "EMPLOYEE", "identity_label": PROF, **kw})


# ── o gémeo ──────────────────────────────────────────────────────────────────────────────

def test_gemeo_o_nome_do_PROGRAMA_devolve_as_proximas_aulas_e_diz_porque():
    """On praxis main 2d6f631 (measured): ``[]`` and «No classes found.»."""
    got, report = _read(discipline=PROGRAMA)
    assert [(e.when, e.subject) for e in got if not e.is_free_slot] == [
        (date(2026, 9, 10), "Bancos NoSQL"), (date(2026, 9, 17), "Spark Distribuído")]
    assert report.unmatched_discipline == PROGRAMA
    assert report.known_disciplines == ("Bancos NoSQL", "Spark Distribuído")
    assert "Redes" not in report.known_disciplines, "listou a disciplina de outro professor"
    assert report.beyond_horizon, "sem o filtro, a janela por omissão volta a valer"


def test_gemeo_a_resposta_da_ferramenta_nomeia_o_falhanco_e_as_disciplinas():
    out = _tool(discipline=PROGRAMA)
    assert "No classes found" not in out
    assert "NO SUCH DISCIPLINE" in out and f'"{PROGRAMA}"' in out
    assert "Bancos NoSQL" in out and "Spark Distribuído" in out
    assert "WITHOUT that filter" in out
    assert not out.startswith("ERROR")


# ── os controlos ─────────────────────────────────────────────────────────────────────────

def test_controlo_uma_disciplina_que_casa_continua_a_filtrar():
    got, report = _read(discipline="spark distribuido")
    assert {e.subject for e in got} == {"Spark Distribuído"}
    assert len(got) == 2, "uma disciplina nomeada continua a levantar a janela (é uma consulta)"
    assert report.unmatched_discipline == "" and report.known_disciplines == ()
    assert "NO SUCH DISCIPLINE" not in _tool(discipline="Bancos NoSQL")


def test_controlo_a_disciplina_que_existe_noutro_mes_nao_e_um_falhanco():
    got, report = _read(discipline="Spark", month="2026-10")
    assert got == [] and report.unmatched_discipline == ""
    assert "No classes found" in _tool(discipline="Spark", month="2026-10")


def test_controlo_sem_report_o_chamador_recebe_a_lista_vazia_de_hoje():
    """An unfiltered list nobody marks as unfiltered would be a wrong answer."""
    got = _service().get_professor_schedule(role="EMPLOYEE", identity_label=PROF,
                                            discipline=PROGRAMA)
    assert got == []
