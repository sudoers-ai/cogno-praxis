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
from cogno_praxis.coordinator.store import SpreadsheetStore
from cogno_praxis.coordinator.types import ClassEntry, ColumnLayout, ReadReport, SheetReadError

_log = logging.getLogger(__name__)

_OVERSIGHT_ROLES = frozenset({"SUPERVISOR", "ADMIN", "OWNER"})
GRADE_GRACE_DAYS = 14           # parent parity: grades/attendance due within 14d of the last class
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
            return int(s[5:7]), int(s[:4])
        except ValueError:
            return None
    if s.isdigit():                                       # "3" / "03"
        m = int(s)
        return (m, 0) if 1 <= m <= 12 else None
    named = _MONTH_NAMES.get(_norm(s))                    # "março" / "mar" / "September"
    return (named, 0) if named else None


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


class CoordinatorService:
    def __init__(self, store: SpreadsheetStore, config: CoordinatorConfig,
                 *, today: Optional[Callable[[], date]] = None) -> None:
        self.store = store
        self.cfg = config
        self._today: Callable[[], date] = today or (lambda: datetime.now().date())

    # ── layout + row helpers ─────────────────────────────────────────────────────────
    def _resolve_columns(self, header: list[str]) -> ColumnLayout:
        h = [c.strip().lower() for c in header]
        date_idx = next((i for i, c in enumerate(h) if c == self.cfg.column_date.lower()), 0)
        prof_idx = next((i for i, c in enumerate(h) if c == self.cfg.column_professor.lower()), None)
        subj_idx = next((i for i, c in enumerate(h) if c == self.cfg.column_subject.lower()), None)
        last = max((i for i, c in enumerate(header) if c.strip()), default=len(header) - 1)
        time_idx = next((i for i, c in enumerate(h) if c == self.cfg.column_time.lower()), None)
        fixed_names = {_norm(n) for n in self.cfg.fixed_columns}
        fixed = {i for i, c in enumerate(h) if _norm(c) in fixed_names}
        content = [i for i in range(last + 1) if i not in fixed]
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
                               include_past: bool = False,
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

        **The window is ``[today, ∞)`` by default.** A schedule spreadsheet holds the whole
        academic year, and the question a professor asks is almost always about what is COMING:
        returning the year and leaving the model to choose is how an April opening workshop got
        read back on a conversation held in September. Past classes come back only when the
        caller asks — ``include_past=True``, or by naming a month that has already ENDED, which
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
        entries = self.get_professor_schedule(
            professor=professor, role=role, identity_label=identity_label, month=month,
            turma=turma, report=report)
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
        org_email, org_name = sender.organizer()
        ics = build_ics_calendar(
            events, organizer_email=org_email, organizer_name=org_name, attendee=recipient,
            tz_name=tz_name, sequence=sequence_now() if sequence is None else sequence,
            duration_minutes=self.cfg.class_duration_minutes)
        body = (f"{len(events)} aula(s) em anexo, no formato de calendário (.ics). "
                f"Abra o anexo para importar tudo de uma vez.")
        ok = await sender.send(to=recipient, subject=subject_line or "Suas aulas",
                               body=body, ics=ics)
        if not ok:
            raise CoordinatorError(
                "The e-mail server did NOT accept the message, so the calendar was not "
                "delivered. Nothing was sent — say exactly that and try again later.")
        return len(events), recipient, dropped

    # ── the spreadsheet write ────────────────────────────────────────────────────────
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
            raise CoordinatorError(f"No free slot found on {new_date} in the same schedule.")
        if _ambiguous_year(dst_matches, new_date):
            raise CoordinatorError(
                f"'{new_date}' matches free slots in more than one year — please include the year.")
        dst = dst_matches[0]
        cols = self._resolve_columns(src.header)
        self.store.swap_rows(src.sheet_id, self.cfg.tab_schedule, self.cfg.range_schedule,
                             src.row_idx, dst.row_idx, content_cols=cols.content_indices)
        return src, dst


class CoordinatorError(Exception):
    """A domain error (not configured, not found, or an unreadable spreadsheet)."""


class CoordinatorAccessError(CoordinatorError):
    """The caller asked for someone ELSE'S data and the role does not allow it.

    A subclass, not a message convention, because the two are told apart by a CALLER outside
    this module: the MCP wrapper renders a plain :class:`CoordinatorError` as a failure and this
    one as a LIMIT. Flattened together, the refusal reached the model reading ``ERROR: You can
    only view your own schedule.`` — and a model handed the word ERROR reports a breakdown, so a
    professor who asked about a colleague was told the assistant could not access the schedule.
    The rule held; only its NAME was wrong on the way out. Nothing here weakens the rule: a
    non-oversight caller is still refused, an oversight one still sees."""
