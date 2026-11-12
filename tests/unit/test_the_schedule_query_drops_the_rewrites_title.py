"""An oversight ``professor`` query drops the rewrite's TITLE before it matches a name.

Measured 2026-11-12 on the ``email_model_bench`` world «Escola Bench» (the cronograma e-mail,
2 of 12 runs failed BEFORE any e-mail): «manda por e-mail o cronograma de aulas de novembro para
a professora Brízida Lameiras» read the schedule back EMPTY. The EGO fills ``professor`` from the
NOUMENO's canonical-English rewrite, which writes the recipient «Professor <name>» — English,
and MASCULINE whatever the Portuguese said. The title became the first token, and neither the
folded substring nor :func:`_is_abbreviation_of` (it pins the first token) could see past it, so
a named teacher's own November classes came back as nothing.

**The two failing runs wore two different sentences, and this twin proves they are ONE read.**
Run 1 voiced «Não encontrei aulas … para Professor Brízida Lameiras» (no classes at all); run 3
voiced «Não encontrei aulas em novembro de 2026 para a Professora Brízida Lameiras» (as if only
the month came up empty). The tool arguments were not logged, so the second looked like it might
be a month miss. It is not: the professor filter runs BEFORE the month one, so a title that
fails the name match empties the read whatever the month — the «novembro» in the voice is a
paraphrase of the same empty list. Both titles, with November named, return the SAME four
classes once the title is dropped, and the bare name (the control) is identical: the title is the
whole delta. Red on the base, green on the fix.

Names invented.
"""
from __future__ import annotations

from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ReadReport,
)

_SID = "C" * 24
_RULES = (f"SPREADSHEETS:\nTurma DE_01 = {_SID}\n\nTAB_SCHEDULE: \"Secretaria\"\n"
          'RANGE_SCHEDULE: "A1:F110"\nCOLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\n'
          'COLUMN_SUBJECT: "Disciplina"\nCOLUMN_TIME: "Hora"\nHOURS_PER_CLASS: 4\n'
          "PAY_RATE_PER_HOUR: 120,00\n")

#: The recipient of the cronograma — a name the sheet carries BARE (no title), as a roster does.
_PROF = "Hortênsia Vexbraúne Quollim"
#: Another teacher on the same sheet, so the match is a match and not "the only row there is".
_OTHER = "Teodomiro Alvanel Prast"
_SHEET = [
    ["Data", "Dia", "Professor", "Disciplina", "Sala", "Hora"],
    ["27/10/2026", "Ter", _PROF, "Engenharia de Dados", "Azul", "19:00"],   # another month
    ["03/11/2026", "Ter", _PROF, "Engenharia de Dados", "Azul", "19:00"],
    ["05/11/2026", "Qui", _OTHER, "Banco de Dados", "Verde", "19:00"],      # another person
    ["10/11/2026", "Ter", _PROF, "Engenharia de Dados", "Azul", "19:00"],
    ["17/11/2026", "Ter", _PROF, "Visualização de Dados", "Azul", "19:00"],
    ["24/11/2026", "Ter", _PROF, "Visualização de Dados", "Azul", "19:00"],
]
#: Today is late October, so November is the month AHEAD (the horizon is not in play once a
#: month is named, but the fixture keeps «hoje» where the measured world had it).
_TODAY = date(2026, 10, 22)
#: The one answer the November query may list for _PROF.
_NOVEMBER = ["03/11/2026", "10/11/2026", "17/11/2026", "24/11/2026"]


def _svc() -> CoordinatorService:
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [list(r) for r in _SHEET])
    return CoordinatorService(store, cfg, today=lambda: _TODAY)


def _read(professor: str, month: str = "novembro") -> list[str]:
    """The EXACT dates the oversight tool reads for ``professor`` in ``month`` — the message the
    executor copies into the e-mail. A SUPERVISOR (oversight) names any teacher."""
    svc = _svc()
    rows = svc.get_professor_schedule(professor=professor, role="SUPERVISOR",
                                      identity_label="Coordenação Bench", month=month,
                                      report=ReadReport())
    return [e.date_str for e in rows]


def test_the_masculine_title_from_the_rewrite_reads_the_teachers_classes():
    # Run 1's shape: «Professor <name>» — the English, masculine title the rewrite emits.
    assert _read(f"Professor {_PROF}") == _NOVEMBER


def test_the_feminine_title_is_the_same_read_not_a_month_miss():
    # Run 3's shape: «Professora <name>», voiced «… em novembro de 2026 …». The month was never
    # the cause — the professor filter empties the read before the month filter is reached — so
    # this reads exactly what run 1's title reads, and what the bare name reads.
    assert _read(f"Professora {_PROF}") == _NOVEMBER
    assert _read(f"Professora {_PROF}") == _read(f"Professor {_PROF}") == _read(_PROF)


def test_the_bare_name_is_the_control_only_the_title_differed():
    # Without any title the read already worked: the delta these twins pin is the title alone.
    assert _read(_PROF) == _NOVEMBER


def test_a_title_only_query_still_designates_nobody():
    # Stripping must not empty the query into "everybody": a bare title names no teacher, so it
    # must not read the whole faculty (here, _OTHER's rows) back.
    assert _read("Professora", month="") == []


if __name__ == "__main__":  # pragma: no cover
    test_the_masculine_title_from_the_rewrite_reads_the_teachers_classes()
    test_the_feminine_title_is_the_same_read_not_a_month_miss()
    test_the_bare_name_is_the_control_only_the_title_differed()
    test_a_title_only_query_still_designates_nobody()
    print("ok")
