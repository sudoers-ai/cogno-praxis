"""The three-layer summary: the line limits are ENFORCED, the text is deterministic, and a field
nobody filled says so instead of being invented."""

from __future__ import annotations

import pytest

from cogno_praxis.admin.impact import Change, Classification, PathChange, classify
from cogno_praxis.admin.summary import (
    MAX_FILES_LISTED,
    MAX_LINE_CHARS,
    MAX_LINES,
    NOT_GIVEN,
    ChangeReport,
    render,
)

_FILES = (PathChange("cogno_praxis/scheduler/prompts/voice.txt", 4, 2),
          PathChange("tests/unit/test_scheduler_server.py", 10, 0))


def _report(**over) -> ChangeReport:
    base = dict(
        title="A voz da agenda confirma o horário por extenso",
        vertical="scheduler",
        classification=classify(Change(_FILES, kind="correction")),
        benefit="menos remarcações por mal-entendido de horário",
        impact="só a resposta final da SECRETARY muda",
        risk="baixo: o juiz continua a exigir o horário exato",
        reviewer_opinion="aprovado sem ressalvas",
        revert="reverter o commit; nenhum dado muda",
        files=_FILES,
        diff_summary="uma frase nova no voice.txt e um teste",
        tests="1 novo, 0 falhas",
        pr="#999",
    )
    base.update(over)
    return ChangeReport(**base)


def _within(summary) -> None:
    for layer in ("diretor", "gerencial", "tecnico"):
        lines = getattr(summary, layer)
        low, high = MAX_LINES[layer]
        assert low <= len(lines) <= high, (layer, len(lines))
        for line in lines:
            assert "\n" not in line and len(line) <= MAX_LINE_CHARS, (layer, line)


def test_the_limits_are_the_declared_ones():
    assert MAX_LINES["diretor"] == (2, 3)


def test_a_small_change_renders_within_the_limits():
    s = render(_report())
    _within(s)
    assert len(s.diretor) == 2
    assert s.diretor[0] == ("A voz da agenda confirma o horário por extenso — mudança pequena em "
                            "scheduler.")
    assert s.gerencial[0] == "Tamanho: pequena"
    assert s.gerencial[3] == "Parecer do revisor: aprovado sem ressalvas"
    assert s.tecnico[0] == "Arquivos: 2 (+14 -2)"
    assert s.tecnico[-1] == "PR: #999"


def test_a_large_change_says_it_waits_for_a_decision_and_why():
    s = render(_report(classification=classify(Change(
        (PathChange("cogno_praxis/scheduler/prompts/scope.txt", 1, 0),), kind="correction"))))
    _within(s)
    assert len(s.diretor) == 3 and s.diretor[2] == "Precisa da sua decisão antes de seguir."
    assert s.gerencial[0] == "Tamanho: grande (muda o escopo ou os limites)"


def test_an_improvement_says_why_it_is_large():
    s = render(_report(classification=classify(Change(_FILES, kind="improvement"))))
    assert s.gerencial[0] == "Tamanho: grande (não é correção: é melhoria ou evolução)"
    assert len(s.diretor) == 3


def test_the_layers_carry_their_labels():
    text = render(_report()).text()
    assert text.startswith("Diretor:\n- ")
    assert "\n\nGerencial:\n- " in text and "\n\nTécnico:\n- " in text


def test_the_text_is_deterministic():
    assert render(_report()).text() == render(_report()).text()
    assert render(_report()) == render(_report())


def test_a_long_field_is_cut_to_one_line():
    s = render(_report(title="palavra " * 100, risk="linha um\nlinha dois\n\n  três"))
    _within(s)
    assert s.diretor[0].endswith("…") and len(s.diretor[0]) == MAX_LINE_CHARS
    assert s.gerencial[2] == "Risco: linha um linha dois três"


@pytest.mark.parametrize("n", [MAX_FILES_LISTED, MAX_FILES_LISTED + 1, 50, 500])
def test_many_files_are_capped_and_the_rest_counted(n):
    files = tuple(PathChange(f"cogno_praxis/v{i}/service.py", 1, 1) for i in range(n))
    s = render(_report(files=files))
    _within(s)
    listed = [line for line in s.tecnico if line.startswith("cogno_praxis/v")]
    assert len(listed) == min(n, MAX_FILES_LISTED)
    if n > MAX_FILES_LISTED:
        assert f"… e mais {n - MAX_FILES_LISTED} arquivo(s)" in s.tecnico
    # the fixed lines survive the cap — the PR is never the line that falls off
    assert s.tecnico[-3].startswith("Resumo do diff:")
    assert s.tecnico[-2].startswith("Testes:") and s.tecnico[-1].startswith("PR:")


def test_nothing_given_is_said_never_invented():
    s = render(ChangeReport(title="x", vertical="bookkeeper",
                            classification=Classification("large", ("doubt: x",))))
    _within(s)
    assert s.diretor[1] == f"Ganho: {NOT_GIVEN}"
    assert s.gerencial[3] == f"Parecer do revisor: {NOT_GIVEN}"
    assert s.tecnico[0] == "Arquivos: 0"
    assert s.tecnico[-1] == f"PR: {NOT_GIVEN}"


def test_an_unknown_count_is_a_question_mark_not_a_zero():
    files = (PathChange("cogno_praxis/a.py", None, 2),)
    s = render(_report(files=files))
    assert s.tecnico[0] == "Arquivos: 1 (linhas: ?)"
    assert s.tecnico[1] == "cogno_praxis/a.py (+? -2)"
