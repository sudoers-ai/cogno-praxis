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
* an IBOPE result that was NOT found produces every declared hypothesis and chooses none;
* rules that declare no rate — or no hours column — produce a refusal, never a figure;
* another professor's pay is refused to EVERY role, which is the victim of an opened scope;
* the block a professor reads cannot carry a third party's data, because it is built from
  derived fields and never copies a spreadsheet row.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorAccessError,
    CoordinatorConfig,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
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

# The tenant's own declaration of the two things this library will not guess. The column name is
# deliberately NOT one this code could have inferred — it is the tenant's phrasing, and a test
# that used "Carga Horária" would pass just as well against a hardcoded guess.
_PAY_RULES = """COLUMN_HOURS: "Total de Horas"
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


# ── twin 1: rules present + classes in the period → a value, grouped by turma and month ──
def test_the_estimate_is_the_hours_times_the_declared_rate_grouped_by_turma_and_month():
    est = _svc().estimate_professor_pay(identity_label=ME)

    # AA_01 September: 2 × 16h; AA_01 October: 1 × 20h; BB_02 September: 1 × 8h
    assert [(g.turma, g.month) for g in est.groups] == [
        ("Turma AA_01", "09/2026"), ("Turma AA_01", "10/2026"), ("Turma BB_02", "09/2026")]
    assert est.hours == pytest.approx(32 + 20 + 8)
    assert est.base == pytest.approx(60 * 120.0)
    assert est.rate == 120.0
    # the other professor's October class is not in it — the schedule read is already self-scoped
    assert all(ln.subject != "Estatistica Aplicada" or g.month == "10/2026"
               for g in est.groups for ln in g.lines)

    block = render_pay_block(est)
    assert "*Turma AA_01 — 09/2026*" in block
    assert "*Turma BB_02 — 09/2026*" in block
    assert "Bancos NoSQL · 2 aulas · 32 h · R$ 3.840,00" in block
    assert "R$ 7.200,00" in block                    # 60 h × 120


def test_the_same_discipline_may_carry_DIFFERENT_hours_in_different_class_groups():
    """The hours are read per SPREADSHEET, and the tenant's own course lists prove why: the same
    discipline is 16h in one MBA and 8h in another. Keying the map globally would let whichever
    group was read first decide what the other one pays."""
    est = _svc().estimate_professor_pay(identity_label=ME)
    by_key = {(g.turma, g.month): g for g in est.groups}
    assert by_key[("Turma AA_01", "09/2026")].lines[0].hours_each == 16
    assert by_key[("Turma BB_02", "09/2026")].lines[0].hours_each == 8


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
    assert est.hours == pytest.approx(60)


def test_a_NAMED_period_still_narrows_the_estimate():
    """The twin: opting out of the default window is not opting out of filtering."""
    est = _svc().estimate_professor_pay(identity_label=ME, period="2026-10")
    assert [(g.turma, g.month) for g in est.groups] == [("Turma AA_01", "10/2026")]
    assert est.hours == pytest.approx(20)


def test_a_discipline_whose_hours_the_sheet_does_not_carry_is_NAMED_never_zeroed():
    """Zero is a figure and it is false: it reads as "that class pays nothing". The honest
    answer names the discipline and leaves it out of the sum."""
    svc = _svc()
    svc.store.put(AA, "Informacoes Adicionais",
                  [_HOURS_AA[0], _HOURS_AA[1]])       # Estatistica Aplicada dropped
    est = svc.estimate_professor_pay(identity_label=ME)
    assert est.hours_missing == ("Estatistica Aplicada",)
    assert est.hours == pytest.approx(32 + 8)         # the 20h discipline is NOT counted as 0
    block = render_pay_block(est)
    assert "Estatistica Aplicada · 1 aula · horas não declaradas · —" in block
    assert "Fora desta soma" in block and "Estatistica Aplicada" in block


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
        [60 * 120.0, 60 * 150.0, 60 * 160.0])

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
    assert "R$ 9.600,00" in block                     # 60 h × (120 + 40)


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
    assert "R$ 7.200,00" in block                     # the base, unchanged
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
    assert est.hours == pytest.approx(60)             # unchanged by the free slot
    assert "Livre" not in render_pay_block(est)


# ── twin 3: rules absent → a clean refusal, no invented rate ─────────────────────────
def test_rules_without_a_rate_refuse_and_NAME_the_missing_key():
    svc = _svc(_BASE_RULES + 'COLUMN_HOURS: "Total de Horas"\n')
    with pytest.raises(CoordinatorError) as exc:
        svc.estimate_professor_pay(identity_label=ME)
    assert "PAY_RATE_PER_HOUR" in str(exc.value)
    assert "has not configured" in str(exc.value)


def test_rules_without_an_hours_COLUMN_refuse_rather_than_guessing_a_header():
    """The column name belongs to the tenant. There is no default and no sniffing: a header that
    "looks like" hours is how a room number becomes a workload."""
    svc = _svc(_BASE_RULES + "PAY_RATE_PER_HOUR: 120,00\n")
    with pytest.raises(CoordinatorError) as exc:
        svc.estimate_professor_pay(identity_label=ME)
    assert "COLUMN_HOURS" in str(exc.value)


def test_a_tenant_that_declared_NEITHER_is_told_about_BOTH():
    cfg = CoordinatorConfig(_BASE_RULES)
    assert cfg.pay_undeclared == ("PAY_RATE_PER_HOUR", "COLUMN_HOURS")
    assert cfg.pay_rate_per_hour is None
    assert cfg.ibope_bonus == ()


def test_the_refusal_is_not_worded_as_a_malfunction():
    """A tenant that never declared a figure is not a system that broke, and the model relays
    the word it is given: "ERROR" reaches a professor as "não consegui acessar"."""
    from cogno_praxis.coordinator.server import build_server
    svc = _svc(_BASE_RULES)
    tools = build_server(svc)._tool_manager._tools
    out = tools["estimate_professor_pay"].fn(identity_label=ME)
    assert out.startswith("NOT CONFIGURED:")
    assert "PAY_RATE_PER_HOUR" in out and "COLUMN_HOURS" in out


# ── twin 4 (the negative twin): somebody else's pay, for EVERY role ──────────────────
@pytest.mark.parametrize("role", ["", "EMPLOYEE", "SUPERVISOR", "ADMIN", "OWNER"])
def test_another_professors_pay_is_refused_to_every_role_including_oversight(role):
    """An opened scope always has a possible victim, and this is the one it is not.

    Every other read here widens for an oversight role — a supervisor sees the master schedule.
    This one does not, and deliberately: the reason the guard opened at all is that the money is
    the ASKER'S. A branch where it is somebody else's has no such reason behind it."""
    with pytest.raises(CoordinatorAccessError) as exc:
        _svc().estimate_professor_pay(professor=OTHER, identity_label=ME, role=role)
    assert "your own" in str(exc.value)
    assert "R$" not in str(exc.value)                 # and it leaks no figure while refusing


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
    assert est.hours == pytest.approx(32 + 20 + 8)        # 60 h, and 80 h with Beta's class in
    assert est.base == pytest.approx(60 * 120.0)
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
    assert pay.hours == pytest.approx(60)                 # …and still earns only their own


# ── (A) what the block a professor reads may contain ─────────────────────────────────
def test_the_block_carries_no_row_verbatim_and_no_third_party_field():
    """The listing formatter beside this one emits EVERY non-empty column of a sheet row
    verbatim, which is why this block is built the other way round: from derived fields only —
    a class-group key, a month, a discipline, a count, an hour total, a figure.

    The fixture's hours tab carries an e-mail column next to the hours precisely so a
    row-copying implementation would fail here. Nothing else is needed to keep a third party out:
    the estimate is self-only, so there is no second person's data in scope to begin with."""
    est = _svc().estimate_professor_pay(identity_label=ME)
    block = render_pay_block(est)
    assert "@" not in block                           # no address travelled with the hours
    assert "exemplo.invalid" not in block
    assert OTHER not in block                         # no other professor
    assert ME not in block                            # not even the reader's own name
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
    svc = _svc(_BASE_RULES + 'COLUMN_HOURS: "Total de Horas"\nPAY_RATE_PER_HOUR: 120,00\n'
               "IBOPE_BONUS: 80-89=30; isto nao e uma faixa\n")
    with pytest.raises(CoordinatorConfigError) as exc:
        svc.estimate_professor_pay(identity_label=ME)
    msg = str(exc.value)
    assert "isto nao e uma faixa" in msg, "the refusal must name the entry to fix"
    assert "SEMICOLONS" in msg
    assert "R$" not in msg                            # it refuses without quoting any figure


def test_rules_that_declare_no_bonus_say_so_instead_of_hypothesising():
    """No tier is not the same fact as no IBOPE result: one is a complete answer."""
    svc = _svc(_BASE_RULES + 'COLUMN_HOURS: "Total de Horas"\nPAY_RATE_PER_HOUR: 120,00\n')
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
    assert "Finance is blocked EXCEPT for that one opening" in scope
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
    assert "horas não declaradas" in system
    assert "NOT CONFIGURED" in system


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
