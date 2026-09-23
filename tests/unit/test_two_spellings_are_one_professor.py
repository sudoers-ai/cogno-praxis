"""One person, one block — and the join is said out loud, or it does not happen.

The schedule spells a professor's name more than one way, and the faculty-wide estimate was
keyed on the spelling: two blocks of half the pay each, and asking for either name by hand
returned that half under a header carrying the person's name, with nothing anywhere to say the
other half existed. Measured on the first real use of the supervision: the faculty TOTAL was
right — every class counted once — and the per-person view, which is the one somebody pays
from, was not.

**Two layers, and neither of them guesses.**

1. The CAST is the tenant's professors tab. Two rows are one person when they share an e-mail
   address AND one name is the other written out more fully. The address is CORROBORATION, not
   AUTHORITY: it is a cell a human types, and a departmental mailbox on two rows would
   otherwise fuse two colleagues into one payment.
2. A spelling off the SCHEDULE resolves against that cast — same first name, every word of it
   present in the declared one — and ONLY when exactly one declared person fits.

There is no ``difflib`` in any of it, no edit distance, no threshold of resemblance. Comparing
spellings pairwise gives a rule whose safety has to be ARGUED; resolving against a closed,
declared set gives one whose safety can be COUNTED, and the two twins below — an ambiguous
spelling, and a shared address the names do not corroborate — are what turn the zeroes in
today's data into conditions of the system.

Every name here is invented. The FORMS are the tenant's: an abbreviation that drops the family
name, two different abbreviations of one person, a family name misspelt by a letter, and a
shared address.
"""

from __future__ import annotations

from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    render_faculty_pay_block,
)

SID = "H" * 24
_RULES = f"""SPREADSHEETS:
Turma DSA_33 = {SID}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:E110"
TAB_PROFESSORS: "Informacoes Adicionais"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
_TAB_HEADER = ["Disciplina", "CH", "Professor", "e-mail"]
OVERSIGHT = {"identity_label": "Coordenação", "role": "SUPERVISOR"}

# The declared people. HELENA is written out in full; the schedule abbreviates her by dropping
# the family name — the commonest abbreviation there is, and the one a rule requiring the last
# token to agree would miss. TOMAS is abbreviated two different ways, each keeping a different
# half. ROSA's family name is misspelt by one letter on one schedule row.
HELENA = "Helena Quintar Bonfim"
TOMAS = "Tomás Nogueira de Alvim Prado"
ROSA = "Rosa Valdemar Pinho"

FACULTY = [_TAB_HEADER,
           ["Estatística", "40", HELENA, "helena.q@example.edu"],
           ["Álgebra", "40", TOMAS, "tomas.nap@example.edu"],
           ["Redes", "40", ROSA, "rosa.vp@example.edu"]]


def _svc(rows: "list[list[str]]", faculty: "list[list[str]] | None" = None,
         *, today: date = date(2026, 9, 30)) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(SID, "Secretaria", [_HEADER] + rows)
    if faculty is not None:
        store.put(SID, "Informacoes Adicionais", faculty)
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: today)


def _class(day: str, professor: str) -> list[str]:
    return [f"{day}/09/2026", "Qua", professor, "Estatística", ""]


def _blocks(svc: CoordinatorService):
    fac = svc.estimate_faculty_pay(period="2026-09", **OVERSIGHT)
    return fac, {e.professor: e for e in fac.estimates}


# ── the join, and the line that says it happened ──────────────────────────────────────
def test_an_abbreviation_that_DROPS_THE_FAMILY_NAME_is_the_same_person():
    """The shape a rule requiring the last token would miss — and it is the commonest one.
    «Helena Quintar» on two rows and «Helena Quintar Bonfim» on one are one person with three
    classes, under the spelling the tenant declared."""
    rows = [_class("02", "Helena Quintar"), _class("09", "Helena Quintar"),
            _class("16", HELENA)]
    fac, by = _blocks(_svc(rows, FACULTY))
    assert [e.professor for e in fac.estimates] == [HELENA, ROSA, TOMAS]
    assert (by[HELENA].hours, by[HELENA].base) == (12, 1440.0)
    assert by[HELENA].variants == ("Helena Quintar",)


def test_the_join_is_RENDERED_so_the_person_paying_can_see_which_spellings_were_summed():
    """A merge a reader cannot see is a merge they cannot undo. The block says which spellings
    it read as one person, in the reply itself — not in a log, not in a field nobody renders."""
    rows = [_class("02", "Helena Quintar"), _class("09", HELENA)]
    block = render_faculty_pay_block(_svc(rows, FACULTY).estimate_faculty_pay(
        period="2026-09", **OVERSIGHT))
    assert f"*Professor: {HELENA}*\nInclui linhas grafadas “Helena Quintar” — somadas como a " \
           f"mesma pessoa." in block
    # and the figure it is attached to is the WHOLE month, not half of it
    assert "8 h · R$ 960,00" in block


def test_TWO_DIFFERENT_ABBREVIATIONS_of_one_declared_person_both_resolve_to_them():
    """Each cuts a different half of the declared name, and pairwise they look like two
    colleagues who merely share a first name. Anchored to the cast, both are the person the
    tenant declared — and neither is ever compared to the other."""
    rows = [_class("02", "Tomás Nogueira"), _class("09", "Tomás Alvim"), _class("16", TOMAS)]
    fac, by = _blocks(_svc(rows, FACULTY))
    assert [e.professor for e in fac.estimates] == [HELENA, ROSA, TOMAS]
    assert (by[TOMAS].hours, by[TOMAS].base) == (12, 1440.0)
    assert by[TOMAS].variants == ("Tomás Alvim", "Tomás Nogueira")


def test_a_FAMILY_NAME_MISSPELT_BY_A_LETTER_is_NOT_joined_and_the_block_says_who_it_may_be():
    """«Rosa Valdemer Pinho» against the declared «Rosa Valdemar Pinho». To any measure of
    resemblance this is indistinguishable from two colleagues with similar names, and joining
    on resemblance pays one person for another's classes in a figure that reads as finished.
    So it is NOT joined: two blocks, and each names the other. The sum is SHORT by one class
    and says why, which is the direction a wrong answer about somebody's pay may be wrong in."""
    rows = [_class("02", ROSA), _class("09", "Rosa Valdemer Pinho")]
    fac, by = _blocks(_svc(rows, FACULTY))
    assert "Rosa Valdemer Pinho" in by and ROSA in by
    assert (by[ROSA].hours, by["Rosa Valdemer Pinho"].hours) == (4, 4)
    assert by["Rosa Valdemer Pinho"].maybe_same == (ROSA,)
    block = render_faculty_pay_block(fac)
    assert f"Atenção: “{ROSA}” pode ser a mesma pessoa — não foi somado aqui." in block
    # parked by name in the PR body: the tenant declares the two spellings, or nothing joins
    assert by[ROSA].variants == () and by["Rosa Valdemer Pinho"].variants == ()


# ── layer one: the professors tab, joined by a corroborated address ───────────────────
def test_the_TAB_joins_two_spellings_of_one_person_by_a_SHARED_E_MAIL_plus_containment():
    """The tenant declares the same person twice, once in full and once short, on one address.
    Both halves are required and both are satisfied, so the cast holds ONE person — and the
    schedule's rows under either spelling land on them."""
    faculty = [_TAB_HEADER,
               ["Estatística", "40", "Íris Calheiros Amado", "iris@example.edu"],
               ["Redes", "40", "Íris Calheiros", "iris@example.edu"]]
    rows = [_class("02", "Íris Calheiros"), _class("09", "Íris Calheiros Amado")]
    fac, by = _blocks(_svc(rows, faculty))
    assert [e.professor for e in fac.estimates] == ["Íris Calheiros Amado"]
    assert (fac.hours, fac.base) == (8, 960.0)
    assert by["Íris Calheiros Amado"].variants == ("Íris Calheiros",)
    # the address is read, compared, and dropped — it never reaches the block
    assert "@" not in render_faculty_pay_block(fac)


def test_TWIN_a_shared_address_the_NAMES_DO_NOT_CORROBORATE_joins_NOTHING_and_warns():
    """Two colleagues on a departmental mailbox. The address says one thing and the names say
    another, and the address does not win: a join here would pay one of them for the other's
    classes, silently. Two blocks, each naming the other, and the figures stay apart.

    Nothing in today's data takes this branch — it is a condition of the system, not a
    correction of a figure — which is exactly why it needs a test rather than a sentence."""
    faculty = [_TAB_HEADER,
               ["Estatística", "40", "Nuno Prata", "secretaria@example.edu"],
               ["Redes", "40", "Nuno Ferraz", "secretaria@example.edu"]]
    rows = [_class("02", "Nuno Prata"), _class("09", "Nuno Ferraz")]
    fac, by = _blocks(_svc(rows, faculty))
    assert sorted(by) == ["Nuno Ferraz", "Nuno Prata"]
    assert (by["Nuno Prata"].hours, by["Nuno Ferraz"].hours) == (4, 4)
    assert by["Nuno Prata"].maybe_same == ("Nuno Ferraz",)
    assert by["Nuno Ferraz"].maybe_same == ("Nuno Prata",)
    assert "pode ser a mesma pessoa" in render_faculty_pay_block(fac)


# ── layer two: UNIQUE is a condition, not a description of today's data ───────────────
def test_TWIN_a_spelling_that_fits_TWO_declared_people_is_REFUSED_and_both_are_named():
    """The cast gains a second person the abbreviation also fits. There is no tie to break
    here — two people fit and this cannot know which — so the spelling keeps its own block,
    names both candidates, and nobody is paid for anybody else's class.

    This is the twin that makes "exactly one" a CONDITION. Without it, the uniqueness in the
    tenant's current data would be a coincidence the tests happened to record."""
    twin = "Helena Quintar Medeiros"
    faculty = FACULTY + [["Cálculo", "40", twin, "helena.qm@example.edu"]]
    rows = [_class("02", "Helena Quintar"), _class("09", HELENA), _class("16", twin)]
    fac, by = _blocks(_svc(rows, faculty))
    assert "Helena Quintar" in by                          # its own block, joined to neither
    assert by["Helena Quintar"].maybe_same == (HELENA, twin)
    assert by[HELENA].hours == 4 and by[twin].hours == 4 and by["Helena Quintar"].hours == 4
    block = render_faculty_pay_block(fac)
    assert f"Atenção: “{HELENA}”, “{twin}” pode ser a mesma pessoa" in block


# ── the controls ─────────────────────────────────────────────────────────────────────
def test_the_TOTAL_IN_REAIS_IS_IDENTICAL_before_and_after_the_join():
    """The join moves classes between blocks; it never creates or destroys one. The faculty
    total is the same figure with the cast and without it — which is also the measured fact
    about the live defect: the total was right all along, and the per-person view was not."""
    rows = [_class("02", "Helena Quintar"), _class("09", HELENA), _class("16", "Tomás Alvim")]
    without = _svc(rows).estimate_faculty_pay(period="2026-09", **OVERSIGHT)
    with_cast = _svc(rows, FACULTY).estimate_faculty_pay(period="2026-09", **OVERSIGHT)
    assert (without.hours, without.base) == (12, 1440.0)
    assert (with_cast.hours, with_cast.base) == (without.hours, without.base)
    assert len(without.estimates) == 3 and len(with_cast.estimates) == 3   # 3 spellings, 3 people
    assert with_cast.unassigned_classes == without.unassigned_classes


def test_a_tenant_whose_data_holds_NO_VARIANTS_renders_BYTE_IDENTICALLY():
    """The control that keeps this from being a change to everybody's reply. With no variant to
    join and nobody to warn about, the block is the one the tenant already reads — byte for
    byte, whether or not a professors tab exists at all."""
    rows = [_class("02", HELENA), _class("09", TOMAS), _class("16", ROSA)]
    declared = render_faculty_pay_block(
        _svc(rows, FACULTY).estimate_faculty_pay(period="2026-09", **OVERSIGHT))
    undeclared = render_faculty_pay_block(
        _svc(rows).estimate_faculty_pay(period="2026-09", **OVERSIGHT))
    assert declared == undeclared
    assert "Inclui linhas grafadas" not in declared
    assert "pode ser a mesma pessoa" not in declared


def test_NOTHING_JOINS_WITHOUT_A_DECLARATION_and_the_empty_tab_is_the_live_shape():
    """The professors tab was EMPTY on the three live turns this feature comes from — the
    declared tab name matched no sheet. With no cast there is no candidate to name and no
    person to resolve against, so every spelling keeps its block and not one note is printed.
    Inventing a join out of the schedule alone is the pairwise guessing this design refuses."""
    rows = [_class("02", "Helena Quintar"), _class("09", HELENA)]
    fac, by = _blocks(_svc(rows))
    assert sorted(by) == ["Helena Quintar", HELENA]
    assert all(e.variants == () and e.maybe_same == () for e in fac.estimates)


# ── asking BY NAME: the door that returned half a month ───────────────────────────────
def test_asking_BY_EITHER_SPELLING_answers_with_the_WHOLE_month_under_the_declared_name():
    """The measured defect at the by-name door: a two-word spelling is not a substring of the
    four-word one it abbreviates, so asking by the short spelling matched only the short rows
    and returned HALF the remuneration, under a header carrying the person's name and no
    warning. Either spelling now answers with every class, under the declared name."""
    rows = [_class("02", "Helena Quintar"), _class("09", HELENA)]
    svc = _svc(rows, FACULTY)
    for asked in ("Helena Quintar", HELENA, "helena quintar", "Quintar"):
        est = svc.estimate_professor_pay(period="2026-09", professor=asked, **OVERSIGHT)
        assert est.professor == HELENA, asked
        assert (est.hours, est.base) == (8, 960.0), asked
        assert est.variants == ("Helena Quintar",), asked


def test_a_name_matching_TWO_PEOPLE_is_still_refused_never_summed():
    """Untouched and re-pinned: the refusal is now over PEOPLE rather than spellings, so two
    spellings of ONE person no longer read as an ambiguity — and two people still do."""
    import pytest
    rows = [_class("02", HELENA), _class("09", TOMAS)]
    with pytest.raises(Exception) as exc:
        _svc(rows, FACULTY).estimate_professor_pay(period="2026-09", professor="a", **OVERSIGHT)
    assert "matches 3 professors" in str(exc.value)
    assert "R$" not in str(exc.value)


# ── the mutations ────────────────────────────────────────────────────────────────────
def test_MUTATION_joining_by_FIRST_NAME_ALONE_pays_one_person_for_anothers_class():
    """Drop the containment and keep the first name, and a DIFFERENT person is swallowed.

    «Helena Marques» teaches one class and is nobody the tenant declared — she shares a first
    name with the declared «Helena Quintar Bonfim» and nothing else. The containment is what
    keeps them apart: her family name is not among his words. Without it she is a shorter name
    beginning "Helena", she is the unique declared Helena, and her class is paid into somebody
    else's block under somebody else's name — with a line asserting the two spellings are one
    person, which is the join saying something false rather than saying nothing."""
    from cogno_praxis.coordinator import service as mod
    other = "Helena Marques"
    rows = [_class("02", HELENA), _class("09", other)]
    fac, by = _blocks(_svc(rows, FACULTY))
    assert (by[HELENA].hours, by[other].hours) == (4, 4)   # the anchor: two people, one each
    assert by[HELENA].variants == ()

    original = mod._is_abbreviation_of
    try:
        mod._is_abbreviation_of = lambda short, full: (  # type: ignore[assignment]
            bool(short) and len(short) < len(full) and short[0] == full[0])
        _fac, mutated = _blocks(_svc(rows, FACULTY))
        assert other not in mutated                        # her block is gone
        assert mutated[HELENA].hours == 8                  # and her class is in his
        assert mutated[HELENA].variants == (other,)
    finally:
        mod._is_abbreviation_of = original                 # type: ignore[assignment]
    assert _blocks(_svc(rows, FACULTY))[1][other].hours == 4


def test_MUTATION_making_the_CANONICAL_the_SHORT_spelling_loses_the_declared_name():
    """The block must be headed with the name the tenant declared — it is what a payroll line
    carries and what the professors tab holds. Head it with the abbreviation and the twin
    dies."""
    rows = [_class("02", "Helena Quintar"), _class("09", HELENA)]
    fac, by = _blocks(_svc(rows, FACULTY))
    assert HELENA in by and "Helena Quintar" not in by     # the anchor
    assert by[HELENA].variants == ("Helena Quintar",)
    assert f"*Professor: {HELENA}*" in render_faculty_pay_block(fac)
    assert "*Professor: Helena Quintar*" not in render_faculty_pay_block(fac)


def test_MUTATION_a_join_that_does_NOT_SAY_SO_is_the_defect_wearing_a_correct_figure():
    """The rendered line is the condition the join is allowed under, so removing it is a
    regression even though every figure stays right: the reader is handed a sum over two
    spellings with nothing to tell them it happened, and no way to undo it."""
    rows = [_class("02", "Helena Quintar"), _class("09", HELENA)]
    fac, by = _blocks(_svc(rows, FACULTY))
    block = render_faculty_pay_block(fac)
    assert by[HELENA].base == 960.0                        # the figure is right either way
    assert "Inclui linhas grafadas “Helena Quintar”" in block
    # and it sits directly under the header it qualifies, before any figure
    lines = block.splitlines()
    at = lines.index(f"*Professor: {HELENA}*")
    assert lines[at + 1].startswith("Inclui linhas grafadas")
    assert block.index("Inclui linhas grafadas") < block.index("R$ 960,00")


def test_a_difference_of_CASE_between_the_two_sources_is_not_a_join_worth_announcing():
    """The tab shouts a name the schedule writes normally. That is ONE spelling folded two ways,
    not two spellings of one person, and a «these were summed as the same person» line over it
    would be a notice about nothing standing exactly where a real join has to be visible.

    The block is headed with the spelling the LISTING shows, which is the rule the universe
    already followed so that the estimate and the list say the same name."""
    faculty = [_TAB_HEADER, ["Estatística", "40", HELENA.upper(), "helena.q@example.edu"]]
    rows = [_class("02", HELENA), _class("09", HELENA)]
    fac, by = _blocks(_svc(rows, faculty))
    assert [e.professor for e in fac.estimates] == [HELENA]
    assert by[HELENA].variants == ()
    assert "Inclui linhas grafadas" not in render_faculty_pay_block(fac)
    # and a REAL variant beside it still announces itself
    fac2, by2 = _blocks(_svc(rows + [_class("16", "Helena Quintar")], faculty))
    assert by2[HELENA].variants == ("Helena Quintar",)
