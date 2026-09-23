"""The name a listing hands on has to be the name the next reader can look up.

The owner asked, naming nobody, for "the professor" to be warned. ``get_weekly_briefing`` read
the schedule and answered ``Professor: <the SPREADSHEET's spelling>``; the model took that
spelling and called the tool that notifies a person, which searches the identity DIRECTORY,
where the same professor is written another way. It found nobody — and asked the owner for the
full name of the man he had just asked us to warn. Run against the same directory afterwards:
the schedule's complete spelling finds nothing, not even a suggestion, and his bare FIRST NAME
finds him. The complete wrong spelling is worse than half a right one.

So the listing renders the CANONICAL spelling of the person, and no consumer downstream has to
learn how to resolve one. The resolution itself is three jumps over DECLARED data — no edit
distance, no ratio, no table of nicknames:

1. two faculty rows sharing an e-mail are one person (``#138``, reused here, not rewritten);
2. a schedule spelling nobody's name contains resolves by the INTERSECTION of two declared
   signals — who the faculty tab says teaches that DISCIPLINE, and who shares a TOKEN of the
   name — and only when exactly ONE is left;
3. (not this change) a person resolves to an identity by e-mail.

**And jump 2 decides a LABEL, never a sum.** Wired into the join itself it swallows a person
the tenant never declared into a declared professor's PAY — measured here, against ``#138``'s
own control, which is written about exactly that swallow and failed on its anchor. Nothing
structural separates a misspelling from a colleague who shares a first name and a discipline;
what separates the outcomes is the cost of being wrong. A wrong label puts a name on a line a
human reads; a wrong merge moves money with nothing on the page to show it. The classes stay
where they were and the pay block still says the two were not summed.

Every name here is invented. The FORMS are the tenant's: a family name the schedule misspells
by one letter, one professor on several tab rows (one per discipline), two colleagues sharing a
first name, and a discipline two people teach.
"""

from __future__ import annotations

import asyncio
from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    render_faculty_pay_block,
)
from cogno_praxis.coordinator import service as mod
from cogno_praxis.coordinator import server as srv
from cogno_praxis.coordinator.server import build_server

SID = "K" * 24
_RULES = f"""SPREADSHEETS:
Turma EST_21 = {SID}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:E110"
TAB_PROFESSORS: "Corpo Docente"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
_TAB_HEADER = ["Disciplina", "CH", "Professor", "e-mail"]
TODAY = date(2026, 10, 1)
OVERSIGHT = {"identity_label": "Coordenação", "role": "SUPERVISOR"}

# The declared people. TEIXEIRA is on TWO rows — the tab's unit is the discipline, not the
# person — and the SECOND of them carries the discipline this whole file turns on.
TEIXEIRA = "Romualdo da Silva Teixeira"
CORREIA = "Ivone Bastos Correia"
NUNES = "Romualdo Bettencourt Nunes"      # only in the WIDENED cast, for the ambiguity twin
ALGEBRA, ESTATISTICA, REDES = "Álgebra Linear", "Estatística Aplicada", "Redes Industriais"

FACULTY = [_TAB_HEADER,
           [ALGEBRA, "40", TEIXEIRA, "r.teixeira@example.edu"],
           [ESTATISTICA, "40", TEIXEIRA, "r.teixeira@example.edu"],
           [ESTATISTICA, "40", CORREIA, "i.correia@example.edu"],
           [REDES, "40", CORREIA, "i.correia@example.edu"]]

# The schedule's spelling of TEIXEIRA: the family name misspelt by one letter, which is a word
# his declared name does not carry — so no rule about MISSING words can reach it.
MISSPELT = "Romualdo Teixeiro"
# A person the tenant never declared, who shares TEIXEIRA's first name and nothing else, and
# teaches a discipline the tab says TEIXEIRA does NOT teach.
STRANGER = "Romualdo Marques"


def _row(day: str, professor: str, subject: str) -> list[str]:
    return [f"{day}/10/2026", "Sex", professor, subject, "Sala 1"]


ROWS = [_row("02", TEIXEIRA, ALGEBRA),
        _row("03", MISSPELT, ESTATISTICA),
        _row("05", CORREIA, REDES)]


def _svc(rows: "list[list[str]]" = (), faculty: "list[list[str]] | None" = None,
         *, today: date = TODAY) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(SID, "Secretaria", [_HEADER] + list(rows or ROWS))
    if faculty is not None:
        store.put(SID, "Corpo Docente", faculty)
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: today)


def _briefing(svc: CoordinatorService, tool: str = "get_weekly_briefing", **kwargs: object) -> str:
    mcp = build_server(svc)

    async def run() -> str:
        res = await mcp.call_tool(tool, {"professor": "", **OVERSIGHT, **kwargs})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")
    return asyncio.run(run())


def _named(out: str) -> list[str]:
    """The professor each dated line names, in order."""
    return [ln.split(" · Professor: ")[1] for ln in out.splitlines() if " · Professor: " in ln]


def _blocks(svc: CoordinatorService):
    fac = svc.estimate_faculty_pay(period="2026-10", **OVERSIGHT)
    return fac, {e.professor: e for e in fac.estimates}


# ── the twin: the misspelt spelling is SHOWN as the declared one ──────────────────────
def test_a_MISSPELT_spelling_is_shown_under_the_name_the_faculty_records_DECLARE():
    """The measured turn, in one line of one listing. The schedule writes «Romualdo Teixeiro»;
    the faculty tab declares «Romualdo da Silva Teixeira» and says he teaches this discipline;
    nobody else who teaches it shares a word of that name. So the briefing hands on the
    spelling the directory carries, and the schedule's own never leaves this vertical."""
    out = _briefing(_svc(faculty=FACULTY))
    assert _named(out) == [TEIXEIRA, TEIXEIRA, CORREIA]
    assert MISSPELT not in out
    assert f"- 03/10 · Turma EST_21 · {ESTATISTICA} · Professor: {TEIXEIRA}" in out.splitlines()


def test_the_SAME_resolution_reaches_every_listing_and_not_only_the_briefing():
    """One renderer, one rule — the defect was reported on the weekly briefing and the next
    turn asks for the month. A tool that resolved names and one that did not would be the
    consumer-by-consumer rule this change exists to avoid."""
    svc = _svc(faculty=FACULTY)
    for tool in ("get_weekly_briefing", "get_professor_schedule"):
        out = _briefing(svc, tool)
        assert _named(out) == [TEIXEIRA, TEIXEIRA, CORREIA], tool
        assert MISSPELT not in out, tool


# ── the control: a listing of declared spellings does not move ───────────────────────
def test_a_listing_whose_SPELLINGS_ARE_ALREADY_THE_TAB_S_renders_BYTE_IDENTICALLY():
    """The control that keeps this from being a change to every tenant's reply. With nothing to
    resolve, the listing is the one the coordinator already reads — byte for byte, whether or
    not a faculty tab exists at all."""
    rows = [_row("02", TEIXEIRA, ALGEBRA), _row("03", TEIXEIRA, ESTATISTICA),
            _row("05", CORREIA, REDES)]
    assert _briefing(_svc(rows, FACULTY)) == _briefing(_svc(rows))
    assert _named(_briefing(_svc(rows, FACULTY))) == [TEIXEIRA, TEIXEIRA, CORREIA]


def test_NO_FACULTY_RECORDS_changes_NOTHING_and_that_is_the_live_shape_of_2026_09_22():
    """The tab was EMPTY on the live turns this vertical's supervision comes from — the declared
    tab name matched no sheet. With no cast there is nobody to resolve to, so every line keeps
    the schedule's own spelling and not one thing breaks."""
    out = _briefing(_svc())
    assert _named(out) == [TEIXEIRA, MISSPELT, CORREIA]
    assert f"Professor: {MISSPELT}" in out


def test_a_PROFESSOR_reading_their_OWN_list_resolves_NOTHING_and_pays_for_nothing():
    """The listing only names a professor when a supervisor is reading more than one, so a
    professor's own list carries no name, asks the service nothing, and is what it always was."""
    svc = _svc(faculty=FACULTY)
    own = _briefing(svc, professor="", identity_label=TEIXEIRA, role="EMPLOYEE")
    assert "Professor:" not in own
    assert srv._canonical_names(svc, svc.aggregate(), "EMPLOYEE") is None


# ── the refusal: two candidates is a question, and the system asks ────────────────────
def test_TWIN_a_spelling_that_two_declared_people_could_be_is_REFUSED_and_BOTH_are_named():
    """Zero ambiguous spellings is the number this tenant's data HAS today, not a property of
    the rule. Widen the cast with a second professor who shares the token AND teaches the
    discipline, and the intersection leaves two: the listing keeps the SCHEDULE's spelling —
    it does not pick — and the pay block names both people it would not choose between."""
    faculty = FACULTY + [[ESTATISTICA, "40", NUNES, "r.nunes@example.edu"]]
    out = _briefing(_svc(faculty=faculty))
    assert _named(out) == [TEIXEIRA, MISSPELT, CORREIA]        # the misspelling stands unresolved
    fac, by = _blocks(_svc(faculty=faculty))
    assert by[MISSPELT].maybe_same == (TEIXEIRA, NUNES)
    assert f"Atenção: “{TEIXEIRA}”, “{NUNES}” pode ser a mesma pessoa" in render_faculty_pay_block(fac)


def test_a_spelling_NO_DECLARED_SIGNAL_REACHES_stays_as_the_sheet_writes_it():
    """A stranger: he shares TEIXEIRA's first name and teaches a discipline the tab says
    TEIXEIRA does not. One signal alone would hand his class to somebody else under somebody
    else's name; the intersection leaves nobody, and the line says what the sheet says."""
    rows = [_row("02", TEIXEIRA, ALGEBRA), _row("03", STRANGER, REDES)]
    out = _briefing(_svc(rows, FACULTY))
    assert _named(out) == [TEIXEIRA, STRANGER]


# ── the boundary: a label is not a sum ────────────────────────────────────────────────
def test_the_RESOLVED_SPELLING_DOES_NOT_MOVE_ONE_CLASS_and_the_block_says_they_were_not_summed():
    """The line this change refuses to cross. The listing shows the declared name because a
    reader has to be able to look the person up; the estimate keeps the two blocks apart
    because merging them moves money on evidence that also fits a colleague sharing a first
    name. The divergence is not discovered by arithmetic — the block states it."""
    fac, by = _blocks(_svc(faculty=FACULTY))
    assert sorted(by) == sorted([TEIXEIRA, MISSPELT, CORREIA])
    assert (by[TEIXEIRA].hours, by[MISSPELT].hours) == (4, 4)
    assert by[MISSPELT].maybe_same == (TEIXEIRA,)
    assert f"Atenção: “{TEIXEIRA}” pode ser a mesma pessoa — não foi somado aqui." \
        in render_faculty_pay_block(fac)
    # and asking BY the misspelt name still answers about the misspelt block, not TEIXEIRA's
    assert _svc(faculty=FACULTY).estimate_professor_pay(
        period="2026-10", professor=MISSPELT, **OVERSIGHT).professor == MISSPELT


# ── the reader the dedup would have blinded ───────────────────────────────────────────
def test_the_FACULTY_RECORDS_reader_is_UNCHANGED_one_row_per_person_first_row_wins():
    """``_faculty_records`` is now expressed over ``_faculty_rows`` instead of beside it, and it
    must answer exactly what it answered: one row per distinct folded name, the FIRST, in sheet
    order. If that folding ever changes in silence, ``#138``'s cast changes with it."""
    rows = _svc(faculty=FACULTY)._faculty_records(None)
    assert [name for name, _rec in rows] == [TEIXEIRA, CORREIA]
    assert [rec["disciplina"] for _n, rec in rows] == [ALGEBRA, ESTATISTICA]   # the FIRST rows
    assert len(_svc(faculty=FACULTY)._faculty_rows(None)) == 4                 # and all four


# ── the mutations ─────────────────────────────────────────────────────────────────────
def test_MUTATION_resolving_by_the_DISCIPLINE_ALONE_leaves_the_name_unresolved():
    """Drop the token half and the discipline answers with everybody who teaches it — here two
    people, which is a refusal. Measured over the tenant's own data the discipline alone leaves
    SIX spellings ambiguous; the shape is this one."""
    assert _named(_briefing(_svc(faculty=FACULTY))).count(TEIXEIRA) == 2       # the anchor
    original = mod._by_discipline_and_token
    try:
        mod._by_discipline_and_token = lambda spelling, disciplines, cast, teaches: sorted(
            {i for d in disciplines for i in teaches.get(d, set())})
        assert _named(_briefing(_svc(faculty=FACULTY))) == [TEIXEIRA, MISSPELT, CORREIA]
    finally:
        mod._by_discipline_and_token = original
    assert _named(_briefing(_svc(faculty=FACULTY))).count(TEIXEIRA) == 2


def test_MUTATION_resolving_by_the_TOKEN_ALONE_puts_a_STRANGERS_class_under_another_name():
    """Drop the discipline half and a shared first name decides. The stranger's own class is
    then announced under a declared professor's name — to a reader, and to the tool that
    notifies a person."""
    rows = [_row("02", TEIXEIRA, ALGEBRA), _row("03", STRANGER, REDES)]
    assert _named(_briefing(_svc(rows, FACULTY))) == [TEIXEIRA, STRANGER]      # the anchor
    original = mod._by_discipline_and_token
    try:
        mod._by_discipline_and_token = lambda spelling, disciplines, cast, teaches: sorted(
            i for i, (canonical, _s, _w) in enumerate(cast)
            if set(mod._name_tokens(spelling)) & set(mod._name_tokens(canonical)))
        assert _named(_briefing(_svc(rows, FACULTY))) == [TEIXEIRA, TEIXEIRA]
    finally:
        mod._by_discipline_and_token = original
    assert _named(_briefing(_svc(rows, FACULTY))) == [TEIXEIRA, STRANGER]


def test_MUTATION_rendering_the_SCHEDULE_S_SPELLING_is_the_defect_with_the_rule_still_in_place():
    """The rule can resolve the name perfectly and the turn still goes wrong, because what
    leaves this vertical is what the LISTING printed. Stop handing the map to the renderer and
    every figure stays right while the model is handed a name the directory does not carry."""
    assert MISSPELT not in _briefing(_svc(faculty=FACULTY))                    # the anchor
    original = srv._canonical_names
    try:
        srv._canonical_names = lambda svc, entries, role: None
        assert _named(_briefing(_svc(faculty=FACULTY))) == [TEIXEIRA, MISSPELT, CORREIA]
    finally:
        srv._canonical_names = original
    assert MISSPELT not in _briefing(_svc(faculty=FACULTY))


def test_MUTATION_PICKING_THE_FIRST_candidate_instead_of_refusing_names_a_person_at_random():
    """The refusal is the rule, not a gap in it. Take the first of two candidates and the
    ambiguous spelling is announced as one of the two people it might be — chosen by the tab's
    row order, which is no evidence about anybody."""
    faculty = FACULTY + [[ESTATISTICA, "40", NUNES, "r.nunes@example.edu"]]
    assert _named(_briefing(_svc(faculty=faculty))) == [TEIXEIRA, MISSPELT, CORREIA]   # anchor
    original = mod._by_discipline_and_token
    try:
        mod._by_discipline_and_token = lambda *a, **k: original(*a, **k)[:1]
        assert _named(_briefing(_svc(faculty=faculty))) == [TEIXEIRA, TEIXEIRA, CORREIA]
    finally:
        mod._by_discipline_and_token = original
    assert _named(_briefing(_svc(faculty=faculty))) == [TEIXEIRA, MISSPELT, CORREIA]


def test_MUTATION_reading_the_DEDUPED_faculty_rows_loses_the_discipline_that_resolves_the_name():
    """Why the discipline signal reads the tab UNFOLDED. One row per person keeps the FIRST and
    it takes its discipline with it — every other discipline leaves with the row it was written
    on. TEIXEIRA's second row is the one that names this discipline, so a deduped read says
    only CORREIA teaches it, the token half finds nothing, and the name stays unresolved."""
    assert MISSPELT not in _briefing(_svc(faculty=FACULTY))                    # the anchor
    original = mod.CoordinatorService._faculty_rows

    def deduped(self, report):
        seen: set = set()
        out = []
        for name, rec in original(self, report):
            if mod._norm(name) in seen:
                continue
            seen.add(mod._norm(name))
            out.append((name, rec))
        return out

    try:
        mod.CoordinatorService._faculty_rows = deduped
        assert _named(_briefing(_svc(faculty=FACULTY))) == [TEIXEIRA, MISSPELT, CORREIA]
    finally:
        mod.CoordinatorService._faculty_rows = original
    assert MISSPELT not in _briefing(_svc(faculty=FACULTY))
