"""The professor's own pay: what the estimate may state, and what it must refuse to state.

Two live turns of one professor's own tenant, 2026-09-06, are the reason this exists. At
22:35:30Z he asked «como funciona a parte financeira. minhas aulas por exemplo, qto eu receberia
por mes?» and was answered "informações sobre remuneração e pagamentos estão fora do meu escopo";
at 22:39:07Z, «baseado nesse calculos, qual seria o q tenho a receber…» came back as "Desculpe,
mas não posso ajudar com questões financeiras." The two refusals came from DIFFERENT layers, and
that is why this change touches four prompts and not one: turn 67's trace carries
``superego.blocked=true`` with ``judge_attempts=0`` — the intake scope guard stopped it before
anything ran — while turn 65 was never blocked at all (``judge_rejected_all``,
``last_draft_voiced``): the executor read the schedule, drafted an honest answer, and the
persona's own "You do NOT ... handle finances" line plus the judge's out-of-scope clause turned
it into a refusal. Opening only the intake would have fixed one of the two.

Turn 65's draft is also the specification for the arithmetic. Left to itself the executor wrote
"the schedule read did not return those hour totals" and "I can't calculate a reliable monthly
total from the number of classes alone" — which is correct, and is the failure this closes: the
hours exist in the institution's own sheet and nothing was reading them.

**Everything below runs on a synthetic sheet.** No live spreadsheet id, no real professor, no
contact detail: the fixtures are two invented class groups and two invented names, and the
figures are round numbers chosen so a wrong multiplication is visible by eye.

What the tests are about, in one line each:

* the estimate exists and groups by class group and month (the two axes the answer promises);
* the month's pay is classes × HOURS_PER_CLASS × the rate — the tenant's own sentence, fixed
  2026-09-22: "na planilha tem a carga horária completa da disciplina, cada linha na planilha
  equivale a 4 horas". Two September classes × 4 h × R$ 120,00 = R$ 960,00; the discipline's
  workload (16 h) is CONTEXT and is never multiplied by the classes again (the old 3.840);
* an IBOPE result that was NOT found produces every declared hypothesis and chooses none;
* rules that declare no rate — or no hours per class — produce a refusal, never a figure, and
  never an inferred "4"; rules that DESCRIBE them in prose are refused NAMING the prose and the
  key (``test_pay_declared_in_prose.py`` has the detector; the twin beside "nada" is here);
* another professor's pay is refused to every role that is NOT the coordination — the victim
  of an opened scope; the coordination's own reach (by name, or everyone one block each,
  2026-09-23) is pinned in ``test_oversight_pay_by_professor.py``;
* the block a professor reads cannot carry a third party's data, because it is built from
  derived fields and never copies a spreadsheet row.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    WORKLOAD_HEADER,
    CoordinatorAccessError,
    CoordinatorConfig,
    CoordinatorConfigError,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
    fmt_money,
    parse_bonus_tiers,
    parse_money,
    render_pay_block,
)

# Two invented class groups. The ids are obviously fake and long enough for the config's own
# id token, which is the only property this file needs from them.
AA = "AAAAAAAAAAAAAAAAAAAAAAAA"
BB = "BBBBBBBBBBBBBBBBBBBBBBBB"
ME = "Prof Alfa"                 # the caller, invented
OTHER = "Prof Beta"              # someone else, invented

_BASE_RULES = f"""SPREADSHEETS:
Turma AA_01 = {AA}
Turma BB_02 = {BB}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:E110"
TAB_PROFESSORS: "Informacoes Adicionais"
RANGE_PROFESSORS: "A1:E50"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
"""

# The tenant's own declaration of the things this library will not guess. The column name is
# deliberately NOT one this code could have inferred — it is the tenant's phrasing, and a test
# that used "Carga Horária" would pass just as well against a hardcoded guess. HOURS_PER_CLASS
# is the tenant's own sentence ("cada linha na planilha equivale a 4 horas") and, like the rate,
# has no default anywhere: the tests that omit it assert a refusal, never a 4.
_PAY_RULES = """COLUMN_HOURS: "Total de Horas"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
IBOPE_BONUS: 80-89=30; 90+=40
"""

_SCHEDULE_AA = [
    ["Data", "Dia", "Professor", "Disciplina", "Sala"],
    ["05/09/2026", "Sab", ME, "Bancos NoSQL", "Sala Verde"],
    ["12/09/2026", "Sab", ME, "Bancos NoSQL", "Sala Verde"],
    ["03/10/2026", "Sab", ME, "Estatistica Aplicada", "Sala Verde"],
    ["10/10/2026", "Sab", OTHER, "Estatistica Aplicada", "Sala Verde"],
]
_SCHEDULE_BB = [
    ["Data", "Dia", "Professor", "Disciplina", "Sala"],
    ["19/09/2026", "Sab", ME, "Bancos NoSQL", "Sala Azul"],
]
# The hours tab carries a person's e-mail beside the hours ON PURPOSE: the PII test below needs
# a third-party field that a row-copying formatter would have carried out with it.
# "Total de Horas" is the discipline's TOTAL workload — context, never a factor of the month.
# The 16 is the tenant's own twin: read as hours per class it produced 2 × 16 = 32 h · R$ 3.840,00
# for a month that pays 2 × 4 h × R$ 120,00 = R$ 960,00.
_HOURS_AA = [
    ["Disciplina", "Total de Horas", "Professor", "E-mail"],
    ["Bancos NoSQL", "16", ME, "alfa@exemplo.invalid"],
    ["Estatistica Aplicada", "20", ME, "alfa@exemplo.invalid"],
]
_HOURS_BB = [
    ["Disciplina", "Total de Horas", "Professor", "E-mail"],
    ["Bancos NoSQL", "8", ME, "alfa@exemplo.invalid"],
]


def _svc(rules: str = _BASE_RULES + _PAY_RULES, *, hours: bool = True,
         ibope: "list[list[str]] | None" = None,
         today: date = date(2026, 9, 1)) -> CoordinatorService:
    cfg = CoordinatorConfig(rules)
    store = InMemorySpreadsheetStore()
    store.put(AA, "Secretaria", _SCHEDULE_AA)
    store.put(BB, "Secretaria", _SCHEDULE_BB)
    if hours:
        store.put(AA, "Informacoes Adicionais", _HOURS_AA)
        store.put(BB, "Informacoes Adicionais", _HOURS_BB)
    if ibope is not None:
        store.put(AA, "Resultados IBOPE", ibope)
    return CoordinatorService(store, cfg, today=lambda: today)


# ── twin 1: rules present + classes in the period → classes × HOURS_PER_CLASS × rate ─────
def test_the_estimate_is_classes_times_HOURS_PER_CLASS_times_the_rate_grouped_by_turma_and_month():
    est = _svc().estimate_professor_pay(identity_label=ME)

    # AA_01 September: 2 classes; AA_01 October: 1; BB_02 September: 1 — 4 h each, by the rules
    assert [(g.turma, g.month) for g in est.groups] == [
        ("Turma AA_01", "09/2026"), ("Turma AA_01", "10/2026"), ("Turma BB_02", "09/2026")]
    assert est.hours_per_class == 4.0
    assert est.hours == pytest.approx(8 + 4 + 4)
    assert est.base == pytest.approx(16 * 120.0)
    assert est.rate == 120.0
    # the other professor's October class is not in it — the schedule read is already self-scoped
    assert all(ln.subject != "Estatistica Aplicada" or g.month == "10/2026"
               for g in est.groups for ln in g.lines)

    block = render_pay_block(est)
    assert "Horas por aula declaradas nas regras: 4 h" in block
    assert "*Turma AA_01 — 09/2026*" in block
    assert "*Turma BB_02 — 09/2026*" in block
    assert "Bancos NoSQL · 2 aulas · 8 h · R$ 960,00" in block
    assert "*Base*\n16 h · R$ 1.920,00" in block          # 4 classes × 4 h × 120


def test_the_owners_numbers_two_september_classes_at_four_hours_and_120_are_960():
    """The sentence the semantics were fixed by, 2026-09-22: "cada linha na planilha equivale a
    4 horas". Two September classes in one class group × 4 h × R$ 120,00 = R$ 960,00 — with no
    IBOPE result, that is the "Sem bônus" hypothesis and the base."""
    est = _svc().estimate_professor_pay(identity_label=ME, period="2026-09", turma="AA_01")
    assert [(g.turma, g.month) for g in est.groups] == [("Turma AA_01", "09/2026")]
    assert est.hours == pytest.approx(8)
    assert est.base == pytest.approx(960.0)
    block = render_pay_block(est)
    assert "Bancos NoSQL · 2 aulas · 8 h · R$ 960,00" in block
    assert "*Base*\n8 h · R$ 960,00" in block
    assert "Sem bônus · sem adicional · R$ 960,00" in block


@pytest.mark.parametrize("pct,per_hour,total", [("85", 30.0, 1200.0), ("92", 40.0, 1280.0)])
def test_the_owners_numbers_with_an_IBOPE_result_add_the_band_per_hour(pct, per_hour, total):
    """85% → +R$ 30,00/h over 8 h → R$ 1.200,00; 92% → +R$ 40,00/h → R$ 1.280,00."""
    rules = _BASE_RULES + _PAY_RULES + 'TAB_IBOPE: "Resultados IBOPE"\nCOLUMN_IBOPE: "Resultado"\n'
    svc = _svc(rules, ibope=[["Professor", "Resultado"], [ME, pct]])
    est = svc.estimate_professor_pay(identity_label=ME, period="2026-09", turma="AA_01")
    assert est.matched_tier is not None and est.matched_tier.per_hour == per_hour
    assert est.hypotheses == ()
    block = render_pay_block(est)
    assert f"*Total*\n{fmt_money(total)}" in block


def test_the_workload_is_NEVER_multiplied_by_the_classes_and_the_old_3840_is_gone():
    """The defect, pinned as its own twin. ``COLUMN_HOURS`` = 16 was read as hours PER CLASS and
    multiplied by the 2 September classes: 32 h · R$ 3.840,00, where the tenant's rule pays
    R$ 960,00. The workload survives as CONTEXT — under its own header, AFTER everything the
    period is about, pricing the whole discipline — and is a factor of nothing."""
    est = _svc().estimate_professor_pay(identity_label=ME, period="2026-09", turma="AA_01")
    line = est.groups[0].lines[0]
    assert (line.classes, line.workload, line.hours_total) == (2, 16.0, 8.0)
    block = render_pay_block(est)
    assert "R$ 3.840,00" not in block and "32 h" not in block
    assert WORKLOAD_HEADER in block
    assert "Bancos NoSQL (Turma AA_01) · 16 h · a disciplina inteira: R$ 1.920,00" in block
    assert block.index(WORKLOAD_HEADER) > block.index("*Base*")
    assert block.index(WORKLOAD_HEADER) > block.index("Bônus IBOPE")


def test_COLUMN_HOURS_is_optional_and_without_it_no_workload_is_said_or_sniffed():
    """A tenant that names no workload column gets the same estimate with less context — and no
    header is looked for on the sheet, because a column that "seems like" hours is the guess
    this config refuses to make."""
    rules = _BASE_RULES + "HOURS_PER_CLASS: 4\nPAY_RATE_PER_HOUR: 120,00\n"
    est = _svc(rules).estimate_professor_pay(identity_label=ME, period="2026-09", turma="AA_01")
    assert est.base == pytest.approx(960.0)
    assert est.workload_read is False and est.workload_missing == ()
    assert all(ln.workload is None for g in est.groups for ln in g.lines)
    block = render_pay_block(est)
    assert WORKLOAD_HEADER not in block
    assert "carga" not in block.lower()


def test_a_COLUMN_HOURS_declared_but_ABSENT_from_the_sheet_is_ignored_without_error():
    """The tenant's rules will say ``COLUMN_HOURS: <a name>`` over a tab that has no column by
    that name. That is context the tenant cannot have and nothing more: the estimate comes out
    whole — classes × HOURS_PER_CLASS × rate, bonus and all — with no context section, no
    refusal, no "NOT CONFIGURED" and no PARTIAL RESULT on its account. Three-way twin:
    declared+absent renders BYTE-IDENTICAL to not-declared; declared+present carries the
    section."""
    from cogno_praxis.coordinator.server import build_server
    absent = _svc(_BASE_RULES + 'COLUMN_HOURS: "Horas por aula"\n' + _PAY_RULES.split("\n", 1)[1])
    not_declared = _svc(_BASE_RULES + _PAY_RULES.split("\n", 1)[1])
    present = _svc()                                          # "Total de Horas" IS on the sheet
    assert absent.cfg.column_hours == "Horas por aula" and not_declared.cfg.column_hours == ""

    est = absent.estimate_professor_pay(identity_label=ME)
    assert est.workload_read is False and est.workload_missing == ()
    assert est.hours == pytest.approx(16) and est.base == pytest.approx(1920.0)
    assert [h.per_hour for h in est.hypotheses] == [0.0, 30.0, 40.0]   # the bonus half intact
    assert render_pay_block(est) == render_pay_block(
        not_declared.estimate_professor_pay(identity_label=ME))
    assert WORKLOAD_HEADER not in render_pay_block(est)
    assert WORKLOAD_HEADER in render_pay_block(present.estimate_professor_pay(identity_label=ME))
    # …and at the layer the model reads: a complete block, nothing refused, nothing partial
    out = build_server(absent)._tool_manager._tools["estimate_professor_pay"].fn(identity_label=ME)
    assert "R$ 960,00" in out and "*Base*" in out
    assert "NOT CONFIGURED" not in out and "PARTIAL RESULT" not in out and "ERROR" not in out


def _svc_mid_month(today: date = date(2026, 9, 15)) -> CoordinatorService:
    """Two September classes already GIVEN (03/09, 08/09) and one still to give (24/09), plus
    one in October — read on the 15th, so the past/future cut has something to cut."""
    cfg = CoordinatorConfig(_BASE_RULES + _PAY_RULES)
    store = InMemorySpreadsheetStore()
    store.put(AA, "Secretaria", [_SCHEDULE_AA[0],
                                 ["03/09/2026", "Qui", ME, "Bancos NoSQL", "Sala Verde"],
                                 ["08/09/2026", "Ter", ME, "Bancos NoSQL", "Sala Verde"],
                                 ["24/09/2026", "Qui", ME, "Bancos NoSQL", "Sala Verde"],
                                 ["03/10/2026", "Sab", ME, "Estatistica Aplicada", "Sala Verde"]])
    store.put(BB, "Secretaria", [_SCHEDULE_BB[0]])
    store.put(AA, "Informacoes Adicionais", _HOURS_AA)
    return CoordinatorService(store, cfg, today=lambda: today)


def test_the_estimate_reads_the_WHOLE_month_given_classes_included():
    """Turn 104, 2026-09-22: «quanto recebo pelas aulas de setembro», asked mid-month, came back
    as «1 aula» — the two classes already taught were cut as "past", because the estimate
    inherited the LISTING's from-today-onward default. Pay is the month, given and to give:
    2 past + 1 future = 3 × 4 h × R$ 120,00 = R$ 1.440,00."""
    est = _svc_mid_month().estimate_professor_pay(identity_label=ME, period="2026-09")
    assert [(g.turma, g.month) for g in est.groups] == [("Turma AA_01", "09/2026")]
    assert [(ln.subject, ln.classes) for ln in est.groups[0].lines] == [("Bancos NoSQL", 3)]
    assert est.hours == pytest.approx(12) and est.base == pytest.approx(1440.0)
    block = render_pay_block(est)
    assert "Bancos NoSQL · 3 aulas · 12 h · R$ 1.440,00" in block
    assert "R$ 480,00" not in block                       # not the «1 aula» the listing gives


def test_an_EMPTY_period_is_the_current_month_in_full_plus_what_comes_and_no_earlier_month():
    """No period named → the current month whole (its given classes included) and everything
    onward — and NOT the academic year's earlier months, which ``include_past`` alone would
    drag in. August is the control: one class there, and it must stay out."""
    svc = _svc_mid_month()
    svc.store.put(BB, "Secretaria", [_SCHEDULE_BB[0], ["20/08/2026", "Qui", ME, "Bancos NoSQL", "Sala Azul"]])
    est = svc.estimate_professor_pay(identity_label=ME, period="")
    assert [(g.turma, g.month) for g in est.groups] == [("Turma AA_01", "09/2026"), ("Turma AA_01", "10/2026")]
    assert est.groups[0].lines[0].classes == 3           # 03/09 and 08/09 are in, 20/08 is not
    assert est.hours == pytest.approx(12 + 4)


def test_the_LIST_read_keeps_hiding_past_classes_only_the_estimate_reads_the_month_whole():
    """The other half of the rule: ``get_professor_schedule`` called as a list is untouched — a
    professor reading a list still gets what is coming, and the report still counts the cut."""
    from cogno_praxis.coordinator.service import ReadReport
    svc = _svc_mid_month()
    report = ReadReport()
    listed = svc.get_professor_schedule(identity_label=ME, month="2026-09", report=report)
    assert [e.when.day for e in listed if e.when] == [24]
    assert report.hidden_past == 2
    assert svc.estimate_professor_pay(identity_label=ME, period="2026-09").groups[0].lines[0].classes == 3


def test_HOURS_PER_CLASS_reads_the_same_grammar_as_every_other_numeric_key():
    """``KEY: value``, the number alone — ``4``, ``4,5``, ``4.5``. No key here takes a suffix
    (``IBOPE_MIN_RESPONSE_PCT: 30%`` is already undeclared today), so ``4h`` is not invented
    into a 4: it is UNDECLARED and the refusal names the key, loudly."""
    assert CoordinatorConfig("HOURS_PER_CLASS: 4").hours_per_class == 4.0
    assert CoordinatorConfig("HOURS_PER_CLASS: 4,5").hours_per_class == 4.5
    assert CoordinatorConfig("HOURS_PER_CLASS: 4.5").hours_per_class == 4.5
    assert CoordinatorConfig('HOURS_PER_CLASS: "4"').hours_per_class == 4.0
    assert CoordinatorConfig("IBOPE_MIN_RESPONSE_PCT: 30%").ibope_min_response_pct is None
    assert CoordinatorConfig("HOURS_PER_CLASS: 4h").hours_per_class is None
    assert "HOURS_PER_CLASS" in CoordinatorConfig("HOURS_PER_CLASS: 4h\nPAY_RATE_PER_HOUR: 120,00"
                                                  ).pay_undeclared


def test_the_same_discipline_may_carry_a_DIFFERENT_workload_in_different_class_groups():
    """The workload is read per SPREADSHEET, and the tenant's own course lists prove why: the
    same discipline is 16h in one MBA and 8h in another. Keying the map globally would let
    whichever group was read first describe the other one."""
    est = _svc().estimate_professor_pay(identity_label=ME)
    by_key = {(g.turma, g.month): g for g in est.groups}
    assert by_key[("Turma AA_01", "09/2026")].lines[0].workload == 16
    assert by_key[("Turma BB_02", "09/2026")].lines[0].workload == 8
    block = render_pay_block(est)
    assert "Bancos NoSQL (Turma AA_01) · 16 h · a disciplina inteira: R$ 1.920,00" in block
    assert "Bancos NoSQL (Turma BB_02) · 8 h · a disciplina inteira: R$ 960,00" in block


def test_the_estimate_is_not_cut_by_the_listing_horizon():
    """The 30-day default window is a READING convenience — it exists so a professor scanning a
    list does not have to scroll. An estimate is not a list, and one silently cut at 30 days
    answers "quanto eu recebo" with some of the months and no sign that it did. That is the
    calendar export's own "quietly exported 3 of 6" defect said about money, where the reader
    has no way to notice the shortfall. The export opts out for that reason; so does this."""
    from cogno_praxis.coordinator.service import DEFAULT_HORIZON_DAYS
    est = _svc().estimate_professor_pay(identity_label=ME)      # today = 01/09/2026
    months = {g.month for g in est.groups}
    assert "10/2026" in months, (
        f"October is {DEFAULT_HORIZON_DAYS}+ days out and belongs in the estimate")
    assert est.hours == pytest.approx(16)


def test_a_NAMED_period_still_narrows_the_estimate():
    """The twin: opting out of the default window is not opting out of filtering."""
    est = _svc().estimate_professor_pay(identity_label=ME, period="2026-10")
    assert [(g.turma, g.month) for g in est.groups] == [("Turma AA_01", "10/2026")]
    assert est.hours == pytest.approx(4)


def test_a_discipline_whose_workload_the_sheet_does_not_carry_is_NAMED_never_zeroed():
    """Zero is a figure and it is false. The month's pay does not depend on the sheet any more —
    that discipline is paid classes × HOURS_PER_CLASS like every other — so what is unknown is
    only its TOTAL workload, and the context section says exactly that, by name."""
    svc = _svc()
    svc.store.put(AA, "Informacoes Adicionais",
                  [_HOURS_AA[0], _HOURS_AA[1]])       # Estatistica Aplicada dropped
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.workload_missing == ("Estatistica Aplicada",)
    assert est.hours == pytest.approx(16)             # its October class is still 4 h, not 0
    block = render_pay_block(est)
    assert "Estatistica Aplicada · 1 aula · 4 h · R$ 480,00" in block
    assert "Estatistica Aplicada (Turma AA_01) · carga não declarada na planilha" in block
    assert "Fora desta soma" not in block             # nothing is outside the sum any more
    assert "0 h" not in block and "R$ 0,00" not in block


# ── twin 2: IBOPE absent → the hypotheses AND the sentence ───────────────────────────
def test_an_absent_IBOPE_result_yields_every_declared_hypothesis_and_chooses_none():
    est = _svc().estimate_professor_pay(identity_label=ME)
    assert est.ibope_found is False
    assert est.ibope_pct is None

    # one per declared tier, plus the no-bonus baseline. NOT a hardcoded 3: the count follows
    # the tenant's declaration, and this tenant declares two bands.
    assert len(est.hypotheses) == len(est.tiers) + 1 == 3
    assert [h.per_hour for h in est.hypotheses] == [0.0, 30.0, 40.0]
    assert [h.total for h in est.hypotheses] == pytest.approx(
        [16 * 120.0, 16 * 150.0, 16 * 160.0])

    block = render_pay_block(est)
    assert "RESULTADO NÃO ENCONTRADO" in block
    assert "não foi encontrado" in block
    assert "nenhuma delas foi escolhida" in block
    for label in ("Sem bônus", "IBOPE 80–89%", "IBOPE 90%+"):
        assert label in block, label


def test_the_rendered_block_carries_EVERY_hypothesis_the_estimate_holds():
    """The deleting mutation for the declared table (the bonus bands).

    A renderer that dropped a band — or that stopped at the first — would still show a plausible
    block with a plausible number in it, and nobody reading the reply could tell. This walks the
    estimate's own list and demands each one, so removing an entry from the rendering is red.
    """
    est = _svc().estimate_professor_pay(identity_label=ME)
    block = render_pay_block(est)
    assert est.hypotheses, "the fixture declares two bands; with none there is nothing to pin"
    for h in est.hypotheses:
        assert h.label in block, f"hypothesis {h.label!r} vanished from the block"


def test_two_IBOPE_rows_that_DISAGREE_are_read_as_not_found_rather_than_arbitrated():
    """Picking one of two results is an invented bonus wearing a real number."""
    rules = _BASE_RULES + _PAY_RULES + 'TAB_IBOPE: "Resultados IBOPE"\nCOLUMN_IBOPE: "Resultado"\n'
    svc = _svc(rules, ibope=[["Professor", "Resultado"], [ME, "85"], [ME, "92"]])
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.ibope_found is False
    assert len(est.hypotheses) == 3


def test_an_IBOPE_result_that_WAS_found_applies_its_band_and_offers_no_hypothesis():
    rules = _BASE_RULES + _PAY_RULES + 'TAB_IBOPE: "Resultados IBOPE"\nCOLUMN_IBOPE: "Resultado"\n'
    svc = _svc(rules, ibope=[["Professor", "Resultado"], [ME, "92%"], [OTHER, "10"]])
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.ibope_found is True and est.ibope_pct == 92.0
    assert est.matched_tier is not None and est.matched_tier.per_hour == 40.0
    assert est.hypotheses == ()
    block = render_pay_block(est)
    assert "RESULTADO NÃO ENCONTRADO" not in block
    assert "R$ 2.560,00" in block                     # 16 h × (120 + 40)


def test_a_result_BELOW_every_declared_band_is_ZERO_and_the_zero_is_SAID():
    """One of the two worlds ``matched_tier is None`` used to flatten together.

    70% is under the lowest declared band, and the rules read "Ibope > 80% … adicional". So the
    adicional really is zero — an apurado fact, not an absence of one — and the block says which
    it is. It offers no hypothesis, because nothing here is open."""
    rules = _BASE_RULES + _PAY_RULES + 'TAB_IBOPE: "Resultados IBOPE"\nCOLUMN_IBOPE: "Resultado"\n'
    svc = _svc(rules, ibope=[["Professor", "Resultado"], [ME, "70"]])
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.ibope_found is True and est.matched_tier is None
    assert est.bonus_state == "below"
    assert est.hypotheses == ()
    block = render_pay_block(est)
    assert "Abaixo da faixa mais baixa declarada (80%)" in block
    assert "Isto é um valor apurado, não uma falta de informação." in block
    assert "*Total*\nR$ 1.920,00" in block            # the base, unchanged
    assert "NÃO ENCONTRADO" not in block


def test_a_result_IN_A_GAP_between_declared_bands_is_UNDETERMINED_and_never_zero():
    """The other world, and the one that used to be paid as zero.

    89,5 against bands of 80–89 and 90+ falls in neither. Paying zero there is a figure about
    somebody's money that the tenant's own rules never authorised; so is quietly promoting it to
    the band above. The estimate says the number, says the bands do not cover it, and offers the
    two neighbours — choosing neither."""
    rules = _BASE_RULES + _PAY_RULES + 'TAB_IBOPE: "Resultados IBOPE"\nCOLUMN_IBOPE: "Resultado"\n'
    svc = _svc(rules, ibope=[["Professor", "Resultado"], [ME, "89,5"]])
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.ibope_found is True and est.matched_tier is None
    assert est.bonus_state == "gap", "a gap must not be read as 'below the lowest band'"

    # the NEIGHBOURS, and only them — the whole ladder would be noise for a known number
    assert [(t.low, t.high) for t in est.neighbouring_tiers] == [(80.0, 89.0), (90.0, None)]
    assert [h.per_hour for h in est.hypotheses] == [0.0, 30.0, 40.0]

    block = render_pay_block(est)
    assert "FAIXA NÃO DECLARADA" in block
    assert "INDETERMINADO, e não é zero" in block
    assert "89,5%" in block or "89.5%" in block
    # ...and it did NOT quietly settle on either side
    assert "*Total*" not in block


def test_the_two_worlds_that_look_alike_from_inside_matched_tier_are_told_APART():
    """Both answer ``matched_tier is None``. Reading them as one is how 89,5 got paid as zero;
    reading a genuine sub-80 as "undetermined" would be the mirror defect, inventing doubt where
    the rules are perfectly clear. The state is what separates them."""
    rules = _BASE_RULES + _PAY_RULES + 'TAB_IBOPE: "Resultados IBOPE"\nCOLUMN_IBOPE: "Resultado"\n'
    below = _svc(rules, ibope=[["Professor", "Resultado"], [ME, "70"]]) \
        .estimate_professor_pay(identity_label=ME)
    gap = _svc(rules, ibope=[["Professor", "Resultado"], [ME, "89,5"]]) \
        .estimate_professor_pay(identity_label=ME)
    assert below.matched_tier is gap.matched_tier is None
    assert (below.bonus_state, gap.bonus_state) == ("below", "gap")
    assert below.hypotheses == () and gap.hypotheses != ()


def test_the_response_rate_CONDITION_is_stated_and_never_assumed_met():
    """``IBOPE_MIN_RESPONSE_PCT`` is a condition this system has no reader for — no tenant
    declares a column carrying the answered share. So it is never treated as met and never as
    failed: it is RENDERED, because a bonus quoted without the condition it hangs on reads as a
    bonus that has been earned."""
    rules = (_BASE_RULES + _PAY_RULES + 'TAB_IBOPE: "Resultados IBOPE"\n'
             'COLUMN_IBOPE: "Resultado"\nIBOPE_MIN_RESPONSE_PCT: 30\n')
    svc = _svc(rules, ibope=[["Professor", "Resultado"], [ME, "92"]])
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.ibope_min_response_pct == 30.0
    block = render_pay_block(est)
    assert "pelo menos 30% da turma" in block
    assert "Este sistema não lê essa taxa" in block
    # and a tenant who declares no threshold gets no sentence about one
    plain = _svc(_BASE_RULES + _PAY_RULES).estimate_professor_pay(identity_label=ME)
    assert plain.ibope_min_response_pct is None
    assert "da turma" not in render_pay_block(plain)


def test_an_out_of_range_threshold_is_refused_rather_than_clamped():
    """Clamping 150 to 100 would invent a rule the tenant never wrote, about money."""
    from cogno_praxis.coordinator import CoordinatorConfig
    assert CoordinatorConfig("IBOPE_MIN_RESPONSE_PCT: 30").ibope_min_response_pct == 30.0
    for junk in ("150", "-1", "abc", ""):
        assert CoordinatorConfig(f"IBOPE_MIN_RESPONSE_PCT: {junk}").ibope_min_response_pct is None


def test_a_free_slot_is_not_a_class_and_earns_nothing():
    """FREE_SLOT_LABELS rows are openings in the calendar, not taught classes. Counting one is
    paying for a lesson nobody gave."""
    svc = _svc()
    svc.store.put(BB, "Secretaria", _SCHEDULE_BB + [["26/09/2026", "Sab", ME, "Livre", "Sala Azul"]])
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.hours == pytest.approx(16)             # unchanged by the free slot
    assert "Livre" not in render_pay_block(est)


# ── twin 3: rules absent → a clean refusal, no invented rate ─────────────────────────
def test_rules_without_a_rate_refuse_and_NAME_the_missing_key():
    svc = _svc(_BASE_RULES + 'COLUMN_HOURS: "Total de Horas"\nHOURS_PER_CLASS: 4\n')
    with pytest.raises(CoordinatorError) as exc:
        svc.estimate_professor_pay(identity_label=ME)
    assert "PAY_RATE_PER_HOUR" in str(exc.value)
    assert "has not configured" in str(exc.value)
    assert "HOURS_PER_CLASS" not in str(exc.value)    # only what is missing is named


def test_rules_without_HOURS_PER_CLASS_refuse_and_never_infer_four_nor_divide_the_workload():
    """The number belongs to the tenant. "4" is what every tenant so far has meant, which is
    exactly why a default would be right until the day it is not; and 16 h ÷ 2 classes = 8 h
    is a derivation nobody wrote. Both are wrong numbers about a person's pay, so with the key
    absent there is no estimate — and the refusal names the key, not the column, which is no
    longer required."""
    svc = _svc(_BASE_RULES + 'COLUMN_HOURS: "Total de Horas"\nPAY_RATE_PER_HOUR: 120,00\n')
    with pytest.raises(CoordinatorConfigError) as exc:
        svc.estimate_professor_pay(identity_label=ME)
    msg = str(exc.value)
    assert "HOURS_PER_CLASS" in msg and "has not configured" in msg
    assert "COLUMN_HOURS" not in msg
    assert "R$" not in msg                            # nothing was estimated on any assumption
    # …and a zero or junk value is UNDECLARED, never "a class is worth nothing"
    for junk in ("0", "-4", "abc", ""):
        assert CoordinatorConfig(f"HOURS_PER_CLASS: {junk}").hours_per_class is None
    assert CoordinatorConfig("HOURS_PER_CLASS: 4,5").hours_per_class == 4.5


def test_a_tenant_that_declared_NEITHER_is_told_about_BOTH():
    cfg = CoordinatorConfig(_BASE_RULES)
    assert cfg.pay_undeclared == ("PAY_RATE_PER_HOUR", "HOURS_PER_CLASS")
    assert cfg.pay_rate_per_hour is None
    assert cfg.hours_per_class is None
    assert cfg.ibope_bonus == ()
    # "nada": NOTHING in prose either, so the refusal names the keys and nothing else
    assert cfg.pay_in_prose == ()
    with pytest.raises(CoordinatorConfigError) as exc:
        _svc(_BASE_RULES).estimate_professor_pay(identity_label=ME)
    assert "PAY_RATE_PER_HOUR, HOURS_PER_CLASS are missing" in str(exc.value)
    assert "found" not in str(exc.value)


def test_a_tenant_that_declared_them_in_PROSE_is_told_what_was_found_and_which_key_it_needs():
    """The twin of "nada", and the 2026-09-22 turn: the same two keys missing, but the rules
    plainly CONTAIN the figures — in Portuguese prose the parser does not read. The refusal
    has to say so, sentence by sentence, or it is "missing" over rules that are not."""
    prose = (_BASE_RULES + "\n# Valores Financeiros\n"
             " - Aula - R$ 120,00 por hora, sendo o mínimo 4 horas por aula.\n")
    cfg = CoordinatorConfig(prose)
    assert cfg.pay_undeclared == ("PAY_RATE_PER_HOUR", "HOURS_PER_CLASS")
    assert [(h.key, h.excerpts) for h in cfg.pay_in_prose] == [
        ("PAY_RATE_PER_HOUR", ("R$ 120,00 por hora",)),
        ("HOURS_PER_CLASS", ("4 horas por aula",))]
    with pytest.raises(CoordinatorConfigError) as exc:
        _svc(prose).estimate_professor_pay(identity_label=ME)
    msg = str(exc.value)
    assert "PAY_RATE_PER_HOUR, HOURS_PER_CLASS are missing" in msg
    assert 'found "R$ 120,00 por hora" in the rules, but PAY_RATE_PER_HOUR is not declared' in msg
    assert 'found "4 horas por aula" in the rules, but HOURS_PER_CLASS is not declared' in msg
    assert "R$ 960" not in msg and "R$ 480" not in msg   # named, never computed


def test_the_refusal_is_not_worded_as_a_malfunction():
    """A tenant that never declared a figure is not a system that broke, and the model relays
    the word it is given: "ERROR" reaches a professor as "não consegui acessar"."""
    from cogno_praxis.coordinator.server import build_server
    svc = _svc(_BASE_RULES)
    tools = build_server(svc)._tool_manager._tools
    out = tools["estimate_professor_pay"].fn(identity_label=ME)
    assert out.startswith("NOT CONFIGURED:")
    assert "PAY_RATE_PER_HOUR" in out and "HOURS_PER_CLASS" in out


# ── twin 4 (the negative twin): somebody else's pay, for every NON-oversight role ─────
@pytest.mark.parametrize("role", ["", "GUEST", "EMPLOYEE"])
def test_another_professors_pay_is_refused_to_every_role_that_is_not_the_coordination(role):
    """An opened scope always has a possible victim, and this is the one it is not.

    Until 2026-09-23 this refusal reached the oversight roles too; the owner's decision — «o
    supervisor pode ter acesso a todos os professores, pois ele é o coordenador» — moved THEM
    and nobody else: a professor asking about a colleague gets this sentence, unchanged, and
    ``test_oversight_pay_by_professor.py`` pins it as a literal."""
    with pytest.raises(CoordinatorAccessError) as exc:
        _svc().estimate_professor_pay(professor=OTHER, identity_label=ME, role=role)
    assert "your own" in str(exc.value)
    assert "R$" not in str(exc.value)                 # and it leaks no figure while refusing


@pytest.mark.parametrize("role", ["SUPERVISOR", "ADMIN", "OWNER"])
def test_an_oversight_role_naming_another_professor_gets_THAT_estimate_named(role):
    """The other half of the same line: the coordination may ask about a professor by name,
    and the block says whose it is. Beta's one October class, 4 h · R$ 480,00 — not Alfa's 16."""
    est = _svc().estimate_professor_pay(professor=OTHER, identity_label=ME, role=role)
    assert est.professor == OTHER
    assert est.hours == pytest.approx(4) and est.base == pytest.approx(480.0)
    assert f"Professor: {OTHER}" in render_pay_block(est)


def test_a_turn_with_no_identified_professor_is_refused_rather_than_answered_for_nobody():
    """With nobody named, "their own pay" has no referent — and an empty professor filter would
    otherwise aggregate the WHOLE faculty's classes into one estimate."""
    with pytest.raises(CoordinatorAccessError):
        _svc().estimate_professor_pay(identity_label="", role="ADMIN")


def test_naming_YOURSELF_is_allowed_because_it_is_the_same_person():
    """The twin that keeps the refusal from becoming "never accept a name": a professor who
    types their own name is asking the very question this tool exists for."""
    est = _svc().estimate_professor_pay(professor=ME, identity_label=ME)
    assert est.base > 0


# ── twin 5: the EMPTY argument, which is the door the named one was locking ───────────
#
# The guard above refuses ``professor=OTHER`` to every role. It was measured on 2026-09-09 that
# leaving ``professor`` EMPTY walked straight past it for an oversight role, because the estimate
# delegated to ``get_professor_schedule`` with ``professor=""`` and the caller's own ``role`` —
# and there an empty professor means "no filter", i.e. THE MASTER SCHEDULE. On a seeded sheet:
# EMPLOYEE 12 h / R$ 1.440,00 (hers) against SUPERVISOR 16 h / R$ 1.920,00, the extra four hours
# being another professor's class, summed into a block whose every line says what the CALLER
# earns. The shape is the one this repository already has a name for: the wrapper is careful and
# the thing it delegates to is not. The file already half-knew — the no-label twin's own
# docstring says "an empty professor filter would otherwise aggregate the WHOLE faculty's
# classes into one estimate" — but it guarded the missing LABEL and not the widening ROLE.
_EVERY_ROLE = ["", "GUEST", "EMPLOYEE", "SUPERVISOR", "ADMIN", "OWNER"]


@pytest.mark.parametrize("role", _EVERY_ROLE)
def test_an_EMPTY_professor_gets_the_callers_OWN_pay_whatever_their_role(role):
    """``professor=""`` means "me", never "everybody" — and for an oversight role it used to
    mean everybody. ``Prof Beta``'s October class is the witness: it sits in the same class
    group and the same month as one of ``Prof Alfa``'s, so a leak does not add a group or a
    line, it doubles a COUNT — which is exactly how it went unnoticed."""
    est = _svc().estimate_professor_pay(professor="", identity_label=ME, role=role)
    assert est.hours == pytest.approx(8 + 4 + 4)          # 16 h, and 20 h with Beta's class in
    assert est.base == pytest.approx(16 * 120.0)
    october = [g for g in est.groups if (g.turma, g.month) == ("Turma AA_01", "10/2026")]
    assert [(ln.subject, ln.classes) for g in october for ln in g.lines] == [
        ("Estatistica Aplicada", 1)]                      # 1 = mine; 2 = mine AND Beta's


def test_the_estimate_is_the_SAME_FIGURE_whatever_the_callers_role():
    """The positive statement of the rule, in one comparison rather than six assertions.

    Every OTHER read in this service widens for oversight, on purpose. This one is the single
    capability whose scope argument is the asker, so a role may not move its number at all —
    and a test that says so cannot be satisfied by a fix that merely narrows SUPERVISOR while
    leaving ADMIN or OWNER behind."""
    figures = {role: _svc().estimate_professor_pay(professor="", identity_label=ME, role=role)
               for role in _EVERY_ROLE}
    assert len({(e.hours, e.base) for e in figures.values()}) == 1


def test_the_SCHEDULE_still_widens_for_oversight_and_only_the_ESTIMATE_does_not():
    """The other half of the fix, and the reason it is a fix and not a regression.

    ``get_professor_schedule`` SHOULD hand an oversight role the master grid — that is its
    documented scope and a coordinator's whole job. The defect was never that the schedule read
    widens; it was that the pay estimate INHERITED the widening from it while promising, in its
    own docstring and in its tool description, "self-only, for every role". So this pins the
    divergence itself: same service, same sheet, same caller — the schedule widens, the money
    does not. A future simplification that puts ``professor=""`` back kills this."""
    svc = _svc()
    master = svc.get_professor_schedule(professor="", identity_label=ME, role="SUPERVISOR",
                                        apply_horizon=False)
    own = svc.get_professor_schedule(professor="", identity_label=ME, role="EMPLOYEE",
                                     apply_horizon=False)
    assert OTHER in {e.professor for e in master}         # the coordinator sees everybody
    assert OTHER not in {e.professor for e in own}
    assert len(master) > len(own)

    pay = svc.estimate_professor_pay(professor="", identity_label=ME, role="SUPERVISOR")
    assert pay.hours == pytest.approx(16)                 # …and still earns only their own


# ── (A) what the block a professor reads may contain ─────────────────────────────────
def test_the_block_carries_no_row_verbatim_and_no_third_party_field():
    """The listing formatter beside this one emits EVERY non-empty column of a sheet row
    verbatim, which is why this block is built the other way round: from derived fields only —
    a class-group key, a month, a discipline, a count, an hour total, a figure.

    The fixture's hours tab carries an e-mail column next to the hours precisely so a
    row-copying implementation would fail here. Nothing else is needed to keep a third party out:
    the caller's own estimate is scoped to the caller, so there is no second person's data in
    scope to begin with — and the one name on it is the reader's own, on the ownership line."""
    est = _svc().estimate_professor_pay(identity_label=ME)
    block = render_pay_block(est)
    assert "@" not in block                           # no address travelled with the hours
    assert "exemplo.invalid" not in block
    assert OTHER not in block                         # no other professor
    # the reader's own name appears EXACTLY once, on the ownership header (2026-09-23) — a
    # figure without an owner in a coordinator's hands shipped as the faculty's totals
    assert block.count(ME) == 1 and f"Professor: {ME}" in block.splitlines()[1]
    assert "Sala" not in block                        # no room, no unrelated sheet column
    assert AA not in block and BB not in block        # no spreadsheet id


def test_the_block_is_the_rendered_shape_the_channel_expects():
    block = render_pay_block(_svc().estimate_professor_pay(identity_label=ME))
    headers = [ln for ln in block.splitlines() if ln.startswith("*") and ln.endswith("*")]
    assert headers[0] == "*Remuneração estimada*"
    assert "*Base*" in headers
    # lines carry values, not repeated labels
    body = [ln for ln in block.splitlines() if " · " in ln]
    assert body and not any(ln.startswith(("Disciplina:", "Aulas:", "Turma:")) for ln in body)


def test_a_period_that_filtered_something_is_NAMED_and_one_that_filtered_nothing_is_not():
    """The same rule the calendar proposal already lives by: the sentence describing the filter
    and the filter itself have to be the same fact."""
    assert _svc().estimate_professor_pay(identity_label=ME, period="2026-10").period \
        == "October 2026"
    assert _svc().estimate_professor_pay(identity_label=ME, period="").period == ""
    assert _svc().estimate_professor_pay(identity_label=ME, period="de").period == ""


def test_a_period_with_no_classes_answers_emptily_instead_of_estimating_zero():
    from cogno_praxis.coordinator.server import build_server
    tools = build_server(_svc())._tool_manager._tools
    out = tools["estimate_professor_pay"].fn(identity_label=ME, period="2026-12")
    assert "nothing to estimate" in out
    assert "R$" not in out


# ── the two pure parsers the money rides on ─────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("120,00", 120.0), ("120.00", 120.0), ("120", 120.0), ("R$ 1.920,00", 1920.0),
    ("1,920.00", 1920.0), ("", None), ("  ", None), ("abc", None), ("R$", None),
    ("12,3,4", None), (None, None),
])
def test_money_is_read_in_both_locales_and_refuses_everything_else(raw, expected):
    """A rate read wrong by a factor of a thousand is worse than no rate, so there is no
    best-effort branch: anything the grammar does not cover comes back None and refuses."""
    assert parse_money(raw) == expected


def test_a_band_the_parser_cannot_read_is_REPORTED_never_dropped():
    """The failure this replaced was silent and cost money. An unreadable band used to vanish
    into a log warning, and a value whose bands ALL failed came back as "no bonus declared" —
    the very sentence a tenant with no bonus scheme legitimately gets. A typo therefore paid a
    professor less and gave nobody, on either side, anything to notice."""
    tiers, bad = parse_bonus_tiers("80-89=30; isto nao e uma faixa; 90+=40")
    assert [(t.low, t.high, t.per_hour) for t in tiers] == [(80.0, 89.0, 30.0),
                                                            (90.0, None, 40.0)]
    assert bad == ("isto nao e uma faixa",), "the unreadable band has to come back NAMED"
    assert parse_bonus_tiers("") == ((), ())
    assert parse_bonus_tiers("nada aqui") == ((), ("nada aqui",))


def test_a_comma_is_a_DECIMAL_separator_and_never_a_band_separator():
    """The thousand-fold money bug, pinned. With the comma acting as a band separator,
    ``80-89 = 1.234,56`` split into ``"80-89 = 1.234"`` and ``"56"``: the first parsed as a
    perfectly plausible **R$ 1,23** and the second was discarded. Nothing looked wrong. A
    separator that can occur INSIDE the value it separates is not a separator."""
    tiers, bad = parse_bonus_tiers("80-89=1.234,56")
    assert bad == ()
    assert [(t.low, t.high, t.per_hour) for t in tiers] == [(80.0, 89.0, 1234.56)]
    # and the same amount written the other way round reads identically
    assert parse_bonus_tiers("80-89=1234.56")[0][0].per_hour == 1234.56
    # two bands whose amounts BOTH carry decimals still separate correctly
    tiers, bad = parse_bonus_tiers("80-89=30,00; 90+=40,50")
    assert bad == ()
    assert [t.per_hour for t in tiers] == [30.0, 40.5]


def test_an_unreadable_band_REFUSES_THE_ESTIMATE_and_names_the_entry():
    """The loud half, at the layer the professor reaches: not a dropped band, a refused turn."""
    from cogno_praxis.coordinator import CoordinatorConfigError
    svc = _svc(_BASE_RULES + 'COLUMN_HOURS: "Total de Horas"\nHOURS_PER_CLASS: 4\n'
               "PAY_RATE_PER_HOUR: 120,00\nIBOPE_BONUS: 80-89=30; isto nao e uma faixa\n")
    with pytest.raises(CoordinatorConfigError) as exc:
        svc.estimate_professor_pay(identity_label=ME)
    msg = str(exc.value)
    assert "isto nao e uma faixa" in msg, "the refusal must name the entry to fix"
    assert "SEMICOLONS" in msg
    assert "R$" not in msg                            # it refuses without quoting any figure


def test_rules_that_declare_no_bonus_say_so_instead_of_hypothesising():
    """No tier is not the same fact as no IBOPE result: one is a complete answer."""
    svc = _svc(_BASE_RULES + 'COLUMN_HOURS: "Total de Horas"\nHOURS_PER_CLASS: 4\n'
               "PAY_RATE_PER_HOUR: 120,00\n")
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.tiers == () and est.hypotheses == ()
    block = render_pay_block(est)
    assert "não declaram nenhuma faixa de bônus" in block
    assert "RESULTADO NÃO ENCONTRADO" not in block


# ── (B) the guard that opened, and the half that stayed shut ─────────────────────────
def _prompt(slot: str) -> str:
    from pathlib import Path
    root = Path(__import__("cogno_praxis").__file__).resolve().parent
    return " ".join((root / "coordinator" / "prompts" / f"{slot}.txt")
                    .read_text(encoding="utf-8").split())


def test_the_intake_now_lets_a_professors_OWN_pay_question_in():
    """Turn 67 never reached a tool: ``superego.blocked=true``, ``judge_attempts=0``. A
    capability the intake blocks is a capability nobody can reach."""
    scope = _prompt("scope")
    assert "THEIR OWN remuneration" in scope
    assert "quanto eu recebo" in scope


def test_the_intake_still_blocks_the_finance_that_did_NOT_open():
    """«Passou a permitir X» without «e continua a recusar Y» is half a sentence."""
    scope = _prompt("scope")
    assert "Finance is blocked EXCEPT for those openings" in scope
    for still_out in ("another person's pay", "the institution's accounts",
                      "invoices to process", "budgets", "tuition"):
        assert still_out in scope, still_out


def test_the_executor_is_told_never_to_do_the_arithmetic_itself():
    """Turn 65's own draft counted classes and reached for a total; the numbers it needed were
    in the sheet and nothing was reading them. The tool reads them now, and the prompt has to
    say that multiplying a listing is not a substitute."""
    system = _prompt("system")
    assert "estimate_professor_pay" in system
    assert "Never compute pay yourself" in system
    assert "Leave `professor` EMPTY" in system


def test_the_executor_is_told_the_three_sentences_that_must_survive_into_the_reply():
    system = _prompt("system")
    assert "RESULTADO NÃO ENCONTRADO" in system and "Relay ALL of them" in system
    assert "Carga horária total das disciplinas" in system   # context, never the month's amount
    assert "never present one as the month's amount" in system
    assert "NOT CONFIGURED" in system
    assert "but PAY_RATE_PER_HOUR is not declared" in system  # the prose sentence must survive


def test_the_judge_reads_an_unknown_bonus_as_a_COMPLETE_answer():
    """The family this persona has already lost turns to: a fail-closed judge reading a truthful
    "we do not know the bonus" as an incomplete goal and retrying it into a handoff."""
    limits = _prompt("limits")
    assert "A PAY ESTIMATE is COMPLETE" in limits
    assert "naming one would be the fabrication" in limits
    assert "REJECT, however: any pay figure that did not come from that tool" in limits


def test_the_voicer_is_told_to_relay_the_block_and_to_refuse_a_third_partys_pay_as_a_RULE():
    voice = _prompt("voice")
    assert "keep that sentence AND every hypothesis under it" in voice
    assert "só posso falar da sua própria remuneração" in voice
    assert "never as a system fault" in voice
