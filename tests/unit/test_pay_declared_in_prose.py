"""The pay figures a tenant wrote in PROSE — recognised, named beside the key, never read as a number.

Measured 2026-09-22 on six live turns of one tenant (``turns.id`` 1963–1968; no name, id or
address from them appears here). The professor asked what he would earn; ``estimate_professor_pay``
was offered, chosen and executed, ``ok=True``, and answered "NOT CONFIGURED: PAY_RATE_PER_HOUR,
COLUMN_HOURS are missing from the persona rules". The persona rules, meanwhile, said — in
Portuguese prose, under a heading about remuneration — exactly the figures the estimate needs.
Both were true at once: ``_find`` reads ``KEY: value`` lines and returns the default in silence,
so the same truth in two grammars counted in one and told nobody. Two tests across two repos
FIXED that refusal as the correct answer; they now tell "nothing declared" from "declared in
prose", and this file holds the detector that makes the difference sayable.

**Everything here is synthetic.** The rules block below is the tenant's own wording with every
name of a person or institution removed; the figures are kept because they ARE the test.

What is pinned, in one line each:

* the tenant's block yields one hint per key, with the sentence that produced it;
* a DECLARED key silences its prose (documentation beside configuration is not a defect);
* the detector is conservative — a workload in a course list, a clinic's price, an unrelated
  "2 horas por semana" produce nothing;
* the config refuses NAMING each sentence and its key; the warning is logged ONCE per
  configuration per process and carries a bounded excerpt, never a line of free text;
* an OPTIONAL key in prose refuses too, for the reason an unreadable band does.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorConfigError,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ProseHint,
    find_pay_in_prose,
    pay_refusal,
)
from cogno_praxis.coordinator import config as config_module

AA = "AAAAAAAAAAAAAAAAAAAAAAAA"
ME = "Prof Alfa"

_BASE = f"""SPREADSHEETS:
Turma AA_01 = {AA}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:E110"
TAB_PROFESSORS: "Informacoes Adicionais"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
"""

#: The tenant's rules as they stand, names removed. The last line is a CONTROL: a workload in
#: the course list ("(4h)", "(16h)") is not hours per class and must produce no hint.
TENANT_RULES_IN_PROSE = """# Valores Financeiros (Caso haja perguntas sobre NF e remuneração)
 - Aula - R$ 120,00 por hora, sendo o mínimo 4 horas por aula.
 - Financeiro cálculo = 120,00 * quantidade de horas em cada disciplina (mínimo 4 horas) + Bônus
 - Ibope > 80% e <89%: Adicional de R$ 30,00 por hora
 - Ibope > 90%: Adicional de R$ 40,00 por hora
 - O ibope ter sido respondido por pelo menos 30% da turma
A carga horária de cada disciplina está na grade curricular: Workshop de Abertura (4h),
Fundamentals of Data Engineering (16h).
"""

_ALL_UNDECLARED = {"PAY_RATE_PER_HOUR": False, "HOURS_PER_CLASS": False,
                   "IBOPE_BONUS": False, "IBOPE_MIN_RESPONSE_PCT": False}


def _svc(rules: str) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(AA, "Secretaria", [["Data", "Dia", "Professor", "Disciplina", "Sala"],
                                 ["05/09/2026", "Sab", ME, "Bancos NoSQL", "Sala Verde"],
                                 ["12/09/2026", "Sab", ME, "Bancos NoSQL", "Sala Verde"]])
    store.put(AA, "Informacoes Adicionais", [["Disciplina", "Total de Horas"], ["Bancos NoSQL", "16"]])
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: date(2026, 9, 1))


# ── the tenant's own block, key by key ────────────────────────────────────────────────
def test_the_tenants_rules_in_prose_yield_one_hint_per_key_with_the_sentence_that_produced_it():
    hints = find_pay_in_prose(TENANT_RULES_IN_PROSE, declared=_ALL_UNDECLARED)
    assert hints == (
        ProseHint("PAY_RATE_PER_HOUR", ("R$ 120,00 por hora",)),
        ProseHint("HOURS_PER_CLASS", ("4 horas por aula",)),
        ProseHint("IBOPE_BONUS", ("Adicional de R$ 30,00 por hora", "Adicional de R$ 40,00 por hora")),
        ProseHint("IBOPE_MIN_RESPONSE_PCT", ("respondido por pelo menos 30%",)),
    )


def test_a_workload_in_the_course_list_is_NOT_hours_per_class():
    """"Workshop de Abertura (4h)" is a discipline's total workload — the very figure the old
    semantics multiplied by the classes. Reading it as HOURS_PER_CLASS would put the defect back
    one layer up, as a hint."""
    hints = find_pay_in_prose("Workshop de Abertura (4h), Fundamentals of Data Engineering (16h).",
                              declared=_ALL_UNDECLARED)
    assert hints == ()


def test_a_declared_key_silences_its_prose():
    """Prose beside a declared key is documentation, and this is not a linter: the rate line is
    declared, so only the three OTHER keys are reported, and the bonus lines — which also say
    "R$ … por hora" — are never mistaken for a second rate."""
    hints = find_pay_in_prose(TENANT_RULES_IN_PROSE,
                              declared=dict(_ALL_UNDECLARED, PAY_RATE_PER_HOUR=True))
    assert [h.key for h in hints] == ["HOURS_PER_CLASS", "IBOPE_BONUS", "IBOPE_MIN_RESPONSE_PCT"]
    assert find_pay_in_prose(TENANT_RULES_IN_PROSE,
                             declared={k: True for k in _ALL_UNDECLARED}) == ()


@pytest.mark.parametrize("text,expected", [
    # the rate, in the ways a coordinator writes it
    ("Aula: R$ 120,00 por hora", [("PAY_RATE_PER_HOUR", "R$ 120,00 por hora")]),
    ("Pagamos R$120 a hora", [("PAY_RATE_PER_HOUR", "R$120 a hora")]),
    ("Valor: R$ 1.250,50/h", [("PAY_RATE_PER_HOUR", "R$ 1.250,50/h")]),
    # hours per class
    ("cada aula tem 4 horas", []),                          # no "por/cada aula" — not claimed
    ("mínimo de 4 horas por aula", [("HOURS_PER_CLASS", "4 horas por aula")]),
    ("cada aula de 3 horas", [("HOURS_PER_CLASS", "aula de 3 horas")]),
    ("aula de 4h", [("HOURS_PER_CLASS", "aula de 4h")]),
    # the bonus is decided by the LINE, not by the figure
    ("Bônus: R$ 30,00 por hora acima de 80%", [("IBOPE_BONUS", "R$ 30,00 por hora")]),
    ("Ibope > 90%: Adicional de R$ 40,00 por hora", [("IBOPE_BONUS", "Adicional de R$ 40,00 por hora")]),
    # the response-rate condition
    ("respondido por no mínimo 25% da turma", [("IBOPE_MIN_RESPONSE_PCT", "respondido por no mínimo 25%")]),
    # conservative: none of these is a pay figure
    ("A consulta particular custa R$ 280 e o retorno é gratuito.", []),
    ("Atendemos 2 horas por semana.", []),
    ("PAY_RATE_PER_HOUR: 120,00", []),                      # the grammar that IS read
    ("Ibope acima de 80% dá bônus", []),                    # a bonus with no figure names nothing
    ("", []),
])
def test_the_detector_table(text, expected):
    hints = find_pay_in_prose(text, declared=_ALL_UNDECLARED)
    assert [(h.key, e) for h in hints for e in h.excerpts] == expected


def test_an_excerpt_is_bounded_and_never_a_line_of_free_text():
    """What travels into the message and the log is the matched figure with a few words around
    it — the patterns are anchored to a figure, and the cap is the belt to their braces."""
    line = "Aula - R$ 120,00 por hora, " + "x" * 200
    (hint,) = find_pay_in_prose(line, declared=_ALL_UNDECLARED)
    assert hint.excerpts == ("R$ 120,00 por hora",)
    assert all(len(e) <= config_module._EXCERPT_MAX for e in hint.excerpts)


# ── the config, the refusal and the warning ──────────────────────────────────────────
def test_the_config_reads_the_prose_off_the_rules_and_the_estimate_refuses_naming_each():
    cfg = CoordinatorConfig(_BASE + TENANT_RULES_IN_PROSE)
    assert cfg.pay_undeclared == ("PAY_RATE_PER_HOUR", "HOURS_PER_CLASS")
    assert [h.key for h in cfg.pay_in_prose] == [
        "PAY_RATE_PER_HOUR", "HOURS_PER_CLASS", "IBOPE_BONUS", "IBOPE_MIN_RESPONSE_PCT"]
    with pytest.raises(CoordinatorConfigError) as exc:
        _svc(_BASE + TENANT_RULES_IN_PROSE).estimate_professor_pay(identity_label=ME)
    msg = str(exc.value)
    assert msg.startswith("This institution has not configured the pay figures: "
                          "PAY_RATE_PER_HOUR, HOURS_PER_CLASS are missing")
    assert 'found "R$ 120,00 por hora" in the rules, but PAY_RATE_PER_HOUR is not declared' in msg
    assert 'found "4 horas por aula" in the rules, but HOURS_PER_CLASS is not declared' in msg
    assert ('found "Adicional de R$ 30,00 por hora", "Adicional de R$ 40,00 por hora" in the '
            "rules, but IBOPE_BONUS is not declared") in msg
    assert 'found "respondido por pelo menos 30%" in the rules, but IBOPE_MIN_RESPONSE_PCT' in msg
    assert "KEY: value" in msg
    assert "R$ 960" not in msg and "R$ 3.840" not in msg  # named, never computed


def test_the_refusal_reaches_the_model_as_NOT_CONFIGURED_with_the_prose_named():
    from cogno_praxis.coordinator.server import build_server
    tools = build_server(_svc(_BASE + TENANT_RULES_IN_PROSE))._tool_manager._tools
    out = tools["estimate_professor_pay"].fn(identity_label=ME)
    assert out.startswith("NOT CONFIGURED:")
    assert 'found "R$ 120,00 por hora" in the rules, but PAY_RATE_PER_HOUR is not declared' in out
    assert "ERROR" not in out


def test_the_warning_is_logged_ONCE_per_configuration_and_carries_only_the_excerpts(
        caplog, monkeypatch):
    monkeypatch.setattr(config_module, "_PROSE_WARNED", set())
    with caplog.at_level(logging.WARNING, logger="cogno_praxis.coordinator.config"):
        CoordinatorConfig(_BASE + TENANT_RULES_IN_PROSE)
        CoordinatorConfig(_BASE + TENANT_RULES_IN_PROSE)      # the same configuration again
        CoordinatorConfig(_BASE + TENANT_RULES_IN_PROSE + "PAY_RATE_PER_HOUR: 120,00\n")
        CoordinatorConfig(_BASE)                               # nothing in prose → no warning
    records = [r for r in caplog.records if "PROSE" in r.getMessage()]
    assert len(records) == 2, [r.getMessage() for r in records]
    first = records[0].getMessage()
    assert "R$ 120,00 por hora" in first and "PAY_RATE_PER_HOUR" in first
    assert "NF e remuneração" not in first                   # the heading's free text stays out
    assert "Workshop de Abertura" not in first
    assert "PAY_RATE_PER_HOUR" not in records[1].getMessage()  # the declared key is not warned


def test_an_OPTIONAL_key_in_prose_refuses_too_for_the_reason_an_unreadable_band_does():
    """Rate and hours declared; the bonus bands only described. "This tenant declares no bonus"
    over rules that describe one pays less with the very sentence a tenant with no bonus
    scheme legitimately gets — so it is refused and named, like a band the parser cannot read.
    Declaring the key silences the prose and the estimate goes through."""
    declared = _BASE + "HOURS_PER_CLASS: 4\nPAY_RATE_PER_HOUR: 120,00\n"
    prose = declared + (" - Ibope > 80% e <89%: Adicional de R$ 30,00 por hora\n"
                        " - Ibope > 90%: Adicional de R$ 40,00 por hora\n")
    cfg = CoordinatorConfig(prose)
    assert cfg.pay_undeclared == ()
    assert [h.key for h in cfg.pay_in_prose] == ["IBOPE_BONUS"]
    with pytest.raises(CoordinatorConfigError) as exc:
        _svc(prose).estimate_professor_pay(identity_label=ME)
    msg = str(exc.value)
    assert "has not configured" not in msg               # nothing REQUIRED is missing
    assert 'found "Adicional de R$ 30,00 por hora", "Adicional de R$ 40,00 por hora"' in msg
    assert "IBOPE_BONUS is not declared" in msg
    # the twin: the same prose beside a DECLARED band is documentation, and the estimate runs
    est = _svc(prose + "IBOPE_BONUS: 80-89=30; 90+=40\n").estimate_professor_pay(identity_label=ME)
    assert est.base == pytest.approx(960.0)
    assert [t.per_hour for t in est.tiers] == [30.0, 40.0]


def test_pay_refusal_has_three_shapes_and_the_bare_one_is_unchanged():
    assert pay_refusal(("PAY_RATE_PER_HOUR",), ()) == (
        "This institution has not configured the pay figures: PAY_RATE_PER_HOUR is missing from "
        "the persona rules. Nothing can be estimated without it, and nothing here will be assumed.")
    both = pay_refusal(("PAY_RATE_PER_HOUR",), (ProseHint("PAY_RATE_PER_HOUR", ("R$ 120,00 por hora",)),))
    assert both.startswith("This institution has not configured the pay figures")
    assert "The rules DO describe them in prose" in both
    only = pay_refusal((), (ProseHint("IBOPE_BONUS", ("Adicional de R$ 30,00 por hora",)),))
    assert only.startswith("The rules DO describe pay figures in prose")
    assert "has not configured" not in only
    with pytest.raises(AssertionError):
        pay_refusal((), ())                              # nothing to refuse with
