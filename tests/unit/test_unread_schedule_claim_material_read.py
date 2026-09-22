"""`unread_schedule_claim` did not know `consult_material` — a read that held the answer.

Measured in the rehearsal tenant on 2026-09-22 (host ``ad3b3920``, n=2, the specimens
``P1_P11_S2-horas-derivacao`` and ``P1_P12_S2p-carga-horaria-total``): a reply grounded in a
``consult_material`` read with ``ok=True`` — the tenant's REGISTERED timetable and syllabus —
was rewritten 2/2 by rule 6, which admitted only ``list_appointments`` / ``check_availability``
as a read. The trigger both times was the courtesy tail "ajuda com agendamentos"
(``agendament`` in the occupancy pattern); the cost was a repair re-step per turn, and in the
re-step the executor called a ``list_appointments`` nobody asked for.

The ruler is the judge's — THE VALUE, NOT THE SOURCE. A read that is not the scheduler's own
earns the exemption only when its output HOLDS a schedule figure the reply states. By name
alone it would launder any figure the model invented over an unrelated lookup (twin 3); and
the scheduler's own listing keeps grounding by KIND, as it always has (twin 4).

The tool outputs below carry the specimens' VALUES in the specimens' SHAPE (the
``consult_material`` header, the timetable and syllabus sections) and no tenant or person.
"""

from __future__ import annotations

import pytest

from cogno_praxis.grounding import ToolCall
from cogno_praxis.scheduler.grounding import UNREAD_SCHEDULE_MSG, ground_reply


def _material(result: str) -> ToolCall:
    return ToolCall(tool="consult_material", ok=True, result=result)


def _list(result: str) -> ToolCall:
    return ToolCall(tool="list_appointments", ok=True, result=result)


# The timetable section the P11 read returned: the class runs 19h00–22h30 and 08h00–11h30.
_GRADE = (
    "Material registado sobre 'Data Modeling':\n\n"
    "## Grade de horários — turmas do semestre\n"
    "Horários das aulas presenciais e online de cada disciplina, por turma.\n\n"
    "### Turma TN-01 (noite)\n\n"
    "- **Modelagem de Dados** — quarta-feira, 19h00 às 22h30, sala B-204 (presencial).\n"
    "- **Redes de Computadores** — segunda-feira, 19h00 às 22h30, sala B-207 (presencial).\n\n"
    "### Turma TM-02 (manhã)\n\n"
    "- **Modelagem de Dados** — terça-feira, 08h00 às 11h30, sala A-102 (presencial).\n")
# The syllabus section the P12 read returned: the workload is written "(60h)".
_EMENTA = (
    "Material registado sobre 'Data Modeling — total workload':\n\n"
    "## Ementas das disciplinas\n"
    "Conteúdo programático de cada disciplina, com carga horária e avaliação.\n\n"
    "### Modelagem de Dados (60h)\n\n"
    "Modelo entidade-relacionamento; normalização até a terceira forma normal.\n")
# The courtesy tail both specimens ended with — it is what the occupancy pattern matched.
_TAIL = "\n\nSe precisar de mais informações ou ajuda com agendamentos, é só avisar! 😊"

# P11: the duration is DERIVED from the read (22h30 − 19h00) and the times are repeated from it.
_P11 = ("Modelagem de Dados tem uma duração de **3 horas e 30 minutos** por aula. As aulas "
        "presenciais acontecem nos seguintes horários:\n\n"
        "- **Turma TN-01 (noite):** quarta-feira, das 19h00 às 22h30\n"
        "- **Turma TM-02 (manhã):** terça-feira, das 08h00 às 11h30" + _TAIL)
# P12: "60 horas" — the read spells it "(60h)".
_P12 = "A carga horária total de **Modelagem de Dados** é de **60 horas**." + _TAIL


# ── twin 1: the value the reply states IS in the material read → no repair ───────────
@pytest.mark.parametrize("reply, material", [
    pytest.param(_P11, _GRADE, id="P11-times-and-derived-duration"),
    pytest.param(_P12, _EMENTA, id="P12-60-horas-spelled-60h"),
])
def test_a_schedule_figure_the_material_read_holds_grounds_the_claim(reply, material):
    v = ground_reply(reply, tools=[_material(material)], had_executor=True, is_read_query=True)
    assert v is None, v.rule


# ── twin 2: the same claim with no read at all → the repair stands ────────────────────
@pytest.mark.parametrize("reply", [
    pytest.param(_P11, id="P11"),
    pytest.param(_P12, id="P12"),
])
def test_the_same_claim_with_no_read_is_still_repaired(reply):
    """The control that keeps twin 1 from being vacuous: the SAME replies do trip the rule,
    so ``None`` above is the read earning the exemption, not the detector missing them."""
    v = ground_reply(reply, tools=(), had_executor=True, is_read_query=True)
    assert v is not None and v.rule == "unread_schedule_claim"
    assert v.repairable and v.critique and v.message == UNREAD_SCHEDULE_MSG


# ── twin 3: a material read in hand whose output does NOT hold the value → fabrication ─
@pytest.mark.parametrize("reply", [
    # a time and a duration the timetable never states
    pytest.param("A aula de Modelagem de Dados é na quarta-feira às 14h00 e dura 2 horas."
                 + _TAIL, id="figure-absent-from-the-read"),
    # "30" is a digit run inside the read's "22h30"; "2 horas e 30 minutos" is not in it
    pytest.param("Cada aula de Modelagem de Dados dura 2 horas e 30 minutos." + _TAIL,
                 id="digit-run-inside-another-figure-is-not-the-value"),
    # a claim with no figure at all: there is no value the read could hold
    pytest.param("Você já tem compromissos marcados nessa quarta-feira." + _TAIL,
                 id="no-figure-claimed"),
])
def test_a_figure_the_material_read_does_not_hold_is_still_repaired(reply):
    v = ground_reply(reply, tools=[_material(_GRADE)], had_executor=True, is_read_query=True)
    assert v is not None and v.rule == "unread_schedule_claim", reply


# ── twin 4: the scheduler's OWN listing keeps grounding by kind, as today ─────────────
def test_the_schedulers_own_listing_still_grounds_by_kind():
    """The figure condition is the price of admission for a read that is NOT the scheduler's.
    ``list_appointments`` is, and it grounds the claim as it always did — even when the reply
    states a time the listing does not spell (the per-figure guarantee is the judge's)."""
    listing = _list("abc: [BLOQUEIO: Bloqueado] on 2026-07-16 at 09:00 [CONFIRMED]")
    reply = "Você tem os dias 16 e 17 bloqueados na sua agenda, das 14h00 às 18h00."
    assert ground_reply(reply, tools=[listing], had_executor=True, is_read_query=True) is None
    # …and beside a material read that holds nothing of the reply, the listing still decides.
    both = [listing, _material(_EMENTA)]
    assert ground_reply(reply, tools=both, had_executor=True, is_read_query=True) is None


# ── the ruler itself: a figure compares by VALUE, never by spelling ───────────────────
def test_schedule_figures_compare_by_value_not_by_spelling():
    from cogno_praxis.scheduler.grounding import schedule_figures

    assert schedule_figures("60 horas") == schedule_figures("(60h)") == {"60:00"}
    assert (schedule_figures("3 horas e 30 minutos") == schedule_figures("3h30")
            == schedule_figures("3.5 hours") == schedule_figures("3 hours and 30 minutes")
            == {"3:30"})
    assert schedule_figures("quarta-feira, 19h00 às 22h30") == {"19:00", "22:30"}
    assert schedule_figures("7pm") == schedule_figures("19:00") == {"19:00"}
    assert schedule_figures("às 11h") == {"11:00"}
    # a digit run is not a figure: the "30" of "22h30" is not "30 minutos", nor "3h30"
    assert schedule_figures("22h30") == {"22:30"}
    assert not (schedule_figures("22h30") & schedule_figures("30 minutos"))
    assert not (schedule_figures("22h30") & schedule_figures("3 horas e 30 minutos"))
    # a number with no time unit is nothing
    assert schedule_figures("sala B-204, dias 16 e 17, R$ 1.234,56, 60%") == set()
