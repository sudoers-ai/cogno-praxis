"""The coordination's reach over the faculty's pay — by name, or everyone one block each — and
the half that did not move: a professor who is not the coordination still sees only their own.

Three live turns of the owner's own tenant, 2026-09-22 (``turn_traces`` 1974/1975/1978 — turns
111, 112, 115; caller role SUPERVISOR; every name of a person replaced), are the reason this
file exists, and they showed THREE independent holes:

1. ``estimate_professor_pay(professor="")`` answered the SUPERVISOR with **his own** pay — the
   same figures turn 114 gave him for "minhas aulas" — and the reply called it «Totais de
   setembro de 2026 por turma». Nothing in the block said whose it was. The most dangerous of
   the three, because it LOOKS right. Closed by the OWNERSHIP HEADER — every estimate block
   says ``Professor: <whose>``, the caller's own included — in a commit of its own, so the
   reader can see the two changes apart.
2. ``get_professor_info`` answered "No faculty records found." on all three turns — the
   declared tab name did not match the sheet's. Configuration, fixed since; but the code must
   keep working over an EMPTY faculty tab, so the grouping is keyed on the SCHEDULE's own
   professor column and the tab is only a complement.
3. The master schedule came back as ``data · turma · disciplina`` — 128 lines, no professor
   anywhere — and the voice said, truthfully, «não consegui associar os professores às turmas».

The owner's decision, textual (2026-09-23): «o supervisor pode ter acesso a todos os professores,
pois ele é o coordenador». The boundary is exactly that: SUPERVISOR/ADMIN/OWNER may ask for a
professor by name or for everyone; ``""`` stays the caller for every role; GUEST/EMPLOYEE keep
today's refusal byte for byte.

**Two fixtures.** The SYNTHETIC one (``Professor A/B/C``, four class groups named like the
tenant's) reproduces the September the three turns read, with two colleagues added so that
"everyone" has somebody to group. The REAL-STATE twins pin the tool outputs those turns actually
recorded — the estimate block of turn 115 (847 chars), the two per-group blocks of turn 111
(769/753), the 117-char "nothing to estimate" — against this fixture, so the pins also prove the
fixture is the tenant's September. No spreadsheet id, no person, no address from the turns
appears here.
"""

from __future__ import annotations

import pytest

from datetime import date

from cogno_praxis.coordinator import (
    ALL_PROFESSORS,
    NO_CLASSES_LINE,
    CoordinatorAccessError,
    CoordinatorConfig,
    CoordinatorConfigError,
    CoordinatorError,
    CoordinatorService,
    FacultyPayEstimate,
    InMemorySpreadsheetStore,
    render_faculty_pay_block,
    render_pay_block,
)
from cogno_praxis.coordinator.server import build_server

# Four invented spreadsheet ids, in the tenant's own declaration order (it is the order the
# listing breaks a same-day tie in: 30/09 DSA_33 before 30/09 DE_10, as turn 115 shows).
S33, S34, D09, D10 = "C" * 24, "D" * 24, "A" * 24, "B" * 24
A, B, C = "Professor A", "Professor B", "Professor C"
SUPERVISOR = {"identity_label": A, "role": "SUPERVISOR"}
EMPLOYEE = {"identity_label": A, "role": "EMPLOYEE"}

_RULES = f"""SPREADSHEETS:
Turma DSA_33 = {S33}
Turma DSA_34 = {S34}
Turma DE_09 = {D09}
Turma DE_10 = {D10}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:E110"
TAB_PROFESSORS: "Informacoes Adicionais"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
IBOPE_BONUS: 80-89=30; 90+=40
IBOPE_MIN_RESPONSE_PCT: 30
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
SPARK = "Integrated Data Platforms and Processing with Spark"
_SHEETS = {
    S33: [["02/09/2026", "Qua", B, SPARK, ""],
          ["07/09/2026", "Seg", "", "Feriado - Independência do Brasil", ""],
          ["09/09/2026", "Qua", C, "Microservices Architecture", ""],
          ["14/09/2026", "Seg", B, f"{SPARK} - Aula adiada", ""],
          ["16/09/2026", "Qua", C, "Microservices Architecture", ""],
          ["21/09/2026", "Seg", B, SPARK, ""],
          ["23/09/2026", "Qua", B, f"{SPARK} - reposição do dia 14/09", ""],
          ["28/09/2026", "Seg", B, SPARK, ""],
          ["30/09/2026", "Qua", C, "Microservices Architecture", ""]],
    S34: [["01/10/2026", "Qui", A, "Workshop de Abertura", ""]],
    D09: [["01/09/2026", "Ter", B, "Python Programming for Data Engineers", ""],
          ["03/09/2026", "Qui", A, "NoSQL and Distributed Databases", ""],
          ["08/09/2026", "Ter", A, "NoSQL and Distributed Databases", ""],
          ["10/09/2026", "Qui", B, "Python Programming for Data Engineers", ""],
          ["15/09/2026", "Ter", C, "Advanced Data Processing with Spark", ""],
          ["17/09/2026", "Qui", B, "Python Programming for Data Engineers", ""],
          ["22/09/2026", "Ter", C, "Advanced Data Processing with Spark - Aula Adiada", ""],
          ["24/09/2026", "Qui", B, "Python Programming for Data Engineers", ""],
          ["29/09/2026", "Ter", C, "Advanced Data Processing with Spark", ""],
          ["01/10/2026", "Qui", C, "Advanced Data Processing with Spark - reposição do dia 22/09", ""]],
    D10: [["30/09/2026", "Qua", A, "Workshop de Abertura", ""]],
}


def _svc(*, rules: str = _RULES, faculty_tab: "list[list[str]] | None" = None,
         today: date = date(2026, 9, 22)) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    for sid, rows in _SHEETS.items():
        store.put(sid, "Secretaria", [_HEADER] + rows)
        if faculty_tab is not None:
            store.put(sid, "Informacoes Adicionais", faculty_tab)
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: today)


def _tool(svc: CoordinatorService, name: str = "estimate_professor_pay"):
    return build_server(svc)._tool_manager._tools[name].fn


# ── what the three turns recorded: the STATE this change starts from ──────────────────
#: The refusal a non-oversight caller gets today for naming anybody else — captured off
#: ``origin/main`` (b9ac6f5) BEFORE this change, and compared as a literal so that the
#: sentence cannot drift while the widening lands beside it.
REFUSAL_TODAY = ("You can only see your own pay estimate — another professor's remuneration is "
                 "not something this assistant discloses to anyone.")
NOT_PERMITTED_TODAY = (f"NOT PERMITTED: {REFUSAL_TODAY} This is an access rule working as "
                       f"intended, not a failure — state the limit plainly and offer what IS "
                       f"allowed.")
NOTHING_TO_ESTIMATE = ("No classes found for this period, so there is nothing to estimate. Say "
                       "that plainly — it is an answer, not a failure.")


def _owned(block: str, name: str) -> str:
    """``block`` as recorded, plus the ONE line the ownership header adds under its title."""
    title, rest = block.split("\n", 1)
    return f"{title}\nProfessor: {name}\n{rest}"


def _nothing_for(name: str) -> str:
    """The empty answer, owned: the same 117-char sentence with WHOSE period was empty."""
    return NOTHING_TO_ESTIMATE.replace("found for this period", f"found for {name} for this period")


#: Turn 115's ``estimate_professor_pay(period="2026-09", professor="")`` — 847 chars, the
#: SUPERVISOR's own two class groups and nobody else's, under a header that does not say so.
TURN_115_BLOCK = """*Remuneração estimada — September 2026*
Valor/hora declarado nas regras: R$ 120,00
Horas por aula declaradas nas regras: 4 h

*Turma DE_09 — 09/2026*
NoSQL and Distributed Databases · 2 aulas · 8 h · R$ 960,00

*Turma DE_10 — 09/2026*
Workshop de Abertura · 1 aula · 4 h · R$ 480,00

*Base*
12 h · R$ 1.440,00

*Bônus IBOPE — RESULTADO NÃO ENCONTRADO*
O resultado do IBOPE não foi encontrado, então o bônus não pode ser calculado. Estas são as hipóteses previstas pelas regras — nenhuma delas foi escolhida e nenhuma foi verificada:
Sem bônus · sem adicional · R$ 1.440,00
IBOPE 80–89% · +R$ 30,00/h · R$ 1.800,00
IBOPE 90%+ · +R$ 40,00/h · R$ 1.920,00

Condição das regras: o bônus só é devido se o IBOPE tiver sido respondido por pelo menos 30% da turma. Este sistema não lê essa taxa — confirme com a secretaria antes de contar com o adicional."""
#: Turn 115's master listing for September (1256 chars) — every line ``dd/mm · turma ·
#: disciplina``, and not one professor in it.
TURN_115_LISTING = """*Setembro de 2026*
- 01/09 · Turma DE_09 · Python Programming for Data Engineers
- 02/09 · Turma DSA_33 · Integrated Data Platforms and Processing with Spark
- 03/09 · Turma DE_09 · NoSQL and Distributed Databases
- 07/09 · Turma DSA_33 · Feriado - Independência do Brasil
- 08/09 · Turma DE_09 · NoSQL and Distributed Databases
- 09/09 · Turma DSA_33 · Microservices Architecture
- 10/09 · Turma DE_09 · Python Programming for Data Engineers
- 14/09 · Turma DSA_33 · Integrated Data Platforms and Processing with Spark - Aula adiada
- 15/09 · Turma DE_09 · Advanced Data Processing with Spark
- 16/09 · Turma DSA_33 · Microservices Architecture
- 17/09 · Turma DE_09 · Python Programming for Data Engineers
- 21/09 · Turma DSA_33 · Integrated Data Platforms and Processing with Spark
- 22/09 · Turma DE_09 · Advanced Data Processing with Spark - Aula Adiada
- 23/09 · Turma DSA_33 · Integrated Data Platforms and Processing with Spark - reposição do dia 14/09
- 24/09 · Turma DE_09 · Python Programming for Data Engineers
- 28/09 · Turma DSA_33 · Integrated Data Platforms and Processing with Spark
- 29/09 · Turma DE_09 · Advanced Data Processing with Spark
- 30/09 · Turma DSA_33 · Microservices Architecture
- 30/09 · Turma DE_10 · Workshop de Abertura"""


def test_the_fixture_IS_the_tenants_september_turn_115s_block_plus_ONE_line_saying_whose():
    """The pin that makes every other pin here mean something: the SUPERVISOR's ``professor=""``
    estimate for 2026-09 renders the 847 characters turn 115 recorded — his OWN two groups,
    12 h · R$ 1.440,00 — over a schedule that holds two other professors' classes, plus
    exactly ONE line: ``Professor: Professor A``, the ownership header. That is hole (a),
    reproduced and closed in the same assertion: the number is still one person's (turn 114's,
    the same call as EMPLOYEE, byte for byte), and the block now says so."""
    out = _tool(_svc())(period="2026-09", professor="", **SUPERVISOR)
    assert out == _owned(TURN_115_BLOCK, A)
    assert len(TURN_115_BLOCK) == 847                     # the recorded block, as it was
    assert out.splitlines()[1] == f"Professor: {A}"       # and the one line it gained
    owner = len(f"Professor: {A}\n")
    # turn 111, once per class group: 769 and 753 chars recorded, and the 117-char nothing
    assert len(_tool(_svc())(period="2026-09", turma="DE_09", **SUPERVISOR)) == 769 + owner
    assert len(_tool(_svc())(period="2026-09", turma="DE_10", **SUPERVISOR)) == 753 + owner
    assert _tool(_svc())(period="2026-09", turma="DSA_33", **SUPERVISOR) == _nothing_for(A)
    assert len(NOTHING_TO_ESTIMATE) == 117
    # …and turn 114's "minhas aulas" figures ARE those: the same call as EMPLOYEE, byte for byte
    assert _tool(_svc())(period="2026-09", professor="", **EMPLOYEE) == out


def test_the_faculty_tab_was_EMPTY_on_all_three_turns_and_the_code_must_keep_working_over_it():
    """Hole (b): "No faculty records found." — the declared tab matched nothing. Pinned so the
    grouping tests below are known to run over an empty tab, which is the live shape."""
    assert _tool(_svc(), "get_professor_info")(professor="", **SUPERVISOR) == \
        "No faculty records found."


# ── twin 111/112: «os valores de todos os professores» → one block PER professor ─────────
def test_ALL_PROFESSORS_answers_the_supervisor_with_one_block_per_professor_and_a_LABELLED_total():
    """Turns 111 and 112 asked for everyone and got one person; ``professor="*"`` now answers
    with a block per professor — keyed on the SCHEDULE's professor column, the faculty tab
    being empty — and a total that says how many people it sums. The two colleagues' figures
    are pairwise different from the supervisor's own, so a block relayed under the wrong name
    cannot pass by coincidence."""
    fac = _svc().estimate_faculty_pay(period="2026-09", **SUPERVISOR)
    assert isinstance(fac, FacultyPayEstimate)
    assert [e.professor for e in fac.estimates] == [A, B, C]
    by = {e.professor: e for e in fac.estimates}
    assert (by[A].hours, by[A].base) == (12, 1440.0)      # turn 115's own figures, now named
    # B and C each have ONE class the sheet annotates «- Aula adiada», and a make-up row that
    # names its date. This file used to pin 36 h / R$ 4.320,00 and 24 h / R$ 2.880,00 — the
    # postponed class paid, and so did the make-up, so one class was bought twice. The
    # docstring above says this fixture IS the tenant's September, which made the pin a test
    # DEFENDING the defect: see ``test_a_postponed_class_and_its_make_up_are_ONE_class_paid_ONCE``.
    assert (by[B].hours, by[B].base) == (32, 3840.0)      # 4 Python + 5 Spark, ONE of them adiada
    assert (by[C].hours, by[C].base) == (20, 2400.0)      # 3 Microservices + 3 Spark, one adiada
    assert (fac.hours, fac.base) == (64, 7680.0)          # was 72 h / R$ 8.640,00 — R$ 960,00 less
    assert fac.unassigned_classes == 1                    # the holiday row: dated, no professor

    block = render_faculty_pay_block(fac)
    assert block.startswith("*Remuneração estimada — todos os professores — September 2026*\n")
    heads = [ln for ln in block.splitlines() if ln.startswith("*Professor: ")]
    assert heads == [f"*Professor: {A}*", f"*Professor: {B}*", f"*Professor: {C}*"]
    # each professor's section carries THEIR figures, in name order
    a, b, c = (block.index(h) for h in heads)
    assert a < block.index("12 h · R$ 1.440,00") < b
    assert b < block.index("32 h · R$ 3.840,00") < c
    assert c < block.index("20 h · R$ 2.400,00")
    assert "*Total (3 professores)*\nBase: 64 h · R$ 7.680,00" in block
    # the bonus is OPEN for all three (no IBOPE result), so no total with bonus is invented
    assert f"Com bônus: não somado — o bônus de {A}, {B}, {C} está em aberto" in block
    assert "Sem professor na agenda: 1 aula" in block
    # the tool relays exactly that block
    assert _tool(_svc())(period="2026-09", professor=ALL_PROFESSORS, **SUPERVISOR) == block


def test_the_grand_total_is_NEVER_a_bare_sum():
    """The mutation this exists to kill: ``"*"`` returning one estimate over everybody's rows.
    The faculty figure appears ONCE, on a line that names what it sums, under a header that
    counts the people — and the block per professor precedes it."""
    block = render_faculty_pay_block(_svc().estimate_faculty_pay(period="2026-09", **SUPERVISOR))
    lines = block.splitlines()
    where = [i for i, ln in enumerate(lines) if "R$ 7.680,00" in ln]
    assert len(where) == 1
    assert lines[where[0]].startswith("Base: ")
    assert lines[where[0] - 1] == "*Total (3 professores)*"
    assert block.count("*Professor: ") == 3
    assert "*Base*\n64 h" not in block                    # no professor's block holds the sum


def test_a_professor_with_no_class_in_the_period_appears_with_ZERO_classes_not_in_silence():
    """The faculty tab names a fourth professor who teaches nothing in September (and
    nothing in the schedule at all). A total that quietly omits a name reads as "not paid":
    the block carries the name and says «0 aulas»."""
    tab = [["Disciplina", "CH", "Professor", "e-mail"],
           ["Redes", "40", "Professor D", "d@example.com"],
           ["Redes", "40", A, "a@example.com"]]
    fac = _svc(faculty_tab=tab).estimate_faculty_pay(period="2026-09", **SUPERVISOR)
    assert [e.professor for e in fac.estimates] == [A, B, C, "Professor D"]
    assert fac.estimates[-1].groups == [] and fac.estimates[-1].hours == 0
    block = render_faculty_pay_block(fac)
    assert f"*Professor: Professor D*\n{NO_CLASSES_LINE}" in block
    assert "0 aulas" in NO_CLASSES_LINE
    assert "*Total (4 professores)*\nBase: 64 h · R$ 7.680,00" in block   # unchanged by a zero
    assert "@" not in block                               # the tab's e-mail never rides out


def test_the_total_WITH_bonus_is_stated_only_when_every_professors_bonus_is_determined():
    """One IBOPE tab, every professor with a result: A applied (85 → +30/h), B applied (92 →
    +40/h), C below every band (70 → zero, an apurado fact). Then the total with bonus exists
    and is the sum of the three; leave ONE professor without a result and it is withheld
    naming that professor."""
    rules = _RULES + 'TAB_IBOPE: "Resultados IBOPE"\nCOLUMN_IBOPE: "Resultado"\n'
    svc = _svc(rules=rules)
    svc.store.put(S33, "Resultados IBOPE", [["Professor", "Resultado"], [A, "85"], [B, "92"], [C, "70"]])
    fac = svc.estimate_faculty_pay(period="2026-09", **SUPERVISOR)
    assert fac.undetermined == ()
    assert fac.total_with_bonus == pytest.approx(7680 + 12 * 30 + 32 * 40 + 0)
    assert "Com bônus: R$ 9.320,00" in render_faculty_pay_block(fac)

    svc.store.put(S33, "Resultados IBOPE", [["Professor", "Resultado"], [A, "85"], [C, "70"]])
    fac = svc.estimate_faculty_pay(period="2026-09", **SUPERVISOR)
    assert fac.undetermined == (B,)
    assert fac.total_with_bonus is None
    assert f"Com bônus: não somado — o bônus de {B} está em aberto" in render_faculty_pay_block(fac)


# ── twin 111 by name: «quanto recebe o professor B» → THAT professor, named in the block ──
@pytest.mark.parametrize("role", ["SUPERVISOR", "ADMIN", "OWNER"])
def test_an_oversight_role_naming_a_professor_gets_THAT_professors_estimate_with_the_name_on_it(role):
    est = _svc().estimate_professor_pay(professor=B, period="2026-09", identity_label=A, role=role)
    assert est.professor == B
    assert (est.hours, est.base) == (32, 3840.0)     # one of B's Spark classes is «- Aula adiada»
    block = render_pay_block(est)
    assert block.splitlines()[:2] == ["*Remuneração estimada — September 2026*", f"Professor: {B}"]
    assert "*Turma DE_09 — 09/2026*\nPython Programming for Data Engineers · 4 aulas · 16 h · R$ 1.920,00" in block
    assert A not in block                                 # the caller's own name is not on it


def test_the_name_is_resolved_exactly_as_the_listing_resolves_it_folded_substring_no_more_no_less():
    """``_visible`` matches an accent-stripped, case-folded SUBSTRING and nothing fuzzier.
    "professor c" and "PROFESSOR C" reach C; "Professor Ç" does too (the fold); a typo does
    not — the listing would show nothing for it, and the estimate refuses rather than
    guessing whom a wrong spelling meant."""
    svc = _svc()
    for spelling in ("professor c", "PROFESSOR C", "Professor Ç", "sor C"):
        assert svc.estimate_professor_pay(professor=spelling, period="2026-09", **SUPERVISOR).professor == C
    with pytest.raises(CoordinatorError) as exc:
        svc.estimate_professor_pay(professor="Profesor X", period="2026-09", **SUPERVISOR)
    assert 'No professor matching "Profesor X"' in str(exc.value)
    # and the classes read are the ones the listing shows for that name — MINUS the rows the
    # sheet annotates as not given. The listing keeps showing the postponed class, on purpose:
    # a professor reading their month has to see the day that did not happen, and the words
    # «- Aula Adiada» are on the line. The estimate counts what was TAUGHT, so of C's six
    # September rows five are paid and the sixth is paid on its make-up date instead.
    listed = svc.get_professor_schedule(professor=C, month="2026-09", include_past=True,
                                        apply_horizon=False, **SUPERVISOR)
    est = svc.estimate_professor_pay(professor=C, period="2026-09", **SUPERVISOR)
    assert len(listed) == 6
    assert sum(1 for e in listed if e.is_postponed) == 1
    assert sum(ln.classes for g in est.groups for ln in g.lines) == len(listed) - 1 == 5


def test_a_name_that_matches_TWO_professors_is_refused_never_summed():
    """"Professor" is inside all three names. The listing would show three people's lines,
    each named; the estimate would sum three people under one header — the bare-sum defect in
    a new coat — so it refuses and names the candidates."""
    with pytest.raises(CoordinatorError) as exc:
        _svc().estimate_professor_pay(professor="Professor", period="2026-09", **SUPERVISOR)
    msg = str(exc.value)
    assert '"Professor" matches 3 professors' in msg
    assert A in msg and B in msg and C in msg
    assert "R$" not in msg


def test_a_named_professor_with_no_class_in_the_period_is_answered_by_name():
    out = _tool(_svc())(professor=B, period="2026-12", **SUPERVISOR)
    assert out == (f"No classes found for {B} for this period, so there is nothing to estimate. "
                   f"Say that plainly — it is an answer, not a failure.")
    # the caller's own empty period is owned too — turns 111/112 relayed this sentence, asked
    # once per class group with ``professor=""``, as «DSA_33: nenhuma aula encontrada» in a
    # table about the faculty; it was the caller's empty group, and now it says so
    assert _tool(_svc())(professor="", period="2026-12", **SUPERVISOR) == _nothing_for(A)


# ── the OWNERSHIP header: every estimate says whose it is ────────────────────────────────
def test_every_estimate_block_carries_the_ownership_header_own_by_name_and_all():
    """The owner's confirmation, textual: «um valor sem dono é tão perigoso como um valor sem
    leitura». Own → the caller's label; by name → the sheet's spelling; ``"*"`` → one header
    per professor and a total that counts them. A block with no second line naming a person
    no longer exists on any door."""
    svc = _svc()
    own = render_pay_block(svc.estimate_professor_pay(professor="", period="2026-09", **EMPLOYEE))
    assert own.splitlines()[1] == f"Professor: {A}"
    named = render_pay_block(svc.estimate_professor_pay(professor="professor b", period="2026-09",
                                                        **SUPERVISOR))
    assert named.splitlines()[1] == f"Professor: {B}"    # the sheet's spelling, not the query's
    everyone = render_faculty_pay_block(svc.estimate_faculty_pay(period="2026-09", **SUPERVISOR))
    assert everyone.count("*Professor: ") == 3 and "*Total (3 professores)*" in everyone
    # the label is the CALLER's, as the host stamps it — not looked up on the sheet
    other_label = render_pay_block(svc.estimate_professor_pay(
        professor="", period="2026-09", identity_label="Professor A", role="OWNER"))
    assert other_label.splitlines()[1] == "Professor: Professor A"
    # and an estimate assembled with no owner (a hand-built value) renders no ownership line
    from cogno_praxis.coordinator import PayEstimate
    assert "Professor:" not in render_pay_block(PayEstimate(rate=120.0, hours_per_class=4.0))


# ── the half that did NOT move: GUEST/EMPLOYEE are self-only, byte for byte ─────────────
@pytest.mark.parametrize("role", ["", "GUEST", "EMPLOYEE"])
@pytest.mark.parametrize("who", [B, ALL_PROFESSORS])
def test_a_non_oversight_caller_asking_for_anybody_else_or_everyone_gets_TODAYS_refusal(role, who):
    """Both doors, both layers, one sentence — the literal captured off main before the
    change. The mutation «EMPLOYEE also sees another» dies here."""
    with pytest.raises(CoordinatorAccessError) as exc:
        _svc().estimate_professor_pay(professor=who, period="2026-09", identity_label=A, role=role)
    assert str(exc.value) == REFUSAL_TODAY
    assert _tool(_svc())(professor=who, period="2026-09", identity_label=A, role=role) \
        == NOT_PERMITTED_TODAY
    if who == ALL_PROFESSORS:
        with pytest.raises(CoordinatorAccessError) as exc:
            _svc().estimate_faculty_pay(period="2026-09", identity_label=A, role=role)
        assert str(exc.value) == REFUSAL_TODAY


@pytest.mark.parametrize("role", ["", "GUEST", "EMPLOYEE", "SUPERVISOR", "ADMIN", "OWNER"])
def test_an_EMPTY_professor_is_STILL_the_caller_for_every_role_and_never_everyone(role):
    """The 2026-09-09 defect stays dead: ``""`` is "me". The SUPERVISOR's ``""`` renders turn
    115's block — one person's 12 h — and not the faculty's 72 h. The mutation «"" is everyone
    again» dies here."""
    est = _svc().estimate_professor_pay(professor="", period="2026-09", identity_label=A, role=role)
    assert (est.hours, est.base) == (12, 1440.0)
    assert est.professor == A                             # own: the caller's own label
    assert render_pay_block(est) == _owned(TURN_115_BLOCK, A)


def test_ALL_PROFESSORS_is_a_sentinel_the_single_estimate_redirects_not_a_name_it_looks_up():
    with pytest.raises(CoordinatorError) as exc:
        _svc().estimate_professor_pay(professor=ALL_PROFESSORS, period="2026-09", **SUPERVISOR)
    assert "estimate_faculty_pay" in str(exc.value)


# ── NOT CONFIGURED is the tenant's, once, for everybody ──────────────────────────────────
def test_NOT_CONFIGURED_names_the_key_for_the_faculty_estimate_too_one_configuration_serves_all():
    rules = _RULES.replace("HOURS_PER_CLASS: 4\n", "")
    with pytest.raises(CoordinatorConfigError) as exc:
        _svc(rules=rules).estimate_faculty_pay(period="2026-09", **SUPERVISOR)
    assert "HOURS_PER_CLASS is missing" in str(exc.value)
    out = _tool(_svc(rules=rules))(professor=ALL_PROFESSORS, period="2026-09", **SUPERVISOR)
    assert out.startswith("NOT CONFIGURED:") and "HOURS_PER_CLASS" in out and "R$" not in out
    by_name = _tool(_svc(rules=rules))(professor=B, period="2026-09", **SUPERVISOR)
    assert by_name.startswith("NOT CONFIGURED:") and "HOURS_PER_CLASS" in by_name


# ── twin 115: the supervision agenda names the professor on every line ────────────────────
def test_the_supervisors_master_listing_names_the_professor_on_every_line_and_ONLY_adds_that():
    """Hole (c). The listing of turn 115 — the 1256 characters, with no professor anywhere —
    is exactly what the new listing becomes once each line's `` · Professor: <name>`` is
    stripped: nothing else moved. The holiday row has no professor on the sheet and gets no
    part. The mutation «line without professor» dies here."""
    out = _tool(_svc(), "get_professor_schedule")(month="2026-09", include_past=True, professor="",
                                                   **SUPERVISOR)
    lines = out.splitlines()
    named = [ln for ln in lines if " · Professor: " in ln]
    assert len(named) == 18 and len([ln for ln in lines if ln.startswith("- ")]) == 19
    assert "- 07/09 · Turma DSA_33 · Feriado - Independência do Brasil" in lines
    assert "- 03/09 · Turma DE_09 · NoSQL and Distributed Databases · Professor: Professor A" in lines
    assert "- 30/09 · Turma DSA_33 · Microservices Architecture · Professor: Professor C" in lines
    stripped = "\n".join(ln.split(" · Professor: ")[0] for ln in lines)
    assert stripped == TURN_115_LISTING
    assert len(TURN_115_LISTING) == 1256


def test_a_professor_reading_their_OWN_list_and_a_supervisor_reading_ONE_professor_are_byte_identical_to_before():
    """The two controls: the professor is the professor on every line, so naming them is the
    year repeating under its header. Neither list carries a ``Professor:`` part, and the
    supervisor's one-professor list equals that professor's own."""
    own = _tool(_svc(), "get_professor_schedule")(month="2026-09", include_past=True, professor="",
                                                   identity_label=B, role="EMPLOYEE")
    one = _tool(_svc(), "get_professor_schedule")(month="2026-09", include_past=True, professor=B,
                                                   **SUPERVISOR)
    assert own == one
    assert "Professor:" not in own
    assert own.count("\n- ") + own.startswith("- ") == 9
    assert "- 01/09 · Turma DE_09 · Python Programming for Data Engineers" in own.splitlines()


def test_every_list_tool_names_the_professor_for_a_supervisor_when_the_list_covers_several():
    """One renderer, one rule — the weekly briefing and the daily digest of a coordinator are
    the same list a turn later, and a coordinator who cannot tell whose class is whose on
    Monday's briefing is the same defect as turn 112."""
    svc = _svc(today=date(2026, 9, 21))                   # week of 21/09: B and C both teach
    week = _tool(svc, "get_weekly_briefing")(professor="", **SUPERVISOR)
    assert " · Professor: Professor B" in week and " · Professor: Professor C" in week
    own_week = _tool(svc, "get_weekly_briefing")(professor="", identity_label=B, role="EMPLOYEE")
    assert "Professor:" not in own_week
    # the daily digest on 30/09: two classes today, two professors → both named; on 21/09 one
    # class today, one professor → the section is that person's and stays bare (the rule is
    # about the LIST rendered, section by section, not about the caller alone)
    two = _tool(_svc(today=date(2026, 9, 30)), "daily_checks")(professor="", **SUPERVISOR)
    assert "- 30/09 · Turma DSA_33 · Microservices Architecture · Professor: Professor C" in two
    assert "- 30/09 · Turma DE_10 · Workshop de Abertura · Professor: Professor A" in two
    one = _tool(svc, "daily_checks")(professor="", **SUPERVISOR)
    today_section = one.split("\n\n")[0]
    assert today_section.endswith("- 21/09 · Turma DSA_33 · Integrated Data Platforms and Processing with Spark")
    assert "Professor:" not in today_section
    # …while the deadline section of the SAME digest, which spans several professors, is named
    assert " · Professor: Professor B" in one


# ── the tool's contract says the two halves ──────────────────────────────────────────────
def test_the_tool_docstring_states_both_halves_own_for_all_by_name_or_all_for_the_coordination():
    desc = " ".join(build_server(_svc())._tool_manager._tools["estimate_professor_pay"].description.split())
    assert "``professor`` EMPTY is the CALLER'S OWN pay, for every role" in desc
    assert '``professor="*"``, ONE block PER PROFESSOR' in desc
    assert "A professor who is not the coordination gets NOT PERMITTED" in desc
