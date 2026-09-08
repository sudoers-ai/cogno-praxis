"""The class group ("turma") — carried on every line, and the one argument that can be a preposition.

Measured 2026-09-06 on the owner's own live COORDINATOR conversation, turns 56 and 57:

* t56 "traga minhas aulas" came back as
  ``- Mês: 2026-09-08 00:00:00 | Dia: 2026-09-08 00:00:00 | Data: 2026-09-08 00:00:00 |
  Disciplina: NoSQL and Distributed Databases | Professor: Vinicius Vale`` — the same day said
  THREE times and the class group said none. He teaches four groups; nothing on that line told
  him which one each class belonged to.
* t57 "e das outras turmas?" was read as *other PROFESSORS* and refused on scope ("só posso
  mostrar as suas aulas"), and the model also switched ``include_past=true`` although nobody
  had mentioned the past.

The group was never missing from the data — ``ClassEntry.sheet_key`` has carried the tenant's own
label since the vertical shipped, and reached a human only inside error messages. It was a
FORMATTING gap, not a plumbing one.

**"DE" is a preposition.** A class group's prefix can also be the commonest Portuguese word in a
sentence about a schedule ("as aulas DE outubro", "a aula DE matemática"). A tolerant match that
went looking for group names in free text would turn half a request into a filter and answer with
an empty list — or, worse, with the wrong group. Two rules were measured against each other
BEFORE either was written, and the over-tightening probe below is that measurement, embedded:

    argument                        squash+substring   token run (shipped)
    'SMP' / 'EM' / 'EM_09' …        correct            correct
    'e'   (conjunction)             EM_09, EM_10       nothing
    'a'   (article)                 all four           nothing
    'a em' (truncated argument)     EM_09, EM_10       nothing
    'mp33' (crosses SMP|33)         SMP_33             nothing
    'as aulas em outubro'           nothing            nothing

Neither rule can save a model that fills ``turma`` with exactly ``"de"``. That half is the
prompt's, and a prompt assertion is a presence assertion — see the honest sentence in the PR.
What the code guarantees is narrower and real: the tool NEVER looks for a class group in free
text, it only reads the argument it was handed, and an argument that designates nothing returns
nothing LOUDLY instead of guessing.

**The fixture is anonymised** (this repo is public, and #97 set the rule). It reproduces the live
SHAPE — four groups, keys with spaces, two of them with a DOUBLED space, invented ids with the
real morphology. The live tenant's hazardous prefix is a two-letter Portuguese preposition; ``EM``
reproduces that hazard without reproducing the tenant's own group naming.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ReadReport,
)
from cogno_praxis.coordinator.server import build_server

_ID_A = "1QwErTy-UiOpAsDfGhJkLzXcVbNm45678"                    # 33 chars
_ID_B = "1PoIuYtReWqLkJhGfDsAmNbVcXz0123456789AbCdEfG"         # 44
_ID_C = "1ZxCvBnM_AsDfGhJkLqWeRtYuIo78901Q"                    # 33
_ID_D = "1MnBvCxZlKjHgFdSaPoIuYtReWq9876543210ZyXwVuT"         # 44

# Two families, and the second one's prefix is a Portuguese preposition on purpose.
# Two keys carry a DOUBLED space, exactly as the live rules do.
RULES = f"""
# Base spreadsheets (current classes)
SPREADSHEETS:
Turma SMP_33 = {_ID_A}
Turma  SMP_34 = {_ID_B}
Turma  EM_09 = {_ID_C}
Turma EM_10 = {_ID_D}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A4:E110"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
FIXED_COLUMNS: "Mes, Dia, Data"
FREE_SLOT_LABELS: "Livre"
SKIP_LABELS: "Feriado"
"""

# The live sheet's own layout: three columns holding the SAME day, then the real content.
_HEADER = ["Mes", "Dia", "Data", "Disciplina", "Professor"]
_TODAY = date(2026, 9, 6)


def _row(iso: str, subject: str, professor: str = "Ana") -> list[str]:
    """One schedule row shaped like the live sheet — the date repeated across three columns,
    verbatim in the spreadsheet's own 'YYYY-MM-DD 00:00:00' form."""
    stamp = f"{iso} 00:00:00"
    return [stamp, stamp, stamp, subject, professor]


def _grid(rows: list[list[str]]) -> list[list[str]]:
    """RANGE_SCHEDULE is A4:… → the header sits on sheet row 4 (grid index 3)."""
    return [[""] * 5, [""] * 5, [""] * 5, list(_HEADER)] + rows


def _service(today: date = _TODAY) -> CoordinatorService:
    cfg = CoordinatorConfig(RULES)
    store = InMemorySpreadsheetStore()
    store.put(_ID_A, "Secretaria", _grid([_row("2026-09-10", "Redes"),
                                          _row("2026-08-01", "Redes")]))       # one in the past
    store.put(_ID_B, "Secretaria", _grid([_row("2026-09-11", "Calculo")]))
    store.put(_ID_C, "Secretaria", _grid([_row("2026-09-12", "Spark")]))
    store.put(_ID_D, "Secretaria", _grid([_row("2026-09-13", "NoSQL")]))
    return CoordinatorService(store, cfg, today=lambda: today)


def _tool(svc: CoordinatorService, **kwargs: object) -> str:
    mcp = build_server(svc)

    async def run() -> str:
        res = await mcp.call_tool("get_professor_schedule",
                                  {"role": "SUPERVISOR", "identity_label": "Sofia", **kwargs})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")
    return asyncio.run(run())


# ── property 1: the group travels on EVERY line ──────────────────────────────────────
def test_every_line_names_its_class_group():
    """The whole point, and the criterion the matrix is scored on: the answer names a turma."""
    out = _tool(_service())
    lines = [ln for ln in out.splitlines() if ln.startswith("- ")]
    assert len(lines) == 4
    # The group moved from a LABELLED first field to the MIDDLE of "DD/MM · TURMA · Disciplina".
    # The property is unchanged and is what this asserts: every line still names it, and the
    # name is still the tenant's own. Only the label went.
    assert all(len(ln.split(" · ")) >= 3 for ln in lines), out
    assert {"Turma SMP_33", "Turma SMP_34", "Turma EM_09", "Turma EM_10"} == {
        ln.split(" · ")[1] for ln in lines}


def test_the_group_is_the_tenants_own_label_not_a_derived_one():
    """The name a human recognises is the one the tenant typed — the doubled space collapses in
    the config parser (#97) and nothing downstream re-spells it."""
    out = _tool(_service(), turma="SMP_34")
    assert "· Turma SMP_34 ·" in out
    assert "SMP34" not in out and "smp_34" not in out


def test_the_group_reaches_the_other_read_tools_too():
    """``_fmt_entry`` is shared: the briefing, the deadlines and the free slots are formatted by
    the same function, so none of them can go on printing a group-less line."""
    svc = _service()
    mcp = build_server(svc)

    async def run() -> str:
        res = await mcp.call_tool("get_weekly_briefing",
                                  {"role": "SUPERVISOR", "identity_label": "Sofia"})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")
    out = asyncio.run(run())
    assert "· Turma SMP_33 ·" in out


# ── property 5: one date, not three ──────────────────────────────────────────────────
def test_the_date_is_said_once_and_normalized():
    out = _tool(_service(), turma="SMP_33")
    line = next(ln for ln in out.splitlines() if ln.startswith("- "))
    assert line == "- 10/09 · Turma SMP_33 · Redes", line
    assert "00:00:00" not in out                      # the raw spreadsheet stamp is gone
    # Said once, and now the YEAR is said once too — by the month header, for the whole group.
    assert out.count("10/09") == 1 and out.count("2026") == 1
    assert out.splitlines()[0] == "*Setembro de 2026*"


def test_a_column_that_is_not_the_same_date_survives():
    """The mutation twin for the collapse: it folds a REPEATED DATE, never a column whose name
    merely looks date-ish. A ``Dia`` holding a weekday is a different fact."""
    cfg = CoordinatorConfig(RULES)
    store = InMemorySpreadsheetStore()
    store.put(_ID_A, "Secretaria",
              _grid([["Setembro", "Quinta", "2026-09-10 00:00:00", "Redes", "Ana"]]))
    # The LISTING no longer carries the extra columns at all — it renders three chosen fields —
    # so the collapse is asserted where the labelled form still lives: ``_fmt_entry``, which
    # renders a calendar event's description. That is the surviving consumer of
    # ``_says_the_same_date``, and dropping this assertion instead of moving it would have left
    # that helper with nothing exercising the distinction it exists to make.
    from cogno_praxis.coordinator.server import _fmt_entry
    entries = CoordinatorService(store, cfg, today=lambda: _TODAY).get_professor_schedule(
        role="SUPERVISOR", identity_label="Sofia", turma="SMP_33")
    described = _fmt_entry(entries[0])
    assert "Mes: Setembro" in described and "Dia: Quinta" in described
    assert "Data: 10/09/2026" in described
    assert described.count("10/09/2026") == 1
    # and the listing, which chose its fields, shows the date once and no stray column
    out = _tool(CoordinatorService(store, cfg, today=lambda: _TODAY), turma="SMP_33")
    assert out.count("10/09") == 1 and "Quinta" not in out


def test_an_unparseable_date_is_still_shown_once():
    cfg = CoordinatorConfig(RULES)
    store = InMemorySpreadsheetStore()
    store.put(_ID_A, "Secretaria", _grid([["a definir", "a definir", "a definir", "Redes", "Ana"]]))
    out = _tool(CoordinatorService(store, cfg, today=lambda: _TODAY), turma="SMP_33")
    assert out.count("a definir") == 1
    assert "Data: a definir" in out


# ── property 2: the tolerant match, and the over-tightening probe ────────────────────
_DESIGNATORS = [
    ("SMP", ["Turma SMP_33", "Turma SMP_34"]),
    ("smp", ["Turma SMP_33", "Turma SMP_34"]),
    ("SMP_33", ["Turma SMP_33"]),
    ("EM", ["Turma EM_09", "Turma EM_10"]),
    ("EM_09", ["Turma EM_09"]),
    ("em_09", ["Turma EM_09"]),
    ("em 09", ["Turma EM_09"]),
    ("EM 09", ["Turma EM_09"]),
    ("EM09", ["Turma EM_09"]),
    ("Turma  EM_09", ["Turma EM_09"]),          # the doubled space the tenant types
    ("33", ["Turma SMP_33"]),
]

# The probe. Every row here is something a model might put in `turma` while NOT naming a group;
# none of them may select one. The first four are the preposition itself in free text, the rest
# are the fragments that separate a token run from a plain substring — under squash+substring
# 'e', 'a', 'a em' and 'mp33' all come back with groups attached.
_NOT_A_GROUP = [
    "as aulas em outubro",
    "a aula em matematica",
    "a aula em matemática",
    "minhas aulas em segunda-feira",
    "reuniao em novembro",
    "as aulas de outubro",
    "a aula de matemática",
    "minhas aulas de segunda-feira",
    "aulas da SMP",
    "e",
    "a",
    "o",
    "d",
    "a em",
    "mp33",
    "maem",
    "rmasmp",
]


@pytest.mark.parametrize("arg,expected", _DESIGNATORS)
def test_a_group_designator_resolves_however_it_was_typed(arg, expected):
    assert _service().resolve_turmas(arg) == expected


@pytest.mark.parametrize("arg", _NOT_A_GROUP)
def test_free_text_never_becomes_a_class_group_filter(arg):
    """The over-tightening probe. A sentence, a preposition, an article, a conjunction or a
    fragment that crosses a token boundary must designate NOTHING."""
    assert _service().resolve_turmas(arg) == []


def test_an_empty_argument_is_no_filter_not_a_miss():
    svc = _service()
    assert svc.resolve_turmas("") == []
    assert svc.resolve_turmas("   ") == []
    report = ReadReport()
    got = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia", report=report)
    assert len(got) == 4 and report.unmatched_turma == ""


def test_a_prefix_selects_the_family_and_only_the_family():
    svc = _service()
    got = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia", turma="SMP")
    assert sorted(e.sheet_key for e in got) == ["Turma SMP_33", "Turma SMP_34"]
    assert {e.subject for e in got} == {"Redes", "Calculo"}


def test_a_turma_that_designates_nothing_says_so_instead_of_guessing():
    """Loud, not silent. Dropping the filter answers a question nobody asked; guessing the group
    sends a professor to the wrong classroom. The tool names the configured groups and tells the
    model what to do about a word that is really a preposition."""
    svc = _service()
    report = ReadReport()
    got = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                     turma="outubro", report=report)
    assert got == []
    assert report.unmatched_turma == "outubro"
    assert report.known_turmas == ("Turma SMP_33", "Turma SMP_34", "Turma EM_09", "Turma EM_10")

    out = _tool(svc, turma="outubro")
    assert "NO SUCH CLASS GROUP" in out
    assert "Turma SMP_33" in out and "Turma EM_10" in out
    assert "turma` empty" in out
    assert not out.startswith("ERROR")           # a bad filter is not a breakdown


def test_a_readable_run_never_mentions_a_missing_group():
    """The mutation twin for the footer: the NO SUCH CLASS GROUP line must be earned."""
    assert "NO SUCH CLASS GROUP" not in _tool(_service(), turma="EM")


# ── property 4: other groups are not the past ────────────────────────────────────────
def test_asking_for_a_group_does_not_reach_into_the_past():
    """The negative twin. ``include_past`` defaults false and a ``turma`` filter never flips it —
    the past class in SMP_33 stays hidden, and the footer says so because something was cut."""
    svc = _service()
    report = ReadReport()
    got = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                     turma="SMP_33", report=report)
    assert [e.subject for e in got] == ["Redes"]
    assert all(e.when and e.when >= _TODAY for e in got)
    assert report.hidden_past == 1

    out = _tool(svc, turma="SMP_33")
    assert "01/08/2026" not in out


def test_the_past_still_comes_back_when_it_is_actually_asked_for():
    """The other half: nothing here narrows the explicit request."""
    svc = _service()
    got = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                     turma="SMP_33", include_past=True)
    assert sorted(e.date_str for e in got) == ["01/08/2026", "10/09/2026"]


# ── property 3: the persona's half, pinned by presence ───────────────────────────────
def test_the_executor_is_told_that_another_group_is_not_another_professor():
    """A presence assertion, and this file does not pretend otherwise: whether the model OBEYS is
    a live measurement. What it buys is that the instruction cannot be deleted silently — which
    is exactly how it was never written in the first place."""
    from pathlib import Path
    prompts = Path(__import__("cogno_praxis").__file__).resolve().parent / "coordinator" / "prompts"
    system = (prompts / "system.txt").read_text(encoding="utf-8")
    assert '"Outras turmas" is not "outro professor"' in system
    assert "there is nothing to refuse" in system
    assert "NOT asking about the past" in system
    # and the argument is fenced off from free text
    assert "never a sentence, never a" in system
    assert "de` is a preposition" in system
    # the group names are NOT hardcoded here: they come from the tenant direction block
    assert "`SPREADSHEETS:` block" in system
    voice = (prompts / "voice.txt").read_text(encoding="utf-8")
    assert "SAY the group" in voice
    assert '"As outras turmas" is NOT another professor' in voice
