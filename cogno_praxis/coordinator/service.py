"""``CoordinatorService`` — the academic-schedule domain (infra-agnostic).

Ported from the parent's coordinator_assistant tools/reports, rebuilt on the new architecture:
the domain reads through a :class:`~cogno_praxis.coordinator.store.SpreadsheetStore` port (the
host injects a Google-download adapter; tests inject the in-memory fake) and is configured by a
:class:`~cogno_praxis.coordinator.config.CoordinatorConfig` parsed from the tenant's custom_rules.

Role handling (host-authorised, parent parity): a non-oversight caller only ever sees THEIR OWN
classes (``professor`` is pinned to their identity label); an oversight role (SUPERVISOR/ADMIN)
may query any professor or the whole master schedule.
"""

from __future__ import annotations

import calendar
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Callable, Optional

from cogno_praxis.coordinator.ics import (
    CalendarEvent,
    CalendarSender,
    build_ics_calendar,
    class_event_uid,
    parse_time,
    sequence_now,
)
from cogno_praxis.coordinator.config import CoordinatorConfig
from cogno_praxis.coordinator.pay import (
    PayEstimate,
    PayGroup,
    PayLine,
    parse_money,
)
from cogno_praxis.coordinator.rsvp import (
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
                out.append(entry)
        out.sort(key=lambda e: (e.when is None, e.when or date.max))
        return out

    # ── RBAC-aware professor filter ──────────────────────────────────────────────────
    def _visible(self, entries: list[ClassEntry], *, professor: str, role: str,
                 identity_label: str) -> tuple[list[ClassEntry], Optional[str]]:
        """Apply role scoping. Returns (filtered, error). A non-oversight caller is pinned to
        their own name; an oversight role may query any professor or all (professor='')."""
        oversight = role.upper() in _OVERSIGHT_ROLES
        target = professor.strip()
        if not oversight:
            if target and _norm(target) != _norm(identity_label):
                return [], "You can only view your own schedule."
            target = identity_label
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
                                     role=role, identity_label=identity_label)
        if err:
            raise CoordinatorAccessError(err)
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
                                     role=role, identity_label=identity_label)
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
                                     role=role, identity_label=identity_label)
        if err:
            raise CoordinatorAccessError(err)
        today = self._today()
        horizon = today + timedelta(days=BRIEFING_HORIZON_DAYS)
        return [e for e in entries if e.when and today <= e.when <= horizon]

    def find_replacement_slot(self, *, professor: str = "", role: str = "",
                              identity_label: str = "",
                              report: Optional[ReadReport] = None) -> list[ClassEntry]:
        """Free slots (FREE_SLOT_LABELS) within the next 21 days — candidates for a swap."""
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
                                     role=role, identity_label=identity_label)
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
    def _hours_by_subject(self, sheet_id: str, sheet_key: str,
                          report: Optional[ReadReport]) -> dict[str, float]:
        """``{normalised discipline: hours}`` from the tenant's declared hours column.

        The tab, the range and the column all come from the config. Nothing here looks for a
        header that "seems like" hours: only :attr:`CoordinatorConfig.column_hours`, matched the
        same way :meth:`_resolve_columns` matches the other three roles. A tenant who has not
        declared it never reaches this method — :meth:`estimate_professor_pay` refuses first.

        A row this cannot read is simply absent from the map, which downstream becomes "horas
        não declaradas" for that discipline. It never becomes a zero.
        """
        try:
            rows = self.store.read_range(sheet_id, self.cfg.tab_hours, self.cfg.range_hours)
        except Exception as exc:                       # noqa: BLE001 — the store is a PORT
            _log.warning("coordinator: hours tab of %r (%s) could not be read: %r",
                         sheet_key, sheet_id, exc)
            if report is not None:
                report.errors.append(_read_error(sheet_key, sheet_id, exc))
            return {}
        if not rows:
            return {}
        header = [c.strip().lower() for c in rows[0]]
        h_idx = next((i for i, c in enumerate(header)
                      if c == self.cfg.column_hours.strip().lower()), None)
        s_idx = next((i for i, c in enumerate(header)
                      if c == self.cfg.column_subject.strip().lower()), None)
        if h_idx is None or s_idx is None:
            _log.warning("coordinator: hours tab %r of %r has no %r/%r column — no hours read",
                         self.cfg.tab_hours, sheet_key, self.cfg.column_hours,
                         self.cfg.column_subject)
            return {}
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

    def _ibope_result(self, *, identity_label: str,
                      report: Optional[ReadReport]) -> Optional[float]:
        """The caller's own IBOPE percentage, or ``None`` — and ``None`` means NOT FOUND.

        ``None`` covers four different worlds on purpose, because they all license the same
        answer and none of them licenses a figure: the tenant declared no IBOPE tab, the tab was
        unreadable, no row names this professor, or SEVERAL rows do and disagree. That last one
        is the reason this returns rather than picks. Two results and a choice between them is
        an invented bonus wearing a real number, and the professor cannot tell which it was.
        """
        tab, col = self.cfg.tab_ibope.strip(), self.cfg.column_ibope.strip()
        if not tab or not col:
            return None
        found: set[float] = set()
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
            want = _norm(identity_label)
            for row in rows[1:]:
                if want and want not in _norm(self._cell(row, p_idx)):
                    continue
                pct = parse_money(self._cell(row, v_idx).rstrip("%"))
                if pct is not None:
                    found.add(pct)
        return found.pop() if len(found) == 1 else None

    def estimate_professor_pay(self, *, professor: str = "", role: str = "",
                               identity_label: str = "", period: str = "", turma: str = "",
                               report: Optional[ReadReport] = None) -> PayEstimate:
        """What the caller's OWN classes in ``period`` come to, grouped by class group and month.

        **Self-only, for every role, and that is the whole shape of this capability.** Every
        other read here scopes by role — a supervisor sees the master schedule — and this one
        does not: an oversight role gets exactly the same refusal a professor gets for asking
        about somebody else. The scope this tool opened is "a professor may ask what THEY earn",
        and a capability whose stated reason is *the money is yours* has no branch where the
        money is somebody else's. Passing ``professor`` with anyone but the caller's own name
        raises :class:`CoordinatorAccessError`; an unauthenticated caller (no
        ``identity_label``) raises too, because with nobody named "their own" has no referent.

        Refuses with :class:`CoordinatorError` when the tenant's rules do not declare the rate
        or the hours column, NAMING the keys — see :attr:`CoordinatorConfig.pay_undeclared`.
        There is no branch that estimates without them.

        The arithmetic is ``classes × hours-per-discipline × rate``, plus an IBOPE bonus when —
        and only when — a survey result was actually read. It is READ-ONLY: nothing here writes
        to a spreadsheet, sends anything, or records a figure.
        """
        me = identity_label.strip()
        if not me:
            raise CoordinatorAccessError(
                "This estimate is only ever about the person asking, and this turn carries no "
                "identified professor.")
        target = professor.strip()
        if target and _norm(target) != _norm(me):
            raise CoordinatorAccessError(
                "You can only see your own pay estimate — another professor's remuneration is "
                "not something this assistant discloses to anyone.")
        missing = self.cfg.pay_undeclared
        if missing:
            raise CoordinatorConfigError(
                f"This institution has not configured the pay figures: {', '.join(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} missing from the persona rules. "
                f"Nothing can be estimated without {'it' if len(missing) == 1 else 'them'}, "
                f"and nothing here will be assumed.")
        # A band the parser could not read REFUSES THE WHOLE ESTIMATE, and it names the entry.
        # Dropping it would be the worse of the two available wrongs: the professor is paid less
        # and the reply is word-for-word the one a tenant with no bonus scheme gets, so nobody —
        # not the professor, not whoever wrote the typo — has anything to notice.
        bad = self.cfg.ibope_bonus_unreadable
        if bad:
            named = "; ".join(repr(b) for b in bad)
            raise CoordinatorConfigError(
                f"IBOPE_BONUS in the persona rules has {len(bad)} band(s) this system cannot "
                f"read: {named}. A band is 'min-max=amount' or 'min+=amount', and bands are "
                f"separated by SEMICOLONS (a comma is a decimal separator). Nothing is estimated "
                f"until that line is fixed — a bonus band that is silently skipped pays less.")
        rate = self.cfg.pay_rate_per_hour
        assert rate is not None                        # pay_undeclared already refused a None

        # ``apply_horizon=False``, for the reason the calendar export already opts out: the
        # 30-day default exists so a professor READING a list does not have to scroll, and this
        # is not a list. An estimate silently cut at 30 days answers "quanto eu recebo" with
        # part of the months and no sign that it did — which is the export's "3 of 6" defect
        # said about money, where the reader has no way at all to notice the shortfall. A named
        # ``period`` still filters exactly as it does everywhere else.
        entries = self.get_professor_schedule(
            professor="", role=role, identity_label=me, month=period, turma=turma,
            apply_horizon=False, report=report)
        hours_by_sheet: dict[str, dict[str, float]] = {}
        # keyed by (class group, sortable year-month) so the two grouping axes the answer
        # promises are the two axes it is actually ordered by. Chronological order across the
        # whole read interleaves the groups, which reads as one list that keeps changing subject.
        buckets: dict[tuple[str, tuple[int, int]], dict[str, int]] = {}
        missing_hours: list[str] = []
        for e in entries:
            if e.is_free_slot or e.when is None or not e.subject.strip():
                continue
            if e.sheet_key not in hours_by_sheet:
                hours_by_sheet[e.sheet_key] = self._hours_by_subject(e.sheet_id, e.sheet_key,
                                                                     report)
            k = (e.sheet_key, (e.when.year, e.when.month))
            buckets.setdefault(k, {})
            buckets[k][e.subject.strip()] = buckets[k].get(e.subject.strip(), 0) + 1

        groups: list[PayGroup] = []
        for (turma_key, (year, month)) in sorted(buckets):
            lines: list[PayLine] = []
            for subject, count in buckets[(turma_key, (year, month))].items():
                hours = hours_by_sheet.get(turma_key, {}).get(_norm(subject))
                if hours is None and subject not in missing_hours:
                    missing_hours.append(subject)
                lines.append(PayLine(subject=subject, classes=count, hours_each=hours))
            groups.append(PayGroup(turma=turma_key, month=f"{month:02d}/{year}", lines=lines))

        pct = self._ibope_result(identity_label=me, report=report)
        return PayEstimate(
            rate=rate, groups=groups, hours_missing=tuple(missing_hours),
            tiers=self.cfg.ibope_bonus, ibope_found=pct is not None, ibope_pct=pct,
            ibope_tab=self.cfg.tab_ibope.strip(), period=month_label(period),
            ibope_min_response_pct=self.cfg.ibope_min_response_pct)

    def get_professor_info(self, *, professor: str = "", role: str = "",
                           identity_label: str = "",
                           report: Optional[ReadReport] = None) -> list[dict[str, str]]:
        """Faculty details from the professors tab (``TAB_PROFESSORS``/``RANGE_PROFESSORS`` — e.g.
        Disciplina, CH, Professor, e-mail, titulação), one dict per row keyed by lowercased header.
        RBAC parity with the schedule: a non-oversight caller only sees THEIR OWN row (pinned to
        their identity label); oversight sees everyone. Returns ``[]`` when no professors tab is
        configured. The specific columns are tenant-defined; the vertical stays column-agnostic."""
        if not self.cfg.tab_professors:
            return []
        oversight = role.upper() in _OVERSIGHT_ROLES
        target = professor.strip()
        if not oversight:
            if target and _norm(target) != _norm(identity_label):
                raise CoordinatorAccessError("You can only view your own faculty details.")
            target = identity_label
        want = _norm(target)
        out: list[dict[str, str]] = []
        seen: set[str] = set()
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
                if want and want not in _norm(name):
                    continue
                dedup = _norm(name)
                if dedup in seen:
                    continue
                seen.add(dedup)
                out.append(rec)
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
