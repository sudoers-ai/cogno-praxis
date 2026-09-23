"""``CoordinatorService`` — the academic-schedule domain (infra-agnostic).

Ported from the parent's coordinator_assistant tools/reports, rebuilt on the new architecture:
the domain reads through a :class:`~cogno_praxis.coordinator.store.SpreadsheetStore` port (the
host injects a Google-download adapter; tests inject the in-memory fake) and is configured by a
:class:`~cogno_praxis.coordinator.config.CoordinatorConfig` parsed from the tenant's custom_rules.

Role handling (host-authorised, parent parity): a non-oversight caller only ever sees THEIR OWN
classes (``professor`` is pinned to their identity label); an oversight role (SUPERVISOR/ADMIN)
may query any professor or the whole master schedule. The pay estimate follows the same line
since 2026-09-23: everybody's own with ``professor=""``; a professor by name, or every professor
one block each (:data:`ALL_PROFESSORS`), for the oversight roles only.
"""

from __future__ import annotations

import calendar
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Callable, Iterable, Optional

from cogno_praxis.coordinator.ics import (
    CalendarEvent,
    CalendarSender,
    build_ics_calendar,
    class_event_uid,
    parse_time,
    sequence_now,
)
from cogno_praxis.coordinator.config import CoordinatorConfig, pay_refusal
from cogno_praxis.coordinator.pay import (
    FacultyPayEstimate,
    PayEstimate,
    PayGroup,
    PayLine,
    parse_money,
)
from cogno_praxis.coordinator.rsvp import (
    RSVP_DECLINED,
    RSVP_PENDING,
    label_for,
    parse_answer,
    state_of,
)
from cogno_praxis.coordinator.store import SpreadsheetStore
from cogno_praxis.coordinator.types import (
    ClassEntry,
    ColumnLayout,
    DailyChecks,
    DeadlineDue,
    ReadReport,
    SheetReadError,
)

_log = logging.getLogger(__name__)

_OVERSIGHT_ROLES = frozenset({"SUPERVISOR", "ADMIN", "OWNER"})
GRADE_GRACE_DAYS = 14           # parent parity: grades/attendance due within 14d of the last class

#: The ``professor`` argument that means EVERY professor, for the pay estimate — a sentinel, and
#: deliberately not the empty string. ``""`` is the caller, for every role: it was measured
#: (2026-09-09) that an empty argument reaching the schedule filter meant "the master schedule"
#: for an oversight role, and the estimate then summed the whole faculty under the caller's name.
#: "All" therefore has to be ASKED FOR with a character nobody's name contains, and answered as
#: one block per professor (:meth:`CoordinatorService.estimate_faculty_pay`), never as one sum.
ALL_PROFESSORS = "*"

#: The refusal a non-oversight caller gets for asking about anybody but themselves — by name or
#: with :data:`ALL_PROFESSORS`. ONE sentence, unchanged since the capability opened: it is the
#: privacy rule for everyone who is not the coordination, and widening the coordination's reach
#: (2026-09-23) did not move a byte of it.
_OWN_PAY_ONLY = ("You can only see your own pay estimate — another professor's remuneration is "
                 "not something this assistant discloses to anyone.")

#: The refusal EVERY door gives a caller the turn could not name — the same rule the companies
#: vertical already lands on its own ids: **an empty id is not the author of anything, neither
#: to read nor to write.**
#:
#: ``identity_label`` is WHO IS ASKING, and ``""`` names nobody. That is not the same as "a
#: caller with no privileges": with no name, "their own" has no referent, and an oversight
#: ``role`` arriving beside a blank label is a claim with nobody making it. The two facts travel
#: in separate arguments and only one of them is checked by a role test, which is how a door
#: could read the role, find SUPERVISOR, and answer the whole faculty to a caller it could not
#: name (measured 2026-09-23 on :meth:`CoordinatorService.estimate_faculty_pay`: three
#: professors' remuneration, with ``identity_label=""``; the sister door
#: :meth:`estimate_professor_pay` refused the same call, and had refused it since it was
#: written — two doors, one rule, one guarded).
#:
#: **What it is NOT about is the coordination's reach.** The owner's decision of 2026-09-23 is
#: textual — «o supervisor pode ter acesso a todos os professores, pois ele é o coordenador» —
#: and stands untouched: a SUPERVISOR who HAS a label still reads every professor, by name and
#: all at once. The guard fires on the blank label alone, so the twin that matters is the
#: inverse one (a named supervisor still gets the data), and it is pinned beside the refusal in
#: ``tests/unit/test_toda_porta_recusa_um_chamador_sem_identidade.py``.
#:
#: Reachable today only through the HOST, which ASSEMBLES the pair: ``cogno_host``'s RBAC
#: injects the role and, when the identity has no label, skips the label injection entirely, so
#: the tool's own ``""`` default stands beside an oversight role. Measured the same day, the
#: parameter is then also still OFFERED in the published schema (the mirror carried the same
#: condition), so a model could fill it with somebody else's name — the host's half is
#: ``cogno-host`` #990. Latent, in the sense that no identity of the served box carries a blank
#: label; one ``POST /identities`` with ``name=""`` away, in the sense that nothing between the
#: API and here refuses one — the column is ``NOT NULL DEFAULT ''``, the create schema declares
#: ``name: str`` with no ``min_length``, and the handler validates neither.
#: The refusal a non-oversight caller gets when their label resolves to NO row but resembles a
#: name on the sheet (:func:`_near_spellings`) — the identification failed, not the schedule.
#: It names NOBODY: saying who the label resembles would be the leak the filter exists to stop,
#: delivered by the error message instead of the rows.
_LABEL_UNRESOLVED = (
    "Your registered name does not match any professor on this schedule exactly, but it "
    "resembles a name that is there — a shorter or longer form of it, or one another person "
    "could also have — so it cannot be safely told apart from someone else's. Nothing was shown "
    "because it could be another person's data; your classes may well exist. Ask the "
    "administrator to register your full name exactly as the schedule writes it. Do not guess, "
    "and do not name who it could be.")

_NO_IDENTITY = ("This turn carries no identified professor, so there is nobody for this answer "
                "to be about. This is an access rule working as intended, not a failure — say "
                "that the caller could not be identified.")

#: How far ahead a schedule read looks when the caller named NO period at all.
#:
#: The old default was ``[today, ∞)``, which on the box's own data answered "traga minhas aulas"
#: with **33 classes running to June 2027** — the whole academic year, in one wall of lines a
#: professor has to scroll past to find this week. The window is not a limit on what may be
#: asked for; it is the answer to the question that was actually asked, and every wider read is
#: one argument away (``month``, ``include_past``), named in the footer the cut raises.
#:
#: This is a UX default and NOTHING ELSE. It is emphatically not the repair for a class that
#: went missing from a listing on 2026-09-06: that class was 24 days out, INSIDE this horizon,
#: and the same unfiltered read returned it seven minutes later. See the PR body.
DEFAULT_HORIZON_DAYS = 30
BRIEFING_HORIZON_DAYS = 7
REPLACEMENT_HORIZON_DAYS = 21
_DISCIPLINE_FUZZY_THRESHOLD = 0.75    # parent parity: per-token SequenceMatcher ratio floor

# Month name → number. PT-BR because a professor asks for "março", not "2026-03" (parent
# parity) — and ENGLISH because of who actually fills the argument: the EGO reads the NOUMENO's
# canonical-English rewrite of the turn, so "aulas de setembro" reaches the tool as
# ``month="September"``. That fell through to ``None`` = no filter at all, the tool returned the
# whole year (an April workshop included, on a September conversation), the judge rejected the
# answer for not showing September, and the retry — which guessed "2026-09" — passed. One full
# EGO+judge round trip per request, bought back by twelve dictionary rows.
_MONTH_NAMES: dict[str, int] = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "março": 3, "marco": 3, "mar": 3,
    "abril": 4, "abr": 4, "maio": 5, "mai": 5, "junho": 6, "jun": 6,
    "julho": 7, "jul": 7, "agosto": 8, "ago": 8, "setembro": 9, "set": 9,
    "outubro": 10, "out": 10, "novembro": 11, "nov": 11, "dezembro": 12, "dez": 12,
    # English. No collision with the PT rows above: where the two languages share a prefix
    # ("mar", "jun", "jul", "nov") they also share the month, and the values agree.
    "january": 1, "february": 2, "feb": 2, "march": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "december": 12, "dec": 12,
}


def _norm(text: str) -> str:
    """Accent-stripped, lowercased — for label/name comparison ('Ciência'→'ciencia')."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


#: The separator a secretary writes between a discipline and the exception she is annotating it
#: with — a spaced dash, in the three shapes a spreadsheet produces (typed hyphen, and the two
#: dashes an editor substitutes for it). SPACED on both sides on purpose: it is what tells an
#: annotation from a hyphen inside a name ("Pós-Graduação" is one word, not a class put off).
_ANNOTATION_SEP = re.compile(r"\s[-–—]\s")


def _annotation(subject: str) -> str:
    """What a subject cell says AFTER its last spaced dash — ``""`` when it says nothing.

    ``"Machine Learning - Aula adiada"`` → ``"Aula adiada"``; ``"Machine Learning"`` → ``""``.

    The LAST separator, not the first, because the annotation is appended to whatever was
    already there, and disciplines carry dashes of their own ("Data Science - Advanced"). A
    cell with no separator has no annotation: the caller then compares the whole cell, which
    is what every label comparison in this module did before there was anything else to do.
    """
    parts = _ANNOTATION_SEP.split(subject or "")
    return parts[-1].strip() if len(parts) > 1 else ""


def _discipline(subject: str) -> str:
    """What a subject cell names BEFORE its last spaced dash — the DISCIPLINE on its own, with
    the exception a secretary appended to it taken off.

    ``"Machine Learning - Aula adiada"`` → ``"Machine Learning"``; a cell with no separator is
    its own discipline. The mirror of :func:`_annotation`, reading the SAME separator so the
    two halves of a cell can never disagree about where it splits, and the LAST one for the
    same reason: the annotation is appended to whatever was already there.

    It exists because a discipline is a JOIN KEY — the professors tab declares who teaches
    what, and a schedule row saying "Redes - Reposição" is a row of Redes. Comparing the whole
    cell would make a class that was put off a discipline nobody declares.
    """
    last = None
    for m in _ANNOTATION_SEP.finditer(subject or ""):
        last = m
    return (subject[:last.start()] if last else (subject or "")).strip()


def _declared_column(rec: dict[str, str], word: str) -> str:
    """The value of the professors-tab column whose (lowercased) header CONTAINS ``word`` —
    ``""`` when the tab has no such column.

    The headers are the TENANT's own, typed into a spreadsheet nobody validates, so every
    reader of that tab names its column by a fragment that survives the punctuation a human
    puts in one ("e-mail", "E-Mail do professor") and reads the same in Portuguese and English
    ("disciplin" → «Disciplina», "discipline"). One reader instead of one per caller.
    """
    key = next((h for h in rec if word in h), "")
    return rec.get(key, "") if key else ""


def _name_tokens(name: str) -> tuple[str, ...]:
    """A person's name, folded and split — the unit every comparison below is made of."""
    return tuple(t for t in _norm(name).split() if t)


def _is_abbreviation_of(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    """Could ``short`` be somebody writing ``long`` in fewer words — same first name, and every
    word of it already in the long one?

    True for «Helena Quintar» ⊂ «Helena Quintar Bonfim» and for «Tomás Alvim» ⊂ «Tomás
    Nogueira de Alvim Prado». Containment of tokens and equality of the first one: no
    ``difflib``, no edit distance, no threshold of resemblance anywhere in this file's
    treatment of people's names.

    **On its own this predicate is NOT a decision, and it is never used as one.** It says two
    spellings are compatible, not that they are one person — «Tomás Alvim» is compatible with
    every declared name beginning "Tomás" that contains "Alvim". What turns it into an answer
    is the caller: :meth:`CoordinatorService._professor_groups` runs it against the tenant's
    DECLARED people and acts only when exactly one fits. Pairwise, it would be a rule whose
    safety has to be ARGUED; against a closed declared set, it is a rule whose safety can be
    COUNTED, and the counting is what the twins pin.

    It deliberately does NOT require the last token to agree. Requiring it is defensible in
    the abstract and wrong in the data: counted over the 32 spellings the tenant this was
    written for carries, first-AND-last joins 7 pairs and MISSES 7 more — every one of those
    seven one person, confirmed against their disciplines and their declared address — because
    the most ordinary way to shorten a name is to drop the family name.
    """
    return (bool(short) and len(short) < len(long) and short[0] == long[0]
            and set(short) <= set(long))


def _by_discipline_and_token(spelling: str, disciplines: set[str],
                             cast: list[tuple[str, list[str], tuple[str, ...]]],
                             teaches: dict[str, set[int]]) -> list[int]:
    """**The second jump: the declared people an ORPHAN spelling could be** — those the tab says
    teach one of the ``disciplines`` this spelling teaches on the schedule, INTERSECTED with
    those who share at least one TOKEN of its name. Cast indices, in the tab's own order.

    It is reached only by a spelling :func:`_is_abbreviation_of` matched NOBODY — a name the
    schedule MISSPELT, which is the one shape containment cannot reach: «Damião Queiroz»
    against a declared «Damião da Silva Queirós» has a word the declared name does not carry,
    so it is not an abbreviation of it and never will be. The measured turn is the whole reason
    this exists: the owner asked to warn "the professor" and named nobody, the listing handed
    the model the SCHEDULE's spelling, the model passed that spelling to the tool that searches
    the identity directory, the directory does not carry it, and the owner was asked for the
    full name of a person he had just named. Against the same directory the schedule's FULL
    spelling finds nobody and the bare first name finds him: the complete wrong spelling is
    worse than half a right one.

    **What it decides is the LABEL, and it is not allowed to decide the money**
    (:attr:`ProfessorGroup.shown_as`). That boundary was MEASURED, not chosen: wired into the
    join itself, this rule swallows «Helena Marques» — a person the tenant never declared, who
    shares a first name with a declared professor and teaches the same discipline — into that
    professor's pay, which is the exact swallow ``#138``'s own control was written to forbid,
    and it did forbid it (``test_MUTATION_joining_by_FIRST_NAME_ALONE_pays_one_person_for_
    anothers_class`` failed on its ANCHOR). Nothing structural separates that spelling from
    «Damião Queiroz»; what separates the two OUTCOMES is the cost of being wrong. A wrong
    label puts a name on a line a human reads and can correct; a wrong merge moves money
    between two people with nothing on the page to show it. So the label is decided here and
    the merge stays exactly where ``#138`` left it, and the spelling still names the person on
    :attr:`ProfessorGroup.maybe_same`, so the pay block says out loud that the two were not
    summed.

    **The known false positive, named rather than guarded** (parked
    ``token-que-e-titulo-ou-particula``): a TOKEN is a whole word and some whole words identify
    nobody — the Portuguese particles «de/da/dos», and a professors column that carries titles
    («Prof. X», «Prof. Y»). Where a discipline has exactly one declared teacher, such a token
    is enough to decide the label. It is left in because the rule shipping here is the rule
    that was MEASURED, and narrowing a measured rule without a new measurement trades a known
    number for an unknown one; the display-only scope is what makes that affordable.

    **Neither signal decides alone, and that is measured rather than argued.** Over the 16
    schedule spellings of the tenant this was written for that no faculty row carries:
    discipline alone leaves 6 AMBIGUOUS (a discipline is taught by more than one person), token
    alone answers with people who merely share an ordinary first name. The intersection gives
    16 unique, 0 ambiguous, 0 without a candidate.

    **It is data DECLARED by the tenant on both sides.** No edit distance, no ratio, no table
    of nicknames: the discipline is a cell the tab writes and a cell the schedule writes, and a
    token is a whole word of a name. A rule built on resemblance would have to be ARGUED safe;
    this one is COUNTED, and the caller's "exactly one" is what turns a candidate into an
    answer — :meth:`CoordinatorService._professor_groups` refuses on two and says both names.

    The declared side is compared through the CANONICAL spelling alone, and that loses nothing:
    a cast entry only ever holds spellings that are abbreviations of its canonical, so the
    canonical's tokens are the union of all of them.
    """
    if not disciplines:
        return []
    candidates: set[int] = set()
    for d in disciplines:
        candidates |= teaches.get(d, set())
    tokens = set(_name_tokens(spelling))
    return sorted(i for i in candidates if tokens & set(_name_tokens(cast[i][0])))


def _same_professor(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Are these two spellings ONE person, compared with nothing else to go on?

    The PAIRWISE question, and it gets the strict answer precisely because there is no third
    thing to check it against: equal, or one is the other written out with BOTH the first and
    the last token agreeing. «Ana» is not «Ana Silva» here — it could be, and nothing in a pair
    of strings can say so, and the caller is about to attach a survey result worth R$ 40,00 an
    hour to whoever it picks.

    Used where there is no declared cast to anchor to (the IBOPE tab). The looser
    :func:`_is_abbreviation_of` is for the other shape — resolving against the people the
    tenant declared, where a unique fit is a fact and not a preference.
    """
    if not a or not b:
        return False
    return a == b or _fuller(a, b) or _fuller(b, a)


def _fuller(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    """:func:`_is_abbreviation_of` with the FAMILY NAME required to agree as well."""
    return _is_abbreviation_of(short, long) and short[-1] == long[-1]


def _own_spellings(label: str, spellings: Iterable[str]) -> set[tuple[str, ...]]:
    """Which of ``spellings`` are the CALLER's own name — the rows a non-oversight role may see.

    **A privacy filter, so it may only ever NARROW.** It replaced a folded SUBSTRING
    (``_norm(label) in _norm(cell)``), and a name is not a substring of a person: an EMPLOYEE
    labelled «Ana» read every row of «Mariana Lopes» — her schedule, her faculty record (the
    calendar then went to HER address) and, through the own-pay door, her classes summed into
    «Ana»'s remuneration: 1 class of her own became 4. The same filter guards the two WRITES a
    professor can make (``confirm_swap``, ``record_class_response``), so the substring also let
    «Ana» move and decline «Mariana Lopes»'s class.

    Two conditions, both over whole TOKENS folded by :func:`_norm`:

    1. **the spelling is the label's, pairwise** — :func:`_same_professor`, the strict rule
       the caller's own IBOPE result was already read by: equal, or one is the other written
       out with BOTH the first and the last token agreeing. «Ana Lopes» ⊂ «Ana Maria Lopes» is
       hers; «Ana Lopes» against «Mariana Lopes» (a shared family name) is not.
    2. **nothing else on the sheet could claim it** — for every spelling on the sheet, it is
       the same person as the candidate exactly when it is the same person as the label. The
       pairwise rule cannot see a THIRD name: labelled «Ana Lopes», a sheet carrying «Ana Maria
       Lopes» AND «Ana Beatriz Lopes» holds two people who both fit, and labelled «Ana Maria
       Lopes», a row written «Ana Lopes» beside an «Ana Beatriz Lopes» may be either. Such a
       spelling is dropped. The label's EXACT spelling always survives this — it disagrees
       with nothing, by construction.

    **What it refuses that is somebody's own, counted rather than hidden:** a label that drops
    the FAMILY name («Ana Maria» against «Ana Maria Lopes»), a label that is a bare first name
    («Ana» against «Ana Lopes»), a title on the sheet («Prof. Ana Lopes»), and an initial
    («Ana M. Lopes»). The first two are, token for token, the shape of a DIFFERENT person
    («Ana Maria» against «Ana Maria Costa», «Ana» against «Ana Silva»): no pairwise rule tells
    them apart, and in a privacy filter the disqualifying error is the leak, so they go to the
    refusal. What reopens them is the identity's label carrying the full name the sheet uses.
    No ``difflib``, no suggestion, no resemblance — a fuzzy rule here would widen a leak.
    """
    mine = _name_tokens(label)
    if not mine:
        return set()
    sheet = {_name_tokens(s) for s in spellings} - {()}
    # Condition 1 is IMPLIED by condition 2 (take ``other = cand``: ``True`` must equal
    # ``_same_professor(cand, mine)``), so loosening the first alone changes nothing — measured
    # as an equivalent mutant. It is written out because it is the question; 2 is the refinement.
    return {cand for cand in sheet
            if _same_professor(mine, cand)
            and all(_same_professor(other, cand) == _same_professor(other, mine)
                    for other in sheet)}


def _near_spellings(label: str, spellings: Iterable[str]) -> bool:
    """Does some spelling on the sheet LOOK like the caller's name without being provably it?

    The second state of a non-oversight read that comes back EMPTY, and the one that must not be
    reported as the first. :func:`_own_spellings` returning nothing means one of two things:
    the sheet holds no name like this one (then "no classes" is the truth), or it holds a name
    this rule REFUSED to call the caller's — «Ana» beside «Ana Lopes», «Ana Maria» beside «Ana
    Maria Lopes», «Ana Lopes» beside «Prof. Ana Lopes», or a fuller spelling another name on the
    sheet also fits. In that second world the classes may well exist and what failed is the
    IDENTIFICATION; answering "No classes found." there is a false sentence a professor acts on.

    Near means: every token of one is in the other (either direction), or the first AND the last
    token agree. It is only ever used to choose which REFUSAL to give — it never admits a row —
    so it can afford to be broad; what it may not do is name anybody (:data:`_LABEL_UNRESOLVED`).
    """
    mine = _name_tokens(label)
    if not mine:
        return False
    for s in spellings:
        cand = _name_tokens(s)
        if not cand or cand == mine:
            continue
        if (set(mine) <= set(cand) or set(cand) <= set(mine)
                or (mine[0] == cand[0] and mine[-1] == cand[-1])):
            return True
    return False


def _note_unconfirmed(report: "Optional[ReadReport]", label: str,
                      mine: set[tuple[str, ...]], spellings: Iterable[str]) -> None:
    """The THIRD state of a non-oversight read: the label resolved to SOME rows, and other rows
    carry a name that looks like it (:func:`_near_spellings`) but could not be confirmed as the
    caller's. Measured on the first cut of this rule: «Ana Lopes» on a sheet with one «Ana
    Lopes» row and two «Prof. Ana Lopes» rows answered 4 h / R$ 400,00 with nothing to say two
    classes were left out — a partial answer read as a whole one.

    It records a BIT on ``report`` (:attr:`ReadReport.unconfirmed_similar`) and nothing else —
    no name and no count, because a count of similar rows already says how many similar
    PEOPLE the sheet holds. ``report`` is the read record every read tool already renders as a
    footer, which is why this rides there rather than on a new return value."""
    if report is None or not mine:
        return
    rest = [s for s in spellings if _name_tokens(s) not in mine]
    if rest and _near_spellings(label, rest):
        report.unconfirmed_similar = True


def _fuzzy_match_discipline(query: str, candidate: str,
                            threshold: float = _DISCIPLINE_FUZZY_THRESHOLD) -> bool:
    """Fuzzy match a discipline query against a class subject (parent parity). Strategy:
      1. accent-normalized substring (fast path) — 'data science' → 'Fundamentals of Data Science'
      2. per-token fuzzy: every query word must SequenceMatcher-match some candidate word above
         ``threshold`` — 'machne learning' → 'Machine Learning' (0.93), 'fundamentos' →
         'Fundamentals' (0.83). 'python' → 'Machine Learning' fails.
    An empty query never matches (the caller skips filtering instead)."""
    nq, nc = _norm(query), _norm(candidate)
    if not nq:
        return False
    if nq in nc:
        return True
    c_words = nc.split()
    for qw in nq.split():
        best = max((SequenceMatcher(None, qw, cw).ratio() for cw in c_words), default=0.0)
        if best < threshold:
            return False
    return True


# One class-group designator, split into the pieces a human varies: letters and digits, with
# every separator, accent and capital thrown away. "DE_09", "de 09", "DE09" and "Turma  DE_09"
# all become the same token list, so the tenant's spacing (one of the live keys carries a DOUBLE
# space) can never decide whether a filter matches.
_TURMA_TOKENS = re.compile(r"[a-z]+|[0-9]+")


def _turma_tokens(text: str) -> list[str]:
    """``'Turma  DE_09'`` → ``['turma', 'de', '09']``; ``'DE09'`` → ``['de', '09']``."""
    return _TURMA_TOKENS.findall(_norm(text))


def _turma_matches(query: list[str], key: str) -> bool:
    """Does a ``turma`` argument designate the class group ``key``?

    The rule is a CONTIGUOUS RUN of whole tokens: the query's tokens must appear side by side,
    in order, inside the key's tokens. So a bare prefix selects a family (``DSA`` → ``DSA_33``
    and ``DSA_34``), a full designator selects one group however it was typed, and a bare number
    still works (``33``).

    **Why a token run and not a substring.** A class-group prefix can also be an ordinary
    Portuguese word: ``DE_09``/``DE_10`` are perfectly ordinary group names and ``de`` is the
    commonest preposition in any sentence about a schedule ("as aulas DE outubro"). The cheap rule
    (strip every separator, then substring) was measured against this one before either was
    written, and it turns the single conjunction ``e`` — the first word of the very turn that
    provoked this change — into a filter selecting both ``DE`` groups, because "e" sits inside
    "turmade09". A token run answers nothing to it. Neither rule can save a model that fills the
    argument with exactly ``"de"``, and that is the prompt's job (the tool NEVER goes looking for
    a class group in free text; it only ever reads the argument it was handed).
    """
    if not query:
        return False
    k = _turma_tokens(key)
    n = len(query)
    return any(k[i:i + n] == query for i in range(len(k) - n + 1))


def _resolve_month(raw: str) -> Optional[tuple[int, int]]:
    """Parse a user month filter into ``(month, year)`` where year may be 0 (any year).
    Accepts ``'2026-03'``, ``'03'``, ``'3'``, or a PT-BR name/abbrev ``'março'``/``'mar'``.
    Returns ``None`` when it can't be understood (the caller then skips month filtering)."""
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) >= 7 and s[4] == "-":                       # "YYYY-MM"
        try:
            m, y = int(s[5:7]), int(s[:4])
        except ValueError:
            return None
        # The SAME bound the bare-number branch below has always had, and it was missing here.
        # Two readings of one predicate that disagree: "13" answered None (no filter), while
        # "2026-13" answered (13, 2026) and travelled on — the filter then matched no class, and
        # ``_month_is_over`` asked ``calendar.monthrange`` for month 13 and raised
        # ``IllegalMonthError``, which is not a ``CoordinatorError`` and therefore reached the
        # bridge as a crash rather than as an answer. Measured on ``origin/main`` (6d887ec) for
        # both ``"2026-13"`` and ``"2026-00"``.
        return (m, y) if 1 <= m <= 12 else None
    if s.isdigit():                                       # "3" / "03"
        m = int(s)
        return (m, 0) if 1 <= m <= 12 else None
    named = _MONTH_NAMES.get(_norm(s))                    # "março" / "mar" / "September"
    return (named, 0) if named else None


# English month names, written out rather than read from ``calendar.month_name``: that table is
# LOCALE-dependent (it renders through ``strftime('%B')``), so a host whose process happens to
# carry a ``LC_TIME`` would have this vertical's tool output change language behind it. The tool
# surface of this repo is English; a proposal that silently switched to another one would be read
# by the model as data it did not recognise.
_MONTH_LABELS = ("", "January", "February", "March", "April", "May", "June", "July", "August",
                 "September", "October", "November", "December")


def month_label(raw: str) -> str:
    """The period a ``month`` argument ACTUALLY filtered by, as words — ``""`` when it filtered
    by nothing.

    Derived from :func:`_resolve_month`, never from the caller's string, and that is the whole
    point: the filter and the sentence describing it must be the same fact. ``"2026-09"`` filtered
    September 2026 and says so; ``"setembro"`` filtered September of ANY year, so the year is
    absent from the words too — inventing ``2026`` there would name a year the reader never asked
    for and the read never applied. A string the resolver could not understand (``"de"``, a
    typo, empty) applied NO filter at all, and the honest label for no filter is nothing: a
    proposal that cannot say the period simply does not claim one.
    """
    mspec = _resolve_month(raw)
    if not mspec:
        return ""
    month, year = mspec
    return f"{_MONTH_LABELS[month]} {year}" if year else _MONTH_LABELS[month]


def _month_is_over(mspec: tuple[int, int], today: date) -> bool:
    """Did the whole named month already end before ``today``? Naming a FULLY PAST month IS the
    explicit request for the past ("as aulas de agosto"), so the today-onward default steps aside
    for it — while the month IN PROGRESS keeps the cut and shows from today to its end."""
    month, year = mspec
    year = year or today.year
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last < today


def _read_error(sheet_key: str, sheet_id: str, exc: BaseException) -> SheetReadError:
    """One failed spreadsheet read, described TERSELY. The message reaches the model and from
    there the contact, so it carries the status and nothing else: the raw exception text of an
    HTTP client embeds the request URL (and with it the spreadsheet id) into what a person ends
    up reading. The operator still gets the full exception, on the log."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return SheetReadError(sheet_key=sheet_key, sheet_id=sheet_id,
                          message=f"HTTP {status}" if status else type(exc).__name__)


def _parse_date(raw: str) -> Optional[date]:
    """dd/mm/yy, dd/mm/yyyy, or ISO/pandas 'YYYY-MM-DD…' → date; None if unparseable."""
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _date_matches(when: Optional[date], date_str: str, raw: str) -> bool:
    """Does class-entry date (``when``/``date_str``) match a user-supplied ``raw`` date? Tolerant
    of the year being omitted — a user says "remaneja de 16/07 pra 18/07", so ``'16/07'`` matches
    ``16/07/2026`` on day+month; a full date still matches on the exact day. Falls back to a raw
    string compare so a preserved verbatim ``date_str`` always works."""
    s = (raw or "").strip()
    if not s:
        return False
    if s == date_str.strip():
        return True
    parsed = _parse_date(s)
    if parsed and when:
        return parsed == when
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})$", s)      # "dd/mm" with no year → day+month only
    if m and when:
        return when.day == int(m.group(1)) and when.month == int(m.group(2))
    return False


def _year_omitted(raw: str) -> bool:
    """True when ``raw`` is a bare ``dd/mm`` (no year) — matched on day+month only, so it can
    span multiple academic years in a multi-year sheet."""
    return bool(re.match(r"^\s*\d{1,2}[/-]\d{1,2}\s*$", raw or ""))


def _ambiguous_year(matches: "list[ClassEntry]", raw: str) -> bool:
    """A year-less date is ambiguous when it matched entries in MORE THAN ONE year — mutating the
    first (sheet-order) is the coordinator wrong-year bug. A full date, or matches all in the same
    year, is unambiguous."""
    if not _year_omitted(raw):
        return False
    years = {e.when.year for e in matches if e.when}
    return len(years) > 1


@dataclass(frozen=True)
class ProfessorGroup:
    """ONE person, and every spelling of their name the tenant's data carries.

    The faculty-wide estimate used to be keyed on the folded spelling, so a schedule that
    wrote a professor's name out in full on some rows and shortened it on others produced TWO
    blocks of half the pay each — and asking for either spelling by hand returned that half,
    under a header naming the person, with nothing anywhere to say the other half existed. Measured on
    the first real use of the supervision (turn 116): the faculty TOTAL was right all along,
    because every class was counted once; what was broken is the per-person view, which is the
    one somebody pays from.

    ``canonical`` is the FULLEST spelling — the one the sheet writes out, the one a payroll
    line should carry — and ``variants`` the others, which the block names out loud
    (:attr:`PayEstimate.variants`): a merge a reader cannot see is a merge they cannot undo,
    and this one is a guess about a person that a human must be able to check with their eyes.

    ``maybe_same`` names people this refused to merge and a human might still — a spelling
    that fits two declared professors or none, and two tab rows sharing an address their names
    do not corroborate. It is carried on BOTH blocks of such a pair, because whichever one a
    reader opens is where the warning has to be.

    ``shown_as`` is the DECLARED spelling a reader should be shown for these rows when the
    tenant's data resolves the name WITHOUT warranting a merge — and it is a separate field
    from ``canonical`` because those are two different decisions with two different costs. A
    wrong LABEL sends a message to the wrong desk and a human sees the name; a wrong MERGE
    moves money between two people's blocks and nothing on the page says so. So the label may
    be decided on evidence the merge refuses (:func:`_by_discipline_and_token`), never the
    other way round, and where it is set ``maybe_same`` carries the same person: the pay block
    then says out loud that the two were NOT summed, which is what keeps a reader from
    discovering the divergence by arithmetic.
    """
    canonical: str                     # the fullest spelling — what the block is headed with
    keys: tuple[str, ...]              # every folded key that belongs to this person
    variants: tuple[str, ...]          # the OTHER spellings, as the sheet writes them
    maybe_same: tuple[str, ...] = ()   # canonical spellings this might be, and would not merge
    shown_as: str = ""                 # the declared spelling to DISPLAY (never to sum under)


@dataclass(frozen=True)
class CalendarProposal:
    """What ONE calendar send WOULD put in the mail, read and NOT sent.

    Every field is something the read actually produced. There is no field for a fact the
    vertical does not hold, because a proposal is only useful if the person reading it can act
    on it: a count that is off by one, or a month nobody filtered by, is worse than saying
    nothing — the professor agrees to something other than what arrives.

    ``period`` is empty exactly when the read filtered by no month at all (see
    :func:`month_label`), and the renderer omits the clause rather than inventing one.
    """

    events: list[CalendarEvent] = field(default_factory=list)
    recipient: str = ""
    target: str = ""
    period: str = ""
    dropped: int = 0

    @property
    def count(self) -> int:
        """How many calendar entries would go — the number the proposal may state.

        Derived from the events that were actually BUILT, never from the rows that were read:
        a row whose date this system cannot parse produces no event, and it is counted in
        :attr:`dropped` instead. Announcing "12 classes" and mailing 11 is the same defect as
        announcing a send that did not happen, one digit smaller.
        """
        return len(self.events)


class CoordinatorService:
    def __init__(self, store: SpreadsheetStore, config: CoordinatorConfig,
                 *, today: Optional[Callable[[], date]] = None,
                 horizon_days: Optional[int] = None) -> None:
        self.store = store
        self.cfg = config
        self._today: Callable[[], date] = today or (lambda: datetime.now().date())
        # Injectable so a test can state the horizon it is exercising instead of arithmetic
        # against a module constant; 0 disables the forward cut entirely (the old behaviour).
        self.horizon_days: int = (DEFAULT_HORIZON_DAYS if horizon_days is None
                                  else max(0, int(horizon_days)))

    # ── layout + row helpers ─────────────────────────────────────────────────────────
    def _resolve_columns(self, header: list[str], *, width: int = 0) -> ColumnLayout:
        """The layout of one sheet, resolved from its header — plus, for a WRITE, its ``width``.

        ``width`` is how many cells the rows a swap is about actually carry, and it exists
        because a sheet is wider than its header row. The tenant's own schedule tab carries
        columns AFTER the last named one — an hour total, an approval state — with the header
        cell left BLANK, so the header alone says the row ends at ``Professor`` while the row
        goes on for three more cells.

        Bounding the content columns at the last non-empty HEADER is what made ``confirm_swap``
        drop them: a swap exchanged the discipline and the professor and left everything past
        the header behind, so the class moved to its new date and its hour total and its
        "Confirmado" stayed with the old one. Nobody sees that happen — the two rows are both
        still full, just describing each other's class.

        **The fix deliberately does NOT name those columns.** It does not need to: to keep a
        cell you have to carry it, not understand it. A column nobody named cannot be FIXED
        either (``FIXED_COLUMNS`` matches header names), so the honest default for an unnamed
        cell is the one every named content column already has — it belongs to the class, and it
        travels with it. The day somebody opens the sheet and writes those headers in, this
        stays correct: a named column is resolved exactly as before, and a named one the tenant
        adds to ``FIXED_COLUMNS`` stops travelling, which is the escape hatch working.

        ``width`` defaults to 0, so every READ path resolves byte-for-byte what it resolved
        before; only the caller that is about to WRITE passes it, because it is the only one
        that knows which two rows are involved.
        """
        h = [c.strip().lower() for c in header]
        date_idx = next((i for i, c in enumerate(h) if c == self.cfg.column_date.lower()), 0)
        prof_idx = next((i for i, c in enumerate(h) if c == self.cfg.column_professor.lower()), None)
        subj_idx = next((i for i, c in enumerate(h) if c == self.cfg.column_subject.lower()), None)
        last = max((i for i, c in enumerate(header) if c.strip()), default=len(header) - 1)
        time_idx = next((i for i, c in enumerate(h) if c == self.cfg.column_time.lower()), None)
        fixed_names = {_norm(n) for n in self.cfg.fixed_columns}
        fixed = {i for i, c in enumerate(h) if _norm(c) in fixed_names}
        # NOT ``last + 1``: that is the header's width, and the ROW is what gets written.
        content = [i for i in range(max(last + 1, width)) if i not in fixed]
        return ColumnLayout(date_idx, prof_idx, subj_idx, last, fixed, content, time_idx=time_idx)

    @staticmethod
    def _cell(row: list[str], idx: Optional[int]) -> str:
        return row[idx].strip() if idx is not None and idx < len(row) else ""

    def _is_skip(self, subject: str) -> bool:
        n = _norm(subject)
        return any(n == _norm(lbl) for lbl in self.cfg.skip_labels)

    def _is_free(self, subject: str) -> bool:
        n = _norm(subject)
        return any(n == _norm(lbl) for lbl in self.cfg.free_slot_labels)

    def _is_postponed(self, subject: str) -> bool:
        """Does this subject cell say the class was PUT OFF — the whole cell, or its annotation?

        The one predicate here that does not read the cell WHOLE, and the reason is that the
        fact is not written there. The secretary does not replace the discipline with an
        exception label; she appends one, and the class keeps its name:
        ``"<discipline> - Aula adiada"``. Every label comparison in this class had been
        whole-cell, so that row read as an ordinary class and WAS PAID — measured on the
        owner's own tenant (turn 105): R$ 1.440,00 for three classes where two were taught,
        R$ 480,00 of somebody else's money in a figure a human was shown.

        **Why the annotation and not a substring.** The two words the tenant appends to these
        rows are opposites — a class ADIADA was not given, and the ``reposição`` that follows
        it IS the day it was given — so the postponed row must stop paying while the make-up
        row keeps paying, and a fix that matched anywhere in the cell would have taken the
        second one down with the first ("Reposição" is a ``FREE_SLOT_LABEL``: a whole cell that
        says only that is an open slot, and a substring rule would have read the annotated
        make-up as one). It also protects the honest case the other way round: a discipline
        whose own NAME contains one of these words is not an exception, it is a subject, and
        it is paid like any other.

        A postponed class is NOT a :meth:`_is_skip` row and is deliberately not made into one:
        skipping drops it from the listing, and a professor reading their month has to see the
        class that did not happen — the annotation says so in their own words, on the line. It
        is not a free slot either: a free slot was never anybody's class. It is a class that
        was scheduled, moved, and is paid on the day it was actually taught.
        """
        n = _norm(subject)
        ann = _norm(_annotation(subject))
        return any(n == _norm(lbl) or (bool(ann) and ann == _norm(lbl))
                   for lbl in self.cfg.postponed_labels)

    # ── aggregation (the core read) ──────────────────────────────────────────────────
    def aggregate(self, *, include_skip: bool = False, include_free: bool = True,
                  report: Optional[ReadReport] = None) -> list[ClassEntry]:
        """Every schedule row across all configured spreadsheets, dates normalized, sorted
        chronologically (unparseable dates last). Skip-label rows dropped unless asked for.

        **One unreadable spreadsheet does not take the others with it.** A read that raises is
        recorded on ``report`` (and logged) and the loop moves on: a tenant with four course
        spreadsheets and one stale id gets three schedules plus a named failure, instead of a
        turn that ends in "I could not access the schedule". The caller decides what to do with
        the record — the read tools SAY it, ``confirm_swap`` REFUSES on it (a write must not be
        planned against a schedule it only half read)."""
        out: list[ClassEntry] = []
        for key, sid in self.cfg.spreadsheets.items():
            try:
                rows = self.store.read_range(sid, self.cfg.tab_schedule, self.cfg.range_schedule)
            except Exception as exc:                   # noqa: BLE001 — the store is a PORT: any
                _log.warning("coordinator: spreadsheet %r (%s) could not be read: %r",
                             key, sid, exc)            # adapter may raise anything at all
                if report is not None:
                    report.errors.append(_read_error(key, sid, exc))
                continue
            if not rows:
                continue
            header = [c.strip() for c in rows[0]]
            cols = self._resolve_columns(header)
            for r_i, row in enumerate(rows[1:], start=1):
                subject = self._cell(row, cols.subject_idx)
                if self._is_skip(subject) and not include_skip:
                    continue
                free = self._is_free(subject)
                if free and not include_free:
                    continue
                when = _parse_date(self._cell(row, cols.date_idx))
                entry = ClassEntry(
                    sheet_id=sid, sheet_key=key, row_idx=r_i, when=when,
                    date_str=(when.strftime("%d/%m/%Y") if when else self._cell(row, cols.date_idx)),
                    professor=self._cell(row, cols.professor_idx),
                    subject=subject, cells=list(row), header=header)
                entry._free = free  # type: ignore[attr-defined]
                entry._postponed = self._is_postponed(subject)  # type: ignore[attr-defined]
                out.append(entry)
        out.sort(key=lambda e: (e.when is None, e.when or date.max))
        return out

    # ── RBAC-aware professor filter ──────────────────────────────────────────────────
    def _visible(self, entries: list[ClassEntry], *, professor: str, role: str,
                 identity_label: str, report: Optional[ReadReport] = None
                 ) -> tuple[list[ClassEntry], Optional[str]]:
        """Apply role scoping. Returns (filtered, error). A non-oversight caller is pinned to
        their own name; an oversight role may query any professor or all (professor='').

        **A caller the turn could not NAME is refused first, whatever the role says**
        (:data:`_NO_IDENTITY`): with a blank label the non-oversight branch pins the read to
        ``""``, which matches every row, and the oversight branch is a claim nobody is making.
        Both read as "the whole master schedule" — the widest answer this method has — and that
        is the one an unidentified caller must never get. A named supervisor is untouched."""
        if not identity_label.strip():
            return [], _NO_IDENTITY
        oversight = role.upper() in _OVERSIGHT_ROLES
        target = professor.strip()
        if not oversight:
            if target and _norm(target) != _norm(identity_label):
                return [], "You can only view your own schedule."
            # Whole-token equality, never the substring below: «ana» is inside «mariana» (see
            # :func:`_own_spellings`). The universe is ``entries`` itself — every caller hands
            # this method the unfiltered aggregate.
            mine = _own_spellings(identity_label, (e.professor for e in entries))
            if not mine and _near_spellings(identity_label, (e.professor for e in entries)):
                return [], _LABEL_UNRESOLVED      # the IDENTIFICATION failed, not the schedule
            _note_unconfirmed(report, identity_label, mine, (e.professor for e in entries))
            return [e for e in entries if _name_tokens(e.professor) in mine], None
        if not target:                      # oversight + no professor → the whole master schedule
            return entries, None
        n = _norm(target)
        return [e for e in entries if n in _norm(e.professor)], None

    # ── read tools ───────────────────────────────────────────────────────────────────
    def resolve_turmas(self, turma: str) -> list[str]:
        """The configured class-group keys a ``turma`` argument designates (``[]`` = none).

        An empty argument returns ``[]`` too — the caller reads that as "no filter", never as
        "no group matched"; only a NON-empty argument that resolves to nothing is a miss."""
        query = _turma_tokens(turma)
        if not query:
            return []
        return [k for k in self.cfg.spreadsheets if _turma_matches(query, k)]

    def get_professor_schedule(self, *, professor: str = "", role: str = "",
                               identity_label: str = "", month: str = "",
                               discipline: str = "", turma: str = "",
                               include_past: bool = False, apply_horizon: bool = True,
                               report: Optional[ReadReport] = None) -> list[ClassEntry]:
        """A professor's (or, for oversight, anyone's) classes, optionally narrowed by ``month``
        (``'2026-03'``, ``'03'``, or a month name in Portuguese or English — ``'março'``,
        ``'September'``) and/or ``discipline`` (fuzzy, typo-tolerant — 'machne learning' still
        matches 'Machine Learning') and/or ``turma`` (the class group — a bare prefix selects the
        whole family, ``'DSA'`` → ``DSA_33`` and ``DSA_34``).

        **A ``turma`` that designates nothing returns nothing, loudly.** It is recorded on
        ``report.unmatched_turma`` together with the configured names, because the alternative —
        quietly dropping the filter — answers a question nobody asked, and the alternative to
        THAT (guessing which group was meant) is how a wrong list of dates gets a professor to
        the wrong classroom.

        **The window is ``[today, today + horizon_days]`` when the caller named no period.** Both
        ends exist for the same reason and neither is a limit on what may be asked. A schedule
        spreadsheet holds the whole academic year, and the question a professor asks is almost
        always about what is COMING: returning the year and leaving the model to choose is how an
        April opening workshop got read back on a conversation held in September, and — measured
        on the box's own turns — how "traga minhas aulas" answered with 33 classes running into
        June 2027.

        **The forward cut yields to any period the caller NAMED**, because then the period IS the
        question: a ``month`` (even a far one) and ``include_past`` both suppress it. So does a
        ``discipline``, which is a LOOKUP for one named thing — "when is the opening workshop?"
        must not be answered "nothing" by a horizon when the answer exists two months out. A
        ``turma`` does not: it narrows WHOSE upcoming classes, not WHEN, so the default stands.
        ``report.beyond_horizon`` records that the cut acted, so the footer can name the argument
        that widens it — a BIT, never a count (see ``server._fmt_report``).

        **``apply_horizon=False`` is for a caller that is not READING a list**, and the calendar
        export is the whole of it. A default that exists so a professor does not have to scroll
        past June has no business deciding what lands in their calendar: a "send me my classes"
        that quietly exported 3 of 6 would be the same wrong answer this window was meant to
        stop, delivered somewhere the contact cannot see it. The forward end is a READING
        comfort; the past end (``include_past``) is a real question about scope and is NOT
        waived here.

        Past classes come back only when the caller asks — ``include_past=True``, or by naming a month that has already ENDED, which
        is the same request said differently. The cut is by DAY, not by clock: a class earlier
        TODAY still counts as today, because "what do I have today" asked at 3pm must not answer
        an empty list. Entries whose date could not be parsed are never cut — the filter refuses
        to hide what it cannot date. ``report.hidden_past`` counts what the cut removed, so a
        caller can say "from today onward" ONLY when something was actually left out."""
        entries, err = self._visible(self.aggregate(report=report), professor=professor,
                                     role=role, identity_label=identity_label, report=report)
        if err:
            raise CoordinatorAccessError(err)
        return self._filter_schedule(entries, month=month, discipline=discipline, turma=turma,
                                     include_past=include_past, apply_horizon=apply_horizon,
                                     report=report)

    def _filter_schedule(self, entries: list[ClassEntry], *, month: str = "",
                         discipline: str = "", turma: str = "", include_past: bool = False,
                         apply_horizon: bool = True,
                         report: Optional[ReadReport] = None) -> list[ClassEntry]:
        """The ``turma``/``month``/``discipline``/window narrowing of
        :meth:`get_professor_schedule`, over entries ALREADY scoped by role.

        Split out, unchanged, so the faculty-wide pay estimate can apply the listing's exact
        filters to ONE read it has already made: it needs the whole grid first (to know who the
        professors are) and the same rows narrowed afterwards, and reading the spreadsheets
        twice for that would report every read error twice. Every rule here is the listing's,
        byte for byte — the docstring above is the specification."""
        if turma.strip():
            keys = self.resolve_turmas(turma)
            if not keys:
                if report is not None:
                    report.unmatched_turma = turma.strip()
                    report.known_turmas = tuple(self.cfg.spreadsheets)
                return []
            wanted = set(keys)
            entries = [e for e in entries if e.sheet_key in wanted]
        mspec = _resolve_month(month)
        if mspec:
            mm, yy = mspec
            entries = [e for e in entries if e.when and e.when.month == mm
                       and (yy == 0 or e.when.year == yy)]
        if discipline.strip():
            entries = [e for e in entries if _fuzzy_match_discipline(discipline, e.subject)]
        if not include_past:
            today = self._today()
            if not (mspec and _month_is_over(mspec, today)):
                kept = [e for e in entries if e.when is None or e.when >= today]
                if report is not None:
                    report.hidden_past += len(entries) - len(kept)
                entries = kept
            if (apply_horizon and self.horizon_days > 0 and not mspec
                    and not discipline.strip()):
                horizon = today + timedelta(days=self.horizon_days)
                near = [e for e in entries if e.when is None or e.when <= horizon]
                if report is not None and len(near) != len(entries):
                    report.beyond_horizon = True
                entries = near
        return entries

    def check_deadlines(self, *, professor: str = "", role: str = "",
                        identity_label: str = "",
                        report: Optional[ReadReport] = None) -> list[ClassEntry]:
        """Disciplines whose LAST class already happened and are within the 14-day grace window
        (grades/attendance still due). Keyed by (sheet, professor, subject)."""
        entries, err = self._visible(self.aggregate(report=report), professor=professor,
                                     role=role, identity_label=identity_label, report=report)
        if err:
            raise CoordinatorAccessError(err)
        today = self._today()
        last_of: dict[tuple, date] = {}
        for e in entries:
            if e.when is None or e.is_free_slot:
                continue
            k = (e.sheet_id, _norm(e.professor), _norm(e.subject))
            if k not in last_of or e.when > last_of[k]:
                last_of[k] = e.when
        due: list[ClassEntry] = []
        for e in entries:
            if e.when is None or e.is_free_slot:
                continue
            k = (e.sheet_id, _norm(e.professor), _norm(e.subject))
            if last_of.get(k) == e.when and e.when < today <= e.when + timedelta(days=GRADE_GRACE_DAYS):
                due.append(e)
        return due

    def weekly_briefing(self, *, professor: str = "", role: str = "",
                        identity_label: str = "",
                        report: Optional[ReadReport] = None) -> list[ClassEntry]:
        """Classes in the next 7 days (inclusive of today).

        Already ``[today, today+7]`` — the "no past classes" default needs nothing here, and
        that is worth saying out loud so nobody adds a second cut on top of this one."""
        entries, err = self._visible(self.aggregate(report=report), professor=professor,
                                     role=role, identity_label=identity_label, report=report)
        if err:
            raise CoordinatorAccessError(err)
        today = self._today()
        horizon = today + timedelta(days=BRIEFING_HORIZON_DAYS)
        return [e for e in entries if e.when and today <= e.when <= horizon]

    def find_replacement_slot(self, *, professor: str = "", role: str = "",
                              identity_label: str = "",
                              report: Optional[ReadReport] = None) -> list[ClassEntry]:
        """Free slots (FREE_SLOT_LABELS) within the next 21 days — candidates for a swap.

        The pool is nobody's, so ``role`` and ``professor`` do not narrow it — but the CALLER
        still has to be somebody (:data:`_NO_IDENTITY`). A free slot is a row of the tenant's
        schedule, and this door is the one place the identity arguments would otherwise be
        declared and never read: a guard nobody can see is the shape the faculty door had."""
        if not identity_label.strip():
            raise CoordinatorAccessError(_NO_IDENTITY)
        today = self._today()
        horizon = today + timedelta(days=REPLACEMENT_HORIZON_DAYS)
        # free slots are not professor-owned; oversight sees all, a professor sees the pool too
        return [e for e in self.aggregate(include_free=True, report=report)
                if e.is_free_slot and e.when and today <= e.when <= horizon]

    def ibope_status(self, *, professor: str = "", role: str = "",
                     identity_label: str = "",
                     report: Optional[ReadReport] = None) -> list[ClassEntry]:
        """LAST classes of a discipline that fall on TODAY — the mechanism behind the survey
        (IBOPE) reminder. The specific threshold/wording (e.g. '30% for the bonus') is the
        persona prompt's job; the vertical only identifies WHICH classes need the nudge."""
        entries, err = self._visible(self.aggregate(report=report), professor=professor,
                                     role=role, identity_label=identity_label, report=report)
        if err:
            raise CoordinatorAccessError(err)
        today = self._today()
        last_of: dict[tuple, date] = {}
        for e in entries:
            if e.when is None or e.is_free_slot:
                continue
            k = (e.sheet_id, _norm(e.professor), _norm(e.subject))
            if k not in last_of or e.when > last_of[k]:
                last_of[k] = e.when
        return [e for e in entries if e.when == today and not e.is_free_slot
                and last_of.get((e.sheet_id, _norm(e.professor), _norm(e.subject))) == today]


    # ── the day, in one call (COMPOSED — nothing here is a new read) ─────────────────
    def daily_checks(self, *, professor: str = "", role: str = "",
                     identity_label: str = "",
                     report: Optional[ReadReport] = None) -> DailyChecks:
        """Everything "o que tenho hoje?" asks, from the three predicates that already answer it.

        **Composition, not a fourth predicate.** Today's classes are :meth:`weekly_briefing`
        narrowed to today; the deadlines are :meth:`check_deadlines` verbatim, each paired with
        how much of its grace window is left; the survey trigger is :meth:`ibope_status`
        verbatim. Nothing here re-decides what "the last class" or "still due" means — those
        definitions have one home each, and a correction to any of them arrives here without
        this method being touched.

        **The deadline split is "closing today" vs "closing later", and that is the ONLY split
        this data supports.** A genuinely OVERDUE deadline is INVISIBLE to this vertical:
        ``check_deadlines`` keeps ``last_class < today <= last_class + GRADE_GRACE_DAYS``, so a
        discipline whose last class was more than fourteen days ago is filtered out at the
        source and reaches nothing downstream. Widening that window would change a shipped
        tool's meaning for every one of its callers, so it is stated here rather than done —
        see :class:`~cogno_praxis.coordinator.types.DeadlineDue`.

        **``report`` is passed to the FIRST composed call only, and the reason is arithmetic
        rather than taste.** All three predicates aggregate the SAME spreadsheets with the same
        arguments, so a tenant with one unreachable sheet would record that one failure three
        times and the footer would announce "3 spreadsheet(s) could not be read" over a single
        stale id. One read's worth of trouble must be reported once.

        Read-only, like every predicate under it: there is no branch here that writes, and the
        only write path in this service is :meth:`confirm_swap`, which nothing here calls.
        """
        today = self._today()
        # FIRST — and therefore the one call that carries the report (see above).
        week = self.weekly_briefing(professor=professor, role=role,
                                    identity_label=identity_label, report=report)
        due = self.check_deadlines(professor=professor, role=role,
                                   identity_label=identity_label)
        ibope = self.ibope_status(professor=professor, role=role,
                                  identity_label=identity_label)
        return DailyChecks(
            classes_today=[e for e in week if e.when == today],
            # ``e.when`` is not Optional here: ``check_deadlines`` drops undated rows itself.
            deadlines=[DeadlineDue(entry=e,
                                   days_left=(e.when + timedelta(days=GRADE_GRACE_DAYS)
                                              - today).days)
                       for e in due if e.when is not None],
            ibope_today=list(ibope))

    # ── the professor's OWN pay (read-only, self-only) ───────────────────────────────
    def _workload_by_subject(self, sheet_id: str, sheet_key: str,
                             report: Optional[ReadReport]) -> Optional[dict[str, float]]:
        """``{normalised discipline: TOTAL workload}`` from the tenant's declared hours column —
        or ``None`` when that column is NOT THERE to be read.

        The tab, the range and the column all come from the config. Nothing here looks for a
        header that "seems like" hours: only :attr:`CoordinatorConfig.column_hours`, matched the
        same way :meth:`_resolve_columns` matches the other three roles. A tenant who has not
        declared it never reaches this method — the column is OPTIONAL and the caller skips the
        read (2026-09-22: the workload is context, not a factor of the pay).

        **``None`` and ``{}`` are different answers.** ``None`` says the sheet carries no such
        column at all (the tab is empty, unreadable, or its header does not name the column);
        a dict says the column exists and names whatever rows it names. The distinction is what
        lets a declared-but-absent column be IGNORED: the tenant's rules will say
        ``COLUMN_HOURS: <a name>`` over a tab that has no column by that name, and the estimate
        must come out whole — classes × HOURS_PER_CLASS × rate, bonus and all — with the context
        section simply not rendered, never a refusal and never "NOT CONFIGURED" on its account.
        A discipline missing from a column that DOES exist is the other case: it becomes "carga
        não declarada na planilha" in the context section. Never a zero, in either case.
        """
        try:
            rows = self.store.read_range(sheet_id, self.cfg.tab_hours, self.cfg.range_hours)
        except Exception as exc:                       # noqa: BLE001 — the store is a PORT
            _log.warning("coordinator: hours tab of %r (%s) could not be read: %r",
                         sheet_key, sheet_id, exc)
            if report is not None:
                report.errors.append(_read_error(sheet_key, sheet_id, exc))
            return None
        if not rows:
            return None
        header = [c.strip().lower() for c in rows[0]]
        h_idx = next((i for i, c in enumerate(header)
                      if c == self.cfg.column_hours.strip().lower()), None)
        s_idx = next((i for i, c in enumerate(header)
                      if c == self.cfg.column_subject.strip().lower()), None)
        if h_idx is None or s_idx is None:
            # Declared in the rules, absent on the sheet: CONTEXT the tenant cannot have, and
            # nothing else. Logged so an operator can see the name does not match; never raised,
            # never reported as a read error — the estimate does not depend on this column.
            _log.warning("coordinator: hours tab %r of %r has no %r/%r column — the workload "
                         "context is skipped, the estimate is unaffected",
                         self.cfg.tab_hours, sheet_key, self.cfg.column_hours,
                         self.cfg.column_subject)
            return None
        out: dict[str, float] = {}
        for row in rows[1:]:
            subject = self._cell(row, s_idx)
            hours = parse_money(self._cell(row, h_idx))
            if subject and hours is not None and hours > 0:
                out.setdefault(_norm(subject), hours)
            elif subject:
                _log.debug("coordinator: %r on %r carries no readable hour total", subject,
                           sheet_key)
        return out

    def _ibope_result(self, *, identity_label: str, report: Optional[ReadReport],
                      universe: Iterable[str] = ()) -> Optional[float]:
        """The caller's own IBOPE percentage, or ``None`` — and ``None`` means NOT FOUND.

        ``None`` covers four different worlds on purpose, because they all license the same
        answer and none of them licenses a figure: the tenant declared no IBOPE tab, the tab was
        unreadable, no row names this professor, or SEVERAL rows do and disagree. That last one
        is the reason this returns rather than picks. Two results and a choice between them is
        an invented bonus wearing a real number, and the professor cannot tell which it was.

        **Which rows are this professor's is :func:`_same_professor`'s question, not a
        substring's.** It used to be ``want in _norm(cell)``, and a name is not a prefix of a
        person: «Ana» took «Ana Silva»'s survey result, «Silva» took every Silva's, and the
        winner was whichever one happened to be the only match — a bonus of R$ 30,00 or
        R$ 40,00 an hour landing on somebody else's pay, or a real result lost to a
        disagreement between two rows about two different people. The predicate is the one
        :meth:`_professor_universe` groups by, for the reason the two questions are one: a row
        belongs to a person, and this file may not hold two answers to that.

        **And pairwise was not enough: it is :func:`_own_spellings`, with the THIRD-NAME guard,
        over the survey tab AND the schedule (``universe``).** Measured on ``6c07c7a``: labelled
        «Ana Lopes», a survey tab holding only «Ana Maria Lopes» (92 %) and a schedule that also
        carries «Ana Beatriz Lopes» — the caller was handed Ana Maria's 92 % and the R$ 40,00/h
        band, because «Ana Lopes» ⊂ «Ana Maria Lopes» agrees on first and last name and the pair
        cannot see that «Ana Beatriz Lopes» fits the label just as well. The schedule's names
        are the universe because the survey tab is usually a subset of the people: the person
        who could claim a result is often only on the schedule.
        """
        tab, col = self.cfg.tab_ibope.strip(), self.cfg.column_ibope.strip()
        if not tab or not col:
            return None
        read: list[tuple[str, float]] = []
        for key, sid in self.cfg.spreadsheets.items():
            try:
                rows = self.store.read_range(sid, tab, self.cfg.range_ibope)
            except Exception as exc:                   # noqa: BLE001 — the store is a PORT
                _log.warning("coordinator: IBOPE tab of %r (%s) could not be read: %r",
                             key, sid, exc)
                if report is not None:
                    report.errors.append(_read_error(key, sid, exc))
                continue
            if not rows:
                continue
            header = [c.strip().lower() for c in rows[0]]
            v_idx = next((i for i, c in enumerate(header) if c == col.lower()), None)
            p_idx = next((i for i, c in enumerate(header)
                          if c == self.cfg.column_professor.strip().lower()), None)
            if v_idx is None or p_idx is None:
                continue
            for row in rows[1:]:
                pct = parse_money(self._cell(row, v_idx).rstrip("%"))
                if pct is not None:
                    read.append((self._cell(row, p_idx), pct))
        mine = _own_spellings(identity_label, [cell for cell, _ in read] + list(universe))
        found = {pct for cell, pct in read if _name_tokens(cell) in mine}
        return found.pop() if len(found) == 1 else None

    # ── the professor's pay: their OWN for every role; by name or faculty-wide for oversight ──
    def _pay_config(self) -> tuple[float, float]:
        """``(rate, hours_per_class)`` — or the refusal every estimate shares, whoever it is for.

        A REQUIRED key missing, or a figure the rules describe in PROSE that no ``KEY: value``
        line declares — either refuses, and the sentence names what was found where. The
        second is the 2026-09-22 defect: rules that plainly said "R$ 120,00 por hora" were
        answered "PAY_RATE_PER_HOUR is missing", which was true and told nobody what to do.
        A band the parser could not read REFUSES THE WHOLE ESTIMATE, and it names the entry:
        dropping it would be the worse of the two available wrongs — the professor is paid
        less and the reply is word-for-word the one a tenant with no bonus scheme gets, so
        nobody has anything to notice. ONE configuration serves every professor of the tenant,
        so this is checked once per call and never per person.
        """
        missing = self.cfg.pay_undeclared
        prose = self.cfg.pay_in_prose
        if missing or prose:
            raise CoordinatorConfigError(pay_refusal(missing, prose))
        bad = self.cfg.ibope_bonus_unreadable
        if bad:
            named = "; ".join(repr(b) for b in bad)
            raise CoordinatorConfigError(
                f"IBOPE_BONUS in the persona rules has {len(bad)} band(s) this system cannot "
                f"read: {named}. A band is 'min-max=amount' or 'min+=amount', and bands are "
                f"separated by SEMICOLONS (a comma is a decimal separator). Nothing is estimated "
                f"until that line is fixed — a bonus band that is silently skipped pays less.")
        rate = self.cfg.pay_rate_per_hour
        hours_per_class = self.cfg.hours_per_class
        assert rate is not None                        # pay_undeclared already refused a None
        assert hours_per_class is not None             # likewise — never inferred, never divided
        return rate, hours_per_class

    def _pay_window(self, entries: list[ClassEntry], period: str) -> list[ClassEntry]:
        """The estimate's own period rule, applied AFTER the listing's filters.

        The estimate reads the WHOLE month, classes already given included (the caller passes
        ``include_past=True``, always). The listing hides past classes unless asked — a
        professor reading a list wants what is coming — and the estimate inherited that:
        measured on a live turn (2026-09-22, turn 104), "quanto recebo pelas aulas de setembro"
        asked mid-month came back as «1 aula», the two classes already taught cut as "past".
        Pay is not a reading convenience: the month is the month, given and to give. A NAMED
        period is therefore read in full; an EMPTY one is the current month in full plus
        everything onward — cut here at the first day of the month, because ``include_past``
        with no month would otherwise hand back every class of the academic year.
        """
        if _resolve_month(period):
            return entries
        month_start = self._today().replace(day=1)
        return [e for e in entries if e.when is None or e.when >= month_start]

    def _payable(self, e: ClassEntry) -> bool:
        """A row that counts as a CLASS GIVEN: dated, with a discipline, not a free slot, not
        put off, and not one the professor answered NO to.

        The first three are what a row has to BE. The last two are what the tenant's own sheet
        SAYS ABOUT IT, in the two places they write it, and both were being read past:

        * **put off** (:attr:`ClassEntry.is_postponed`) — the discipline carries a
          ``" - Aula adiada"`` annotation, and the make-up row that follows names the date it
          is making up for. Both were paid. Measured on the owner's tenant, turn 105:
          R$ 1.440,00 where the truth was R$ 960,00, shown to a human as a figure.
        * **declined** (:meth:`class_response` = ``RSVP_DECLINED``) — the professor answered the
          invitation with a NO, ``record_class_response`` wrote the tenant's own word for it
          into ``COLUMN_STATUS``, the listing has been showing it since, and the pay never
          looked at the column at all. A class somebody declined is a class nobody taught.

        **Only an explicit decline stops the money.** ``PENDING`` pays, and so does a status
        cell holding something this system did not write (``None`` — a note a secretary left).
        The asymmetry is the point: an answer is a fact, and its ABSENCE is not the opposite
        fact. Refusing to pay an unanswered class would invent a decline out of a silence and
        dock somebody who simply taught without replying to an e-mail, which is the same class
        of error as paying a class that never happened, pointed at the person instead of at the
        institution.
        """
        if e.is_free_slot or e.when is None or not e.subject.strip():
            return False
        if e.is_postponed:
            return False
        return self.class_response(e) != RSVP_DECLINED

    def _pay_estimate(self, entries: list[ClassEntry], *, rate: float, hours_per_class: float,
                      period: str, professor: str, ibope_label: str,
                      report: Optional[ReadReport], variants: tuple[str, ...] = (),
                      maybe_same: tuple[str, ...] = (),
                      universe: tuple[str, ...] = ()) -> PayEstimate:
        """The arithmetic over entries ALREADY scoped to ONE person — the same code whether that
        person is the caller, a professor an oversight role named, or one of everybody.

        ``classes × HOURS_PER_CLASS × rate``, bucketed by (class group, sortable year-month) so
        the two grouping axes the answer promises are the two axes it is actually ordered by;
        the workload column read only when the tenant NAMED one (with no column there is no
        header to look for, and looking anyway is the sniffing this class refuses); the IBOPE
        result looked up under ``ibope_label`` — the caller's identity label for their own
        estimate, the sheet's spelling of the professor otherwise. ``professor`` is stamped on
        the result and rendered as its second line when non-empty.
        """
        workload_declared = bool(self.cfg.column_hours.strip())
        workload_by_sheet: dict[str, Optional[dict[str, float]]] = {}
        buckets: dict[tuple[str, tuple[int, int]], dict[str, int]] = {}
        workload_missing: list[str] = []
        for e in entries:
            if not self._payable(e) or e.when is None:
                continue
            if workload_declared and e.sheet_key not in workload_by_sheet:
                workload_by_sheet[e.sheet_key] = self._workload_by_subject(
                    e.sheet_id, e.sheet_key, report)
            k = (e.sheet_key, (e.when.year, e.when.month))
            buckets.setdefault(k, {})
            buckets[k][e.subject.strip()] = buckets[k].get(e.subject.strip(), 0) + 1
        # READ on at least one sheet — the condition the context section renders under. A
        # column declared in the rules and found on no sheet is ignored: same block as a tenant
        # who never declared it, byte for byte, and no error anywhere.
        workload_read = any(m is not None for m in workload_by_sheet.values())

        groups: list[PayGroup] = []
        for (turma_key, (year, month)) in sorted(buckets):
            lines: list[PayLine] = []
            for subject, count in buckets[(turma_key, (year, month))].items():
                workload = (workload_by_sheet.get(turma_key) or {}).get(_norm(subject))
                if workload_read and workload is None and subject not in workload_missing:
                    workload_missing.append(subject)
                lines.append(PayLine(subject=subject, classes=count,
                                     hours_per_class=hours_per_class, workload=workload))
            groups.append(PayGroup(turma=turma_key, month=f"{month:02d}/{year}", lines=lines))

        pct = self._ibope_result(identity_label=ibope_label, report=report, universe=universe)
        return PayEstimate(
            rate=rate, hours_per_class=hours_per_class, groups=groups,
            workload_read=workload_read, workload_missing=tuple(workload_missing),
            tiers=self.cfg.ibope_bonus, ibope_found=pct is not None, ibope_pct=pct,
            ibope_tab=self.cfg.tab_ibope.strip(), period=month_label(period),
            ibope_min_response_pct=self.cfg.ibope_min_response_pct, professor=professor,
            variants=variants, maybe_same=maybe_same)

    def _professor_universe(self, entries: list[ClassEntry],
                            report: Optional[ReadReport]) -> dict[str, str]:
        """Every professor the tenant's data names — ``{folded name: the spelling to show}``,
        sorted by the folded name so every worker renders the same order.

        **Keyed on the schedule's ``COLUMN_PROFESSOR``, with the professors tab as a
        COMPLEMENT** — and that order is measured, not chosen. On the live turns this exists
        for (2026-09-22, turns 111/112/115) the professors tab answered "No faculty records
        found." on all three: the declared tab name did not match the sheet's. A universe read
        off the tab alone would have grouped nobody; the schedule's own column is the one source
        that cannot be empty while there are classes to pay for. The tab still contributes a
        professor who has no class in the period, which is exactly the name a schedule-only
        read would lose — and losing a name from a faculty-wide total reads as "not paid".

        The schedule's spelling wins when both name the same person (``setdefault``): it is the
        spelling the listing shows, so the estimate and the list say the same name.
        """
        out: dict[str, str] = {}
        for e in entries:
            name = e.professor.strip()
            if name:
                out.setdefault(_norm(name), name)
        for name, _rec in self._faculty_records(report):
            out.setdefault(_norm(name), name)
        return dict(sorted(out.items()))

    def _declared_people(
            self, report: Optional[ReadReport]) -> list[tuple[str, list[str], tuple[str, ...]]]:
        """**Layer one of two: the CAST** — the people the tenant's professors tab DECLARES,
        as ``(fullest spelling, every spelling of them)``, in the tab's own order.

        Two rows are one person when they share an E-MAIL ADDRESS **and** one name is an
        abbreviation of the other (:func:`_is_abbreviation_of`). Both halves are required, and
        which half is doing what is the point: **the address is CORROBORATION, not AUTHORITY.**
        It is a cell a human types into a spreadsheet nobody validates, and the shapes that
        make it lie are ordinary ones — a departmental mailbox, the secretary's address copied
        down a column, a paste into the wrong row. Two colleagues sharing a first name and a
        ``secretaria@`` address would otherwise become one person, and one of them would be
        paid for the other's classes with nothing on the page to show it.

        A shared address that the names do not corroborate joins NOTHING and is said out loud
        instead — both rows keep their block and each names the other
        (:attr:`ProfessorGroup.maybe_same`), and the refusal is logged with the two spellings
        and never the address. Measured on the tenant this was written for: 16 spellings, 15
        people, ONE join (same first name, one name contained in the other), ZERO refusals.
        This branch changes no figure today; it is a condition for the day the tab says
        something else, which is the only day it could cost anybody anything.

        **What the pairing costs, stated because it is a real loss:** a person whose family
        name CHANGED and who kept their address — «Maria Silva» and «Maria Souza» on one
        e-mail — no longer joins. It does not occur in this tenant's data, the direction of
        the error is the safe one (a sum that is short), and the outcome is visible: two
        blocks and a note on each. Parked by name: ``mudanca-de-apelido-com-o-mesmo-email``.

        The address never leaves this method — not to a caller, not to a log line, not to a
        rendered block. It is read, compared, and dropped.
        """
        rows = self._faculty_records(report)
        names = [name for name, _ in rows]
        mails: dict[str, set[str]] = {}
        for name, rec in rows:
            raw = _declared_column(rec, "mail")
            mails[name] = {m.strip().lower()
                           for m in raw.replace(",", ";").split(";") if m.strip()}
        parent: dict[str, str] = {name: name for name in names}

        def root(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        unsettled: list[tuple[str, str]] = []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if not (mails[a] & mails[b]):
                    continue
                ta, tb = _name_tokens(a), _name_tokens(b)
                if not (_is_abbreviation_of(ta, tb) or _is_abbreviation_of(tb, ta)):
                    _log.warning("coordinator: %r and %r share an e-mail address, but neither "
                                 "name is the other written out — NOT joined; check the "
                                 "professors tab", a, b)
                    unsettled.append((a, b))
                    continue
                ra, rb = root(a), root(b)
                if ra != rb:
                    parent[rb] = ra
        grouped: dict[str, list[str]] = {}
        for name in names:
            grouped.setdefault(root(name), []).append(name)
        cast = [(max(v, key=lambda s: len(_name_tokens(s))), v) for v in grouped.values()]
        canon = {s: c for c, v in cast for s in v}
        warn: dict[str, set[str]] = {}
        for a, b in unsettled:
            warn.setdefault(canon[a], set()).add(canon[b])
            warn.setdefault(canon[b], set()).add(canon[a])
        return [(c, v, tuple(sorted(warn.get(c, ())))) for c, v in cast]

    def _professor_groups(self, entries: list[ClassEntry],
                          report: Optional[ReadReport]) -> tuple[ProfessorGroup, ...]:
        """**Layer two: every spelling in the data, anchored to the cast** — one
        :class:`ProfessorGroup` per person, ordered by the folded canonical so every worker
        renders the tenant the same way.

        A spelling off the SCHEDULE is resolved against the people
        :meth:`_declared_people` returned: the same one written out, or an abbreviation of it
        — same first token, every token of the short one present in the long one — **and only
        when exactly ONE declared person fits**. Two candidates is not a tie to break, it is a
        question this cannot answer: the spelling gets its own block and both candidates are
        named on it, because choosing between two people is how one of them gets paid for the
        other's classes.

        A spelling that fits nobody keeps its block too, and names the declared people who
        share its first name so a reader can settle it in a second.

        **A spelling that fits NOBODY gets one more question asked of it, and the answer is a
        LABEL and never a sum** (:func:`_by_discipline_and_token` →
        :attr:`ProfessorGroup.shown_as`): the declared people who teach a DISCIPLINE this
        spelling teaches on the schedule, intersected with those sharing a TOKEN of its name,
        and only when exactly one is left. That is the MISSPELT name — the shape containment
        cannot reach, because a wrong word is not a missing one — and it is the shape that sent
        the measured turn wrong. **The classes do not move**: the spelling keeps its own block,
        its own figures and its own key, and the person it resolved to is named on
        ``maybe_same`` so the pay block still says the two were not summed. Two candidates, or
        none, and not even the label is decided.

        **The second jump is asked only where the first found NOBODY**, never to break a tie
        the first one raised: a spelling fitting two declared people is a question about two
        people, and a discipline they both teach is not an answer to it — it is a coincidence
        of the timetable. That refusal is unchanged, byte for byte.

        **Against the CAST, never between loose spellings, and that is what makes it a rule
        rather than a coincidence.** Comparing spellings pairwise cannot tell two
        abbreviations of ONE declared name, each cutting a different half of it, from two
        colleagues who merely share a first name; anchored, both resolve to the person the
        tenant declared, and neither is compared to the other at all. Counted over the 32
        spellings the tenant's two sources carry: requiring first AND last token to agree joins
        7 pairs and MISSES 7 more, every one of those seven one person, because the commonest
        abbreviation is the one that drops the family name.

        **Nothing joins without a declaration.** A tenant whose professors tab is empty — the
        live shape of 2026-09-22, when the declared tab name matched no sheet — gets exactly
        the blocks it got before, one per spelling, and not one note: with no cast there is
        no candidate to name, and inventing one out of the schedule alone is the pairwise
        guessing this design refuses. The honest failure is a sum that is SHORT and says so.
        """
        universe = self._professor_universe(entries, report)
        cast = self._declared_people(report)
        declared: dict[str, int] = {}                  # folded declared spelling → cast index
        for i, (_canonical, spellings, _warn) in enumerate(cast):
            for s in spellings:
                declared.setdefault(_norm(s), i)
        # The two halves of the second jump, each read off DECLARED data: who the tab says
        # teaches what, and what each schedule spelling is written beside. The schedule side is
        # the rows this call was HANDED — a listing resolves the names it is about to show —
        # so a narrower read is narrower evidence, and narrower evidence refuses more often.
        teaches = self._declared_disciplines(declared, report)
        taught: dict[str, set[str]] = {}               # folded schedule spelling → disciplines
        for e in entries:
            k, d = _norm(e.professor), _norm(_discipline(e.subject))
            if k and d:
                taught.setdefault(k, set()).add(d)
        members: dict[int, list[str]] = {i: [] for i in range(len(cast))}
        # (universe key, the people it may be, the declared spelling to SHOW it under)
        alone: list[tuple[str, tuple[str, ...], str]] = []
        for key, spelling in universe.items():
            at = declared.get(key)
            if at is None:
                hits = [i for i, (canonical, _s, _w) in enumerate(cast)
                        if _is_abbreviation_of(_name_tokens(spelling), _name_tokens(canonical))]
                if len(hits) > 1:
                    # NOT a tie to break: two declared people fit and this cannot say which, so
                    # the spelling keeps its own block and names both. The second jump is NOT
                    # asked here — a discipline two candidates share is a fact about the
                    # timetable, not an answer about which of them this is.
                    alone.append((key, tuple(cast[i][0] for i in hits), ""))
                    continue
                if not hits:
                    # NOBODY the containment reaches — the MISSPELT spelling, the one shape a
                    # rule about MISSING words cannot describe. One more question is asked of
                    # it, and the answer decides the NAME SHOWN and never the money
                    # (:func:`_by_discipline_and_token`, :attr:`ProfessorGroup.shown_as`).
                    guess = _by_discipline_and_token(spelling, taught.get(key, set()),
                                                     cast, teaches)
                    maybe = tuple(cast[i][0] for i in guess)
                    if not maybe:
                        # Nobody at all: name the declared people who share its first name,
                        # which is the shortest list a human can settle.
                        first = _name_tokens(spelling)[:1]
                        maybe = tuple(c for c, _s, _w in cast
                                      if first and _name_tokens(c)[:1] == first)
                    shown = universe.get(_norm(maybe[0]), maybe[0]) if len(guess) == 1 else ""
                    alone.append((key, maybe, shown))
                    continue
                at = hits[0]
            members[at].append(key)
        # The canonical is the DECLARED person, spelt as the universe spells that same folded
        # name — which is the schedule's spelling when both sources carry it, the rule
        # :meth:`_professor_universe` already follows so that the estimate and the listing say
        # the same name. Without this, a tab that shouts a name the schedule writes normally
        # would render a "these spellings are one person" line over a difference of CASE, which
        # is a notice about nothing standing where a real join is supposed to be visible.
        head = [universe.get(_norm(c), c) for c, _s, _w in cast]
        groups = [
            ProfessorGroup(canonical=head[i], keys=tuple(keys),
                           variants=tuple(universe[k] for k in keys if universe[k] != head[i]),
                           maybe_same=cast[i][2])
            for i, keys in members.items()] + [
            ProfessorGroup(canonical=universe[key], keys=(key,), variants=(),
                           maybe_same=maybe, shown_as=shown)
            for key, maybe, shown in alone]
        return tuple(sorted(groups, key=lambda g: _norm(g.canonical)))

    def canonical_professor_names(self, entries: list[ClassEntry]) -> dict[str, str]:
        """``{folded spelling as the schedule writes it: the spelling to SHOW}`` for these rows.

        **The listing's answer to a question nobody downstream can answer for itself.** The
        schedule is where a name is TYPED and the identity directory is where it is DECLARED,
        and they disagree: measured on the live turn this comes from, the schedule's full
        spelling of a professor finds nobody in the directory — not even a suggestion — while
        his declared spelling finds him and his bare FIRST NAME finds him too. So the complete
        wrong spelling is worse than half a right one, and the listing was handing the model
        exactly that: the model read the name off the briefing, passed it to the tool that
        notifies a person, the tool found nobody, and the owner was asked for the full name of
        the professor he had just asked us to warn.

        Rendering the canonical here is what keeps every consumer out of it. A resolution done
        at each consumer is a rule each of them gets wrong alone; done at the SOURCE, the name
        that leaves this vertical is the name the tenant declared, and the next reader — a
        model, a notifier, a payroll line — needs to learn nothing.

        Two spellings answer, in this order: :attr:`ProfessorGroup.shown_as` — the declared
        name a MISSPELT spelling resolved to, which is a label and never a sum — and otherwise
        the group's ``canonical``, which is the declared name its rows are already summed
        under. A spelling that resolves to nobody maps to ITSELF, so a tenant with no
        professors tab (the live shape of 2026-09-22, when the declared tab name matched no
        sheet) renders the schedule's own spelling exactly as it always did. **Nothing here can
        leave a name out**: every folded key of these rows is in exactly one
        :class:`ProfessorGroup`.

        **The LISTING and the REMUNERATION BLOCK can therefore show DIFFERENT spellings of the
        same person, and that is deliberate rather than an oversight.** This map is read by the
        listing, so a resolved spelling reaches a reader the way the faculty tab DECLARES it;
        the remuneration block names every estimate :attr:`PayEstimate.professor`, which is the
        group's ``canonical`` — and for a spelling that was only ever a LABEL, that is still the
        schedule's own. The same professor can be «as the tab declares him» on the schedule
        listing and «as the sheet types him» on the pay block, on the same day, over the same
        rows.

        The two surfaces answer two questions whose wrong answers cost different ORDERS OF
        MAGNITUDE, and that is the whole reason the field is separate. The listing exists so
        that somebody — a person, or the tool that notifies one — can FIND the professor: a
        wrong name there is on a screen, read by a human, and corrected in the next sentence.
        The block exists so that nobody is paid for somebody else's classes: a wrong name there
        has already moved money, and there is no one left to see it. So the LABEL is decided on
        evidence the SUM refuses (:attr:`ProfessorGroup.shown_as`), never the other way round —
        and the divergence is never silent, because the same resolution puts that person on
        ``maybe_same``, so the block states out loud that the two spellings were NOT summed.

        No ``report``: this is a DISPLAY refinement over a tab the listing does not otherwise
        read, and a tab it cannot read means "no cast", which is already the documented
        degradation. Announcing it in a schedule listing's error footer would report a failure
        of something the reader did not ask for — the failure is logged, and
        ``get_professor_info`` is the door that surfaces it.
        """
        return {key: (g.shown_as or g.canonical)
                for g in self._professor_groups(entries, None) for key in g.keys}

    def _resolve_professor(self, target: str, entries: list[ClassEntry],
                           report: Optional[ReadReport]) -> ProfessorGroup:
        """The ONE professor an oversight role's ``professor=<name>`` designates — as a
        :class:`ProfessorGroup`, every spelling of them included — or a refusal saying why
        there is not exactly one.

        The matching rule is the OVERSIGHT branch of :meth:`_visible` (the non-oversight one
        is :func:`_own_spellings`), applied to the universe instead of to the rows:
        accent-stripped, case-folded SUBSTRING (``"silva"`` inside ``"ana silva"``), no
        ``difflib`` and no typo tolerance — nothing the listing does not do, and nothing it
        does that this does not. What this adds, and the listing has no need for, is the
        refusal when the name matches MORE THAN ONE professor: the listing shows each of
        their lines with the professor on it, so a supervisor sees two people; the estimate
        would sum both under one name, which is the bare-sum defect in a new coat — ``"Ana"``
        is inside ``"Mariana"``. A name that matches nobody refuses too, rather than answering
        "no classes" about a person who does not exist.

        **It searches the GROUPS, so a name that matches two SPELLINGS of one person is not an
        ambiguity** — it used to be, and worse: asking by the SHORT spelling matched only the
        short rows, because a folded substring is a test on a STRING and a two-word name is not
        inside the four-word one it abbreviates. The supervisor got a block headed with the name
        they asked for, holding half the classes, with nothing to say so. Both halves now answer
        under the declared spelling, and the block says which spellings it summed.
        """
        n = _norm(target)
        hits = [g for g in self._professor_groups(entries, report)
                if any(n in key for key in g.keys)]
        if not hits:
            raise CoordinatorError(
                f'No professor matching "{target}" in the schedule or the faculty records — '
                f"nothing to estimate under that name. Check the spelling or list the faculty.")
        if len(hits) > 1:
            names = ", ".join(g.canonical for g in hits)
            raise CoordinatorError(
                f'"{target}" matches {len(hits)} professors — {names}. Name one of '
                f"them; an estimate that summed them would be one figure about two people.")
        return hits[0]

    def estimate_professor_pay(self, *, professor: str = "", role: str = "",
                               identity_label: str = "", period: str = "", turma: str = "",
                               report: Optional[ReadReport] = None) -> PayEstimate:
        """What ONE professor's classes in ``period`` come to, grouped by class group and month
        — the caller's own for every role; a professor named by an oversight role.

        **Three doors, decided by the argument and the role — and ``""`` is the caller, for
        everyone.** An EMPTY ``professor`` is the person asking, whatever their role: a
        supervisor asking "quanto eu recebo" gets THEIR pay, never the faculty's (the old
        ``professor=""`` = master-schedule defect is described at :meth:`estimate_faculty_pay`).
        A ``professor`` naming somebody ELSE is answered for an oversight role
        (``_OVERSIGHT_ROLES`` — the coordinator is the person a professor's pay is a working
        fact for; the owner's own words, 2026-09-23: "o supervisor pode ter acesso a todos os
        professores, pois ele é o coordenador") and REFUSED to every other role with the same
        sentence it always was — that refusal is the privacy rule for everyone who is not the
        coordination, and it does not move. The name is resolved exactly as the listing
        resolves it (:meth:`_resolve_professor`), the estimate is stamped with the sheet's
        spelling of it (:attr:`PayEstimate.professor`), and the classes read are the ones the
        listing would show for that name. :data:`ALL_PROFESSORS` (``"*"``) is the third door
        and lives in :meth:`estimate_faculty_pay`; here it is refused to a non-oversight role
        like any other name and, for an oversight role, redirected — this method returns ONE
        person's estimate and a sum of several is a different type on purpose. Naming
        YOURSELF is the first door (same person, same block). An unauthenticated caller (no
        ``identity_label``) raises, because with nobody named "their own" has no referent.

        **Every estimate says WHOSE it is** (:attr:`PayEstimate.professor` → the block's
        second line, ``Professor: <name>``): the caller's own label on the first door, the
        sheet's spelling of the professor on the second. The figure was never wrong on turns
        111/112 — the reader's belief about whom it belonged to was, and a header is the
        cheapest thing that can correct a belief.

        Refuses with :class:`CoordinatorConfigError` when the tenant's rules do not declare the
        rate or the hours per class, NAMING the keys — see
        :attr:`CoordinatorConfig.pay_undeclared` — and, when the rules DESCRIBE a figure in
        prose instead ("R$ 120,00 por hora", "4 horas por aula"), naming what it found and the
        key each should have been (:attr:`CoordinatorConfig.pay_in_prose`). There is no
        branch that estimates without them, and none that reads a sentence as a number.

        The arithmetic is ``classes × HOURS_PER_CLASS × rate``, plus an IBOPE bonus per hour
        when — and only when — a survey result was actually read. The discipline's total
        workload (``COLUMN_HOURS``, optional) is CONTEXT rendered beside it and is never a
        factor. The month is read WHOLE — classes already given included — for a named
        ``period`` and, when none is named, for the current month plus everything onward; the
        listing's "from today onward" default is a reading convenience this method does not
        inherit (:meth:`_pay_window`). It is READ-ONLY: nothing here writes to a spreadsheet,
        sends anything, or records a figure.
        """
        me = identity_label.strip()
        if not me:
            raise CoordinatorAccessError(
                "This estimate is only ever about the person asking, and this turn carries no "
                "identified professor.")
        target = professor.strip()
        oversight = role.upper() in _OVERSIGHT_ROLES
        if target == ALL_PROFESSORS:
            if not oversight:
                raise CoordinatorAccessError(_OWN_PAY_ONLY)
            raise CoordinatorError(
                f"professor={ALL_PROFESSORS!r} is every professor at once — that is "
                f"estimate_faculty_pay, one block per professor; this estimate is one person's.")
        if target and _norm(target) != _norm(me):
            if not oversight:
                raise CoordinatorAccessError(_OWN_PAY_ONLY)
            rate, hours_per_class = self._pay_config()
            # ONE read of the schedule: the universe (to resolve the name) and the rows (the
            # listing's own role filter, by the same folded substring) come off the same grid.
            everything = self.aggregate(report=report)
            group = self._resolve_professor(target, everything, report)
            # The rows are the GROUP's, not the canonical spelling's: ``_visible`` matches a
            # folded substring, and the short spelling of a name is not a substring of the long
            # one, so filtering by the canonical would answer with the half of the classes that
            # happen to be written out in full. The access check above is what ``_visible``
            # would have contributed here, and it has already run.
            rows = [e for e in everything if _norm(e.professor) in group.keys]
            rows = self._filter_schedule(rows, month=period, turma=turma, include_past=True,
                                         apply_horizon=False, report=report)
            return self._pay_estimate(self._pay_window(rows, period), rate=rate,
                                      hours_per_class=hours_per_class, period=period,
                                      professor=group.canonical, ibope_label=group.canonical,
                                      variants=group.variants, maybe_same=group.maybe_same,
                                      report=report,
                                      universe=tuple(e.professor for e in everything))
        rate, hours_per_class = self._pay_config()
        # ``apply_horizon=False``, for the reason the calendar export already opts out: the
        # 30-day default exists so a professor READING a list does not have to scroll, and this
        # is not a list. An estimate silently cut at 30 days answers "quanto eu recebo" with
        # part of the months and no sign that it did — which is the export's "3 of 6" defect
        # said about money, where the reader has no way at all to notice the shortfall. A named
        # ``period`` still filters exactly as it does everywhere else.
        # ``professor=me``, NOT ``professor=""``, and the empty string is the whole defect this
        # line was carrying. ``_visible`` reads an EMPTY ``professor`` as "no filter", which for
        # a non-oversight caller means "pin them to their own name" and for an oversight one
        # means THE MASTER SCHEDULE — every professor's classes, in one list. Delegating with an
        # empty argument handed an oversight role in BULK what the guard above refused by NAME,
        # and labelled the sum as the caller's OWN pay. Measured on a seeded sheet before the
        # fix: EMPLOYEE 12 h/R$ 1.440,00 (hers), SUPERVISOR 16 h/R$ 1.920,00 — the extra 4 h
        # being another professor's class. So the caller's own name is passed EXPLICITLY and the
        # same filter does the rest: for a non-oversight role this is byte-for-byte the path
        # that already ran (``_visible`` sets ``target = identity_label``, and ``me`` IS
        # ``identity_label``), and for an oversight role it narrows instead of widening. The
        # faculty-wide answer an oversight role may now ask for is a DIFFERENT door
        # (:data:`ALL_PROFESSORS`), one block per professor, never this path widened.
        #
        # Written out rather than delegated to ``get_professor_schedule`` — the same three calls
        # it makes, in the same order — for ONE reason: the survey lookup needs the schedule's
        # whole cast (``universe``, see :meth:`_ibope_result`), and the listing does not return
        # it. One read of the grid, as on the oversight door above.
        everything = self.aggregate(report=report)
        entries, err = self._visible(everything, professor=me, role=role, identity_label=me,
                                     report=report)
        if err:
            raise CoordinatorAccessError(err)
        entries = self._filter_schedule(entries, month=period, turma=turma, include_past=True,
                                        apply_horizon=False, report=report)
        # ``professor=me`` on the RESULT too — the ownership header (2026-09-23, the owner's
        # confirmation: «um valor sem dono é tão perigoso como um valor sem leitura»). Turns
        # 111/112 handed a SUPERVISOR his own block under a header that did not say whose it
        # was, and the reply called it the faculty's totals; the number was right and the
        # reader was wrong about whom it belonged to. So every block says whose it is: the
        # caller's own label here, the sheet's spelling on the two oversight doors.
        return self._pay_estimate(self._pay_window(entries, period), rate=rate,
                                  hours_per_class=hours_per_class, period=period,
                                  professor=me, ibope_label=me, report=report,
                                  universe=tuple(e.professor for e in everything))

    def estimate_faculty_pay(self, *, role: str = "", identity_label: str = "",
                             period: str = "", turma: str = "",
                             report: Optional[ReadReport] = None) -> FacultyPayEstimate:
        """EVERY professor's estimate for ``period``, one :class:`PayEstimate` each — the
        oversight role's "os valores de todos os professores", and the door behind
        :data:`ALL_PROFESSORS`.

        **Oversight only.** A non-oversight role gets the refusal it gets for naming anybody
        else — byte for byte — because "everyone" contains everyone else. The oversight role
        reads the MASTER schedule (the listing's own ``professor=""`` filter) and the rows are
        partitioned by the schedule's ``COLUMN_PROFESSOR``, folded — EXACT folded equality,
        not the substring the by-name door uses, because here nobody typed a name: a row
        belongs to the professor written on it. The set of professors is
        :meth:`_professor_universe` (the schedule's column, plus the professors tab as a
        complement), so a professor the tenant's data names but who has no class in the period
        appears with NO groups and renders as "0 aulas" rather than vanishing from a total.

        The result is a LIST of estimates and a total that says how many people it sums —
        never one figure. That is the shape the 2026-09-22 turns 111/112/115 asked for and
        could not get: with ``professor=""`` a supervisor received their OWN estimate under
        a header that did not say so, and the reply called it «Totais de setembro por turma».
        A figure with no owner in a coordinator's hands is the bulk-sum defect one step later.
        Rows whose professor cell is EMPTY are counted on
        :attr:`FacultyPayEstimate.unassigned_classes` and rendered as such — not folded into
        anybody's block, not dropped. Configuration refusals are :meth:`_pay_config`'s, once
        for the call: one set of rules serves every professor.
        """
        if not identity_label.strip():
            raise CoordinatorAccessError(_NO_IDENTITY)
        if role.upper() not in _OVERSIGHT_ROLES:
            raise CoordinatorAccessError(_OWN_PAY_ONLY)
        rate, hours_per_class = self._pay_config()
        everything = self.aggregate(report=report)
        groups = self._professor_groups(everything, report)
        names = tuple(e.professor for e in everything)
        master, err = self._visible(everything, professor="", role=role,
                                    identity_label=identity_label)
        assert err is None                             # an oversight role is never refused here
        rows = self._pay_window(
            self._filter_schedule(master, month=period, turma=turma, include_past=True,
                                  apply_horizon=False, report=report), period)
        # A row belongs to the PERSON its spelling resolves to, not to the spelling. Every
        # folded key in the universe is in exactly one group — a name that fell out here would
        # be a professor silently paid nothing — so the lookup below cannot miss.
        at = {key: i for i, g in enumerate(groups) for key in g.keys}
        by_person: dict[int, list[ClassEntry]] = {i: [] for i in range(len(groups))}
        unassigned = 0
        for e in rows:
            key = _norm(e.professor)
            if not key:
                unassigned += self._payable(e)
                continue
            by_person[at[key]].append(e)
        estimates = tuple(
            self._pay_estimate(by_person[i], rate=rate, hours_per_class=hours_per_class,
                               period=period, professor=g.canonical, ibope_label=g.canonical,
                               variants=g.variants, maybe_same=g.maybe_same, report=report,
                               universe=names)
            for i, g in enumerate(groups))
        return FacultyPayEstimate(rate=rate, hours_per_class=hours_per_class,
                                  estimates=estimates, unassigned_classes=unassigned,
                                  period=month_label(period))

    def get_professor_info(self, *, professor: str = "", role: str = "",
                           identity_label: str = "",
                           report: Optional[ReadReport] = None) -> list[dict[str, str]]:
        """Faculty details from the professors tab (``TAB_PROFESSORS``/``RANGE_PROFESSORS`` — e.g.
        Disciplina, CH, Professor, e-mail, titulação), one dict per row keyed by lowercased header.
        RBAC parity with the schedule: a non-oversight caller only sees THEIR OWN row (pinned to
        their identity label); oversight sees everyone. Returns ``[]`` when no professors tab is
        configured. The specific columns are tenant-defined; the vertical stays column-agnostic."""
        if not identity_label.strip():
            raise CoordinatorAccessError(_NO_IDENTITY)
        if not self.cfg.tab_professors:
            return []
        oversight = role.upper() in _OVERSIGHT_ROLES
        target = professor.strip()
        if not oversight and target and _norm(target) != _norm(identity_label):
            raise CoordinatorAccessError("You can only view your own faculty details.")
        records = self._faculty_records(report)
        if not oversight:
            # The schedule's rule (:func:`_own_spellings`), not a substring: the record holds
            # the e-mail a calendar is sent to, and «Ana» used to get «Mariana Lopes»'s.
            mine = _own_spellings(identity_label, (name for name, _rec in records))
            if not mine and _near_spellings(identity_label, (name for name, _rec in records)):
                raise CoordinatorAccessError(_LABEL_UNRESOLVED)
            _note_unconfirmed(report, identity_label, mine, (name for name, _rec in records))
            return [rec for name, rec in records if _name_tokens(name) in mine]
        want = _norm(target)
        return [rec for name, rec in records if not want or want in _norm(name)]

    def _faculty_records(self, report: Optional[ReadReport]) -> list[tuple[str, dict[str, str]]]:
        """Every row of the professors tab across the spreadsheets, as ``(name, record)`` — one
        per distinct folded name, first spelling wins, sheet order; ``[]`` when no tab is
        configured or none carries a row (the live case of 2026-09-22: "No faculty records
        found." on every turn, because the declared tab name did not match the sheet's).

        The read :meth:`get_professor_info` has always made, minus its role filter, so the
        faculty-wide pay estimate can take the names as a COMPLEMENT to the schedule's own
        professor column without a second copy of the tab-reading loop.

        **What the dedup DESTROYS, said here because a reader of this method cannot see it.**
        The tab's row is a DISCIPLINE, not a person: somebody who teaches four of them is on
        four rows. The first row wins and carries ITS discipline with it, so the other three
        disciplines — every one but one, per person — leave with the rows they were written on.
        For a name-keyed caller (the cast, the universe complement, the contact lookup) that
        loss is exactly right: the name is the same on all four rows. For the question "who
        does the tenant say teaches this?" it is fatal, and that question is half of
        :func:`_by_discipline_and_token` — a spelling teaching the fourth discipline would find
        nobody declared to teach it and stay unresolved. So that caller reads
        :meth:`_faculty_rows`: ONE tab-reading loop, two readings of it, never a second reader
        that can drift from this one."""
        out: list[tuple[str, dict[str, str]]] = []
        seen: set[str] = set()
        for name, rec in self._faculty_rows(report):
            dedup = _norm(name)
            if dedup in seen:
                continue
            seen.add(dedup)
            out.append((name, rec))
        return out

    def _faculty_rows(self, report: Optional[ReadReport]) -> list[tuple[str, dict[str, str]]]:
        """EVERY row of the professors tab across the spreadsheets, as ``(name, record)`` — the
        tab as it is written, sheet order, nothing folded away; ``[]`` when no tab is configured.

        The tab's unit is the row, and its row is a DISCIPLINE: the same professor appears once
        per discipline they teach, with that discipline's workload beside them. That is exactly
        the fact :meth:`_declared_disciplines` needs and exactly the fact
        :meth:`_faculty_records` folds away — the first row of a person wins and takes its
        discipline with it — so the two readings are split and the tab-reading loop still exists
        once. :meth:`_faculty_records` is expressed OVER this one, rather than beside it, so
        there is no second reader to disagree with the first about what a row is.
        """
        out: list[tuple[str, dict[str, str]]] = []
        if not self.cfg.tab_professors:
            return out
        for key, sid in self.cfg.spreadsheets.items():
            try:
                rows = self.store.read_range(sid, self.cfg.tab_professors,
                                             self.cfg.range_professors)
            except Exception as exc:                   # noqa: BLE001 — same port contract as
                _log.warning("coordinator: professors tab of %r (%s) could not be read: %r",
                             key, sid, exc)            # aggregate(): one sheet, not the request
                if report is not None:
                    report.errors.append(_read_error(key, sid, exc))
                continue
            if not rows:
                continue
            header = [c.strip().lower() for c in rows[0]]
            prof_key = next((h for h in header if "professor" in h), "")
            for row in rows[1:]:
                if row and row[0].strip().lower() == header[0]:      # skip repeated header rows
                    continue
                rec = {h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(header)}
                name = rec.get(prof_key, "")
                if not name:
                    continue
                out.append((name, rec))
        return out

    def _declared_disciplines(self, declared: dict[str, int],
                              report: Optional[ReadReport]) -> dict[str, set[int]]:
        """``{folded discipline: the cast the tab says teaches it}`` — cast indices, from
        ``declared`` (``{folded declared spelling: index}``).

        The tenant's OWN declaration of who teaches what, read off the column the tab already
        carries and used for nothing else: it is half of :func:`_by_discipline_and_token`, and
        it is the half that stops a shared first name from deciding anything. A row whose name
        is not in the cast (nothing in today's data — the cast is built from these same rows)
        contributes nothing rather than inventing a person.
        """
        out: dict[str, set[int]] = {}
        for name, rec in self._faculty_rows(report):
            at = declared.get(_norm(name))
            if at is None:
                continue
            key = _norm(_discipline(_declared_column(rec, "disciplin")))
            if key:
                out.setdefault(key, set()).add(at)
        return out

    # ── the calendar export (a write: it leaves the house) ───────────────────────────
    def entry_time(self, entry: ClassEntry) -> str:
        """The class hour as canonical ``HH:MM``, or ``""`` when the sheet records none.

        Read through the SAME layout resolution every other field goes through, so a tenant
        who has no ``COLUMN_TIME`` column simply gets ``""`` — never a guessed hour."""
        cols = self._resolve_columns(entry.header)
        return parse_time(self._cell(entry.cells, cols.time_idx))

    def calendar_events(self, entries: list[ClassEntry], *,
                        describe: Optional[Callable[[ClassEntry], str]] = None
                        ) -> list[CalendarEvent]:
        """The datable classes as calendar events, identified by CONTENT.

        Rows whose date could not be parsed are DROPPED, and that is the one thing this method
        hides: a calendar entry needs a day, and inventing one would put a professor in a
        classroom on a date nobody wrote. The caller compares the two lengths and says how many
        were left out — the same contract ``ReadReport.hidden_past`` has for the read tools.
        """
        out: list[CalendarEvent] = []
        for e in entries:
            if e.when is None:
                continue
            time = self.entry_time(e)
            turma = e.sheet_key.strip()
            subject = e.subject.strip() or "Aula"
            summary = f"{subject} — {turma}" if turma else subject
            out.append(CalendarEvent(
                uid=class_event_uid(turma=turma, subject=subject, day=e.when,
                                    date_str=e.date_str, time=time),
                summary=summary, day=e.when, time=time,
                description=describe(e) if describe else ""))
        return out

    def professor_email(self, *, professor: str = "", role: str = "", identity_label: str = "",
                        identity_email: str = "",
                        report: Optional[ReadReport] = None) -> str:
        """The address the target professor's calendar goes to — ``""`` when there is none.

        TWO sources, in a DECLARED order, because they answer the question with different
        authority:

        1. the HOST DIRECTORY (``identity_email``, injected by the host's RBAC and never
           fillable by the model) — but ONLY when the target IS the caller, because that is the
           only person the host authenticated. It wins there: it is the address the
           institution's own directory holds for them.
        2. the tenant's PROFESSORS TAB, read through :meth:`get_professor_info` and therefore
           under the very same role scoping — a professor sees their own row, an oversight role
           sees anyone's. This is the only source for an oversight caller sending SOMEONE
           ELSE'S calendar, and the fallback when the directory has no address on file.

        The order is stated rather than implied because the two can disagree, and a recipient
        resolved by whichever source happened to answer first is how a calendar reaches the
        wrong mailbox.
        """
        if not identity_label.strip():
            raise CoordinatorAccessError(_NO_IDENTITY)
        target = (professor or "").strip() or identity_label.strip()
        if not target:
            return ""
        own = bool(identity_label.strip()) and _norm(target) == _norm(identity_label)
        if own and identity_email.strip():
            return identity_email.strip()
        for rec in self.get_professor_info(professor=target, role=role,
                                           identity_label=identity_label, report=report):
            for header, value in rec.items():
                if "mail" in header and "@" in value:
                    return value.strip()
        return ""

    def _prepare_calendar(
            self, *, sender: Optional[CalendarSender], professor: str, role: str,
            identity_label: str, identity_email: str, month: str, turma: str,
            describe: Optional[Callable[[ClassEntry], str]],
            report: Optional[ReadReport]
    ) -> tuple[CalendarSender, list[CalendarEvent], str, str, int]:
        """Everything a calendar send needs, READ and not yet sent:
        ``(sender, events, recipient, target, dropped)``.

        ONE method behind the proposal and behind the send, and that is the property, not a
        refactor: a proposal is worth something only if it describes the send that would
        actually happen. Two copies of this sequence are two chances for the sentence a
        professor agrees to to stop matching the e-mail that arrives — a wrong count is the
        same defect as an announced send that did not happen, one digit smaller.

        **It RAISES on every path that cannot send**, and the proposal inherits every one of
        those refusals unchanged: the sentences already end in "Nothing was sent", which is
        true of a proposal too. A preview that offered to send a calendar this deployment has
        no mail server for would be a promise nobody can keep.

        ``sender`` comes back NARROWED (never ``None``) because the check that rules it out
        lives here; returning it is how the caller uses it without re-testing what this method
        already decided.
        """
        entries = self.get_professor_schedule(
            professor=professor, role=role, identity_label=identity_label, month=month,
            turma=turma, apply_horizon=False, report=report)
        # WHO the calendar is about, resolved exactly as ``_visible`` resolves it: an oversight
        # caller means whoever they named (empty = the whole master schedule), everyone else is
        # pinned to themselves. Reading it as "the named one, else me" would quietly turn a
        # supervisor's master-schedule request into their own calendar.
        oversight = role.upper() in _OVERSIGHT_ROLES
        target = (professor or "").strip() if oversight else identity_label.strip()
        if oversight and not target:
            raise CoordinatorError(
                "Name the professor whose calendar to send — a calendar is one person's, so "
                "the whole master schedule has no single recipient. Nothing was sent.")
        if not entries:
            raise CoordinatorError(
                f"No upcoming classes were found for {target or 'this professor'}, so there is "
                f"nothing to put in a calendar. Nothing was sent.")
        events = self.calendar_events(entries, describe=describe)
        dropped = len(entries) - len(events)
        if not events:
            raise CoordinatorError(
                "None of the classes found carries a date this system could read, so no "
                "calendar entry could be built. Nothing was sent.")
        recipient = self.professor_email(professor=professor, role=role,
                                         identity_label=identity_label,
                                         identity_email=identity_email, report=report)
        if not recipient:
            raise CoordinatorError(
                f"There is no e-mail address on file for {target}, so there is nowhere to send "
                f"the calendar. This is a missing address, not a failure — ask them to have it "
                f"recorded. Nothing was sent.")
        if sender is None:
            raise CoordinatorError(
                "No e-mail is configured for this institution, so the calendar cannot be sent "
                "from here. Nothing was sent — offer to read the classes out instead.")
        # The ORGANIZER, checked HERE and not at the send, because both paths come through this
        # method and a proposal that offers a send this deployment will refuse is the broken
        # promise the docstring above forbids.
        #
        # ``organizer()`` is allowed to answer "" — a mail config with neither a declared
        # ``from_email`` nor an authenticated ``user`` has no From address to give, and the
        # adapter says so honestly rather than inventing one. Until now nothing read that ""
        # and ``build_ics_calendar`` rendered ``ORGANIZER:mailto:`` into a message that went
        # out anyway. With ``RSVP=TRUE`` the events now ASK for a reply, and every reply is
        # addressed to the ORGANIZER — so an empty one is an invitation with nowhere to answer,
        # and this stops being cosmetic.
        #
        # A CONFIG error, not a plain one: the wrapper renders it "NOT CONFIGURED", which is
        # what somebody can actually go and fix, and never as a system that broke. And it NAMES
        # the keys, the same way the pay estimate does — a refusal that does not say which line
        # to add is a dead end wearing a sentence.
        if not sender.organizer()[0].strip():
            raise CoordinatorConfigError(
                "The calendar mailer declares no address to send FROM, so the invitation would "
                "have no ORGANIZER and the professor's reply would have nowhere to go. Set "
                "`from_email` (or the authenticated `user`) in this institution's SMTP "
                "configuration. Nothing was sent, and nothing will be until that is declared.")
        return sender, events, recipient, target, dropped

    def preview_schedule_to_calendar(
            self, *, sender: Optional[CalendarSender], professor: str = "", role: str = "",
            identity_label: str = "", identity_email: str = "", month: str = "",
            turma: str = "", describe: Optional[Callable[[ClassEntry], str]] = None,
            report: Optional[ReadReport] = None) -> CalendarProposal:
        """What the SAME arguments would send — read, described, and NOT sent.

        This is the proposal half of a two-step send, and it exists because the question the
        contact is asked has to be GROUNDED in what was read. The alternative was measured on
        2026-09-06: the executor picked the send, a confirmation gate held it by NAME before it
        could read anything, and the only thing any layer downstream had left to render was the
        call's own argument — the contact was asked *"Confirmo: esta ação — 2026-09. Posso
        seguir?"*, which names no count, no destination and no month a person would recognise.
        A gate that stops the call cannot ask the skill's question for it; a read that runs can.

        It builds no ``.ics`` and touches no mailer — the events are built (that is where the
        COUNT comes from, and how a row this system cannot date is excluded from it) and then
        described. Nothing about this method can put a message in the mail; the send is a
        separate call the user still has to agree to.
        """
        _snd, events, recipient, target, dropped = self._prepare_calendar(
            sender=sender, professor=professor, role=role, identity_label=identity_label,
            identity_email=identity_email, month=month, turma=turma, describe=describe,
            report=report)
        return CalendarProposal(events=events, recipient=recipient, target=target,
                                period=month_label(month), dropped=dropped)

    async def send_schedule_to_calendar(
            self, *, sender: Optional[CalendarSender], professor: str = "", role: str = "",
            identity_label: str = "", identity_email: str = "", month: str = "",
            turma: str = "", tz_name: str = "", subject_line: str = "",
            describe: Optional[Callable[[ClassEntry], str]] = None,
            sequence: Optional[int] = None,
            report: Optional[ReadReport] = None) -> tuple[int, str, int]:
        """Mail the target professor's upcoming classes as ONE ``.ics``. Returns
        ``(events_sent, recipient, classes_dropped)``.

        **It RAISES on every path that did not send**, and that is a contract, not a style: a
        FastMCP tool that RETURNS a sentence is a successful call, and a successful call on a
        tool the server marks non-read-only is stamped ``side_effect=True`` by the MCP bridge —
        so a polite "there is no e-mail configured" would make the turn count as a WRITE that
        never happened, in the very accounting (``committed_this_turn``) the house uses to
        decide whether a promise was kept. Raising lands as ``isError`` → ``ok=False`` →
        ``side_effect=False``. The one non-error return of this method IS a completed send.

        The read underneath is :meth:`get_professor_schedule` — the same call, the same
        ``_visible`` scoping, the same today-onward window. Nothing here can widen it.
        """
        snd, events, recipient, _target, dropped = self._prepare_calendar(
            sender=sender, professor=professor, role=role, identity_label=identity_label,
            identity_email=identity_email, month=month, turma=turma, describe=describe,
            report=report)
        org_email, org_name = snd.organizer()
        ics = build_ics_calendar(
            events, organizer_email=org_email, organizer_name=org_name, attendee=recipient,
            tz_name=tz_name, sequence=sequence_now() if sequence is None else sequence,
            duration_minutes=self.cfg.class_duration_minutes)
        body = (f"{len(events)} aula(s) em anexo, no formato de calendário (.ics). "
                f"Abra o anexo para importar tudo de uma vez.")
        ok = await snd.send(to=recipient, subject=subject_line or "Suas aulas",
                            body=body, ics=ics)
        if not ok:
            raise CoordinatorError(
                "The e-mail server did NOT accept the message, so the calendar was not "
                "delivered. Nothing was sent — say exactly that and try again later.")
        return len(events), recipient, dropped

    # ── the spreadsheet write ────────────────────────────────────────────────────────
    def _why_not_a_destination(self, src: ClassEntry, new_date: str) -> str:
        """WHY this date cannot receive the class — the sentence a bare refusal owes the reader.

        A destination has to be one of the tenant's own free-slot labels (``FREE_SLOT_LABELS``,
        e.g. "Livre, Reposição"). Everything else is refused, and the refusal used to be one
        sentence for four different worlds: "No free slot found on 18/07 in the same schedule."
        That is true and it is useless. It cannot tell the reader whether the date is not in the
        schedule at all, whether it is a holiday, or whether it already has a class on it — and
        those want three different next moves. A contact who is not told why simply tries
        another date, and then another.

        So this looks the date up AGAIN, this time with the skip rows included, purely to
        DIAGNOSE. It is a read: nothing here decides whether the swap happens — the caller has
        already decided it does not — and nothing here writes.

        **It names the obstacle, never the person behind it.** "That date already has a class"
        is the reason; whose class it is, is somebody else's schedule, and the access rule that
        governs the rest of this vertical does not stop being true inside an error message. The
        acceptable labels ARE named, because they are the tenant's own vocabulary and the reader
        cannot guess them.
        """
        same_day = [e for e in self.aggregate(include_skip=True, include_free=True)
                    if e.sheet_id == src.sheet_id and _date_matches(e.when, e.date_str, new_date)]
        allowed = ", ".join(self.cfg.free_slot_labels) or "(none configured)"
        if not same_day:
            return (f"{new_date} is not a date in this schedule, so there is no slot to move the "
                    f"class into. A destination has to be an open slot already on the sheet "
                    f"({allowed}).")
        skipped = [e for e in same_day if self._is_skip(e.subject)]
        if skipped and len(skipped) == len(same_day):
            return (f"{new_date} is marked \"{skipped[0].subject}\" in this schedule — no class "
                    f"can be moved onto it. A destination has to be an open slot ({allowed}).")
        return (f"{new_date} already has a class scheduled, so it is not an open slot. A class "
                f"can only be moved onto a slot the sheet marks as open ({allowed}) — pick one "
                f"of those, or free this date first. Nothing has been changed.")

    def confirm_swap(self, *, professor: str, original_date: str, new_date: str,
                     role: str = "", identity_label: str = "") -> tuple[ClassEntry, ClassEntry]:
        """Swap a professor's class (source, by date+professor) into a free slot (dest, by
        date+free-label): exchanges the CONTENT columns, leaving fixed columns (dates) put.
        Returns (source, dest) as they were located. Raises if either can't be found.

        **Refuses outright when any spreadsheet failed to read.** The read tools degrade to a
        partial answer and say so; a WRITE must not, because a half-read schedule cannot tell
        "that class is not there" from "the sheet holding it did not load" — and the second one,
        acted on, moves the wrong row."""
        report = ReadReport()
        entries = self.aggregate(include_free=True, report=report)
        if report.errors:
            unread = ", ".join(f"{e.sheet_key} ({e.message})" for e in report.errors)
            raise CoordinatorError(
                f"Cannot swap right now: {len(report.errors)} spreadsheet(s) could not be read "
                f"({unread}) — the schedule is only partly loaded. Try again shortly.")
        vis, err = self._visible(entries, professor=professor, role=role,
                                 identity_label=identity_label)
        if err:
            raise CoordinatorAccessError(err)
        src_matches = [e for e in vis if _date_matches(e.when, e.date_str, original_date)]
        if not src_matches:
            raise CoordinatorError(f"No class found for that professor on {original_date}.")
        if _ambiguous_year(src_matches, original_date):
            raise CoordinatorError(
                f"'{original_date}' matches classes in more than one year — please include the "
                f"year (e.g. {original_date}/{src_matches[0].when.year if src_matches[0].when else ''}).")
        src = src_matches[0]
        dst_matches = [e for e in entries if e.is_free_slot and e.sheet_id == src.sheet_id
                       and _date_matches(e.when, e.date_str, new_date)]
        if not dst_matches:
            raise CoordinatorError(self._why_not_a_destination(src, new_date))
        if _ambiguous_year(dst_matches, new_date):
            raise CoordinatorError(
                f"'{new_date}' matches free slots in more than one year — please include the year.")
        dst = dst_matches[0]
        # The WIDTH comes from the two rows being written, not from the header: a cell the
        # header does not reach is still a cell, and leaving it behind is what desynchronised
        # the hour total and the approval state from the class that moved.
        cols = self._resolve_columns(src.header, width=max(len(src.cells), len(dst.cells)))
        self.store.swap_rows(src.sheet_id, self.cfg.tab_schedule, self.cfg.range_schedule,
                             src.row_idx, dst.row_idx, content_cols=cols.content_indices)
        return src, dst

    # ── the answer to an invitation ──────────────────────────────────────────────────
    def status_column_index(self, header: list[str]) -> Optional[int]:
        """Where the tenant's ``COLUMN_STATUS`` sits in one sheet's header — ``None`` if absent.

        By NAME, never by position, which is the same rule ``server._entry_status`` reads by and
        the reason ``types.DailyChecks`` refuses to interpret the blank-headered approval column
        the live corpus carries. A STATE field resolved positionally starts reporting — and here,
        WRITING — the wrong column the day somebody inserts one, silently."""
        want = _norm(self.cfg.column_status)
        if not want:
            return None
        return next((i for i, c in enumerate(header) if _norm(c) == want), None)

    def record_class_response(self, *, class_date: str, answer: str, professor: str = "",
                              role: str = "", identity_label: str = "", turma: str = "",
                              report: Optional[ReadReport] = None) -> tuple[ClassEntry, str, bool]:
        """Record a professor's answer to ONE class invitation. Returns ``(entry, state, changed)``.

        ``changed`` is ``False`` when the sheet already said this — the second "sim" to the same
        invitation is the SAME state, not a second one, and it writes nothing.

        **What links an answer to a class is the DATE the answer names, and nothing else.** There
        is no message id to hang it on: the invitation goes out as a calendar e-mail, the answer
        arrives as a chat turn, the vertical is a fresh subprocess every turn, and neither WhatsApp
        adapter carries a quoted-message reference into the pipeline. So the link is the same one
        ``confirm_swap`` has always used to write on this data — ``(professor, date)`` resolved
        against the sheet, with the ambiguity checks that come with it — and it is a TOOL ARGUMENT,
        not a sentence: the date is a typed field, and a caller who has none has nothing to record.

        **Every refusal below leaves the class PENDING, which is a real answer.** A bare "yes",
        a date that matches nothing, a date that matches two years or two classes — all of them
        raise, so the invitation stays unanswered and somebody asks again. That is the whole
        design: this method has no branch that picks one of several classes, because the cost of
        guessing is a professor recorded as attending a class they never agreed to, and somebody
        turning up — or not — because of it.

        **It RAISES on every path that did not record**, the same contract
        :meth:`send_schedule_to_calendar` states and for the same reason: the MCP bridge stamps a
        successful call on a non-read-only tool as a WRITE, so a polite sentence about a refusal
        would enter the house's own commit accounting as a change that never happened.
        """
        state = parse_answer(answer)
        if not state:
            raise CoordinatorError(
                f"'{answer}' is not an answer this can record. Ask for one of: ACCEPTED or "
                f"DECLINED. Nothing was recorded.")
        if not class_date.strip():
            raise CoordinatorError(
                "An answer has to say WHICH class it is about — pass the class date (DD/MM or "
                "DD/MM/YYYY). Nothing was recorded, so the invitation is still open.")
        # A REPORT of our own when the caller brought none, exactly like ``confirm_swap``: the
        # refusal below has to fire whether or not somebody upstream wanted the read record, and
        # a check written as ``report is not None and report.errors`` is a guard that a caller
        # switches off by not asking for one.
        read = report if report is not None else ReadReport()
        entries = self.aggregate(include_free=False, report=read)
        if read.errors:
            unread = ", ".join(f"{e.sheet_key} ({e.message})" for e in read.errors)
            raise CoordinatorError(
                f"Cannot record an answer right now: {len(read.errors)} spreadsheet(s) could "
                f"not be read ({unread}) — the schedule is only partly loaded. Try again shortly.")
        vis, err = self._visible(entries, professor=professor, role=role,
                                 identity_label=identity_label)
        if err:
            raise CoordinatorAccessError(err)
        if turma.strip():
            keys = self.resolve_turmas(turma)
            if not keys:
                known = ", ".join(self.cfg.spreadsheets) or "none"
                raise CoordinatorError(
                    f"'{turma}' matches no class group here (configured: {known}). Nothing was "
                    f"recorded.")
            wanted = set(keys)
            vis = [e for e in vis if e.sheet_key in wanted]
        matches = [e for e in vis if _date_matches(e.when, e.date_str, class_date)]
        if not matches:
            raise CoordinatorError(
                f"No class found for that professor on {class_date}, so there is no invitation "
                f"to answer. Nothing was recorded.")
        if _ambiguous_year(matches, class_date):
            years = ", ".join(str(y) for y in sorted({e.when.year for e in matches if e.when}))
            raise CoordinatorError(
                f"'{class_date}' matches classes in more than one year ({years}) — ask for the "
                f"year. Nothing was recorded.")
        if len(matches) > 1:
            which = "; ".join(f"{e.sheet_key} — {e.subject}" for e in matches)
            raise CoordinatorError(
                f"{class_date} has more than one class for that professor ({which}) — ask which "
                f"class group. Nothing was recorded, so the invitation is still open.")
        entry = matches[0]
        idx = self.status_column_index(entry.header)
        if idx is None:
            raise CoordinatorConfigError(
                f"This institution's schedule has no column named '{self.cfg.column_status}', so "
                f"there is nowhere to record an answer. Add that header to the schedule tab (or "
                f"declare the existing one as COLUMN_STATUS in the rules). Nothing was recorded.")
        current = state_of(self._cell(entry.cells, idx),
                           accepted=self.cfg.status_accepted_label,
                           declined=self.cfg.status_declined_label,
                           ordinary=self.cfg.status_default_labels)
        if current is None:
            raise CoordinatorError(
                f"The status of the class on {entry.date_str} already says "
                f"'{self._cell(entry.cells, idx)}', which this assistant did not write and will "
                f"not overwrite. Nothing was recorded — report it as it stands.")
        if current == state:
            return entry, state, False
        self.store.write_cell(entry.sheet_id, self.cfg.tab_schedule, self.cfg.range_schedule,
                              entry.row_idx, idx,
                              label_for(state, accepted=self.cfg.status_accepted_label,
                                        declined=self.cfg.status_declined_label))
        return entry, state, True

    def class_response(self, entry: ClassEntry) -> Optional[str]:
        """What one class's status cell says as an RSVP state — ``PENDING`` when nothing is on
        file, ``None`` when the cell holds something this system did not write.

        The read half of :meth:`record_class_response`, and the reason there is no separate read
        TOOL: the listing already prints an answer on every line (``server._entry_status``), so a
        second surface for the same fact would be a second place for it to disagree. This exists
        for the callers that need the STATE rather than the word — the write path above, and the
        tests that pin the three of them."""
        idx = self.status_column_index(entry.header)
        if idx is None:
            return RSVP_PENDING
        return state_of(self._cell(entry.cells, idx),
                        accepted=self.cfg.status_accepted_label,
                        declined=self.cfg.status_declined_label,
                        ordinary=self.cfg.status_default_labels)


class CoordinatorError(Exception):
    """A domain error (not configured, not found, or an unreadable spreadsheet)."""


class CoordinatorConfigError(CoordinatorError):
    """The tenant's RULES are missing or malformed — nothing broke, nothing is deployed wrong.

    A subclass rather than a phrase in the message, because the caller has to tell it apart and
    the first cut of this did so with ``"has not configured" in str(exc)``. Matching a substring
    across two files is a contract nobody can see: reword the sentence and the wrapper silently
    starts reporting a tenant's unfilled form as a system ERROR — which the model then relays to
    a professor as "não consegui acessar". The type cannot drift from the sentence."""


class CoordinatorAccessError(CoordinatorError):
    """The caller asked for someone ELSE'S data and the role does not allow it.

    A subclass, not a message convention, because the two are told apart by a CALLER outside
    this module: the MCP wrapper renders a plain :class:`CoordinatorError` as a failure and this
    one as a LIMIT. Flattened together, the refusal reached the model reading ``ERROR: You can
    only view your own schedule.`` — and a model handed the word ERROR reports a breakdown, so a
    professor who asked about a colleague was told the assistant could not access the schedule.
    The rule held; only its NAME was wrong on the way out. Nothing here weakens the rule: a
    non-oversight caller is still refused, an oversight one still sees."""
