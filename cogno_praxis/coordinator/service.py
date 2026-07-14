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

import re
import unicodedata
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Callable, Optional

from cogno_praxis.coordinator.config import CoordinatorConfig
from cogno_praxis.coordinator.store import SpreadsheetStore
from cogno_praxis.coordinator.types import ClassEntry, ColumnLayout

_OVERSIGHT_ROLES = frozenset({"SUPERVISOR", "ADMIN", "OWNER"})
GRADE_GRACE_DAYS = 14           # parent parity: grades/attendance due within 14d of the last class
BRIEFING_HORIZON_DAYS = 7
REPLACEMENT_HORIZON_DAYS = 21
_DISCIPLINE_FUZZY_THRESHOLD = 0.75    # parent parity: per-token SequenceMatcher ratio floor

# PT-BR month name → number (a professor asks for "março", not "2026-03"). Parent parity.
_MONTH_NAMES: dict[str, int] = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "março": 3, "marco": 3, "mar": 3,
    "abril": 4, "abr": 4, "maio": 5, "mai": 5, "junho": 6, "jun": 6,
    "julho": 7, "jul": 7, "agosto": 8, "ago": 8, "setembro": 9, "set": 9,
    "outubro": 10, "out": 10, "novembro": 11, "nov": 11, "dezembro": 12, "dez": 12,
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
    named = _MONTH_NAMES.get(_norm(s))                    # "março" / "mar"
    return (named, 0) if named else None


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
        fixed_names = {_norm(n) for n in self.cfg.fixed_columns}
        fixed = {i for i, c in enumerate(h) if _norm(c) in fixed_names}
        content = [i for i in range(last + 1) if i not in fixed]
        return ColumnLayout(date_idx, prof_idx, subj_idx, last, fixed, content)

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
    def aggregate(self, *, include_skip: bool = False, include_free: bool = True) -> list[ClassEntry]:
        """Every schedule row across all configured spreadsheets, dates normalized, sorted
        chronologically (unparseable dates last). Skip-label rows dropped unless asked for."""
        out: list[ClassEntry] = []
        for key, sid in self.cfg.spreadsheets.items():
            rows = self.store.read_range(sid, self.cfg.tab_schedule, self.cfg.range_schedule)
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
    def get_professor_schedule(self, *, professor: str = "", role: str = "",
                               identity_label: str = "", month: str = "",
                               discipline: str = "") -> list[ClassEntry]:
        """A professor's (or, for oversight, anyone's) classes, optionally narrowed by ``month``
        (``'2026-03'``, ``'03'``, or a PT-BR name like ``'março'``) and/or ``discipline`` (fuzzy,
        typo-tolerant — 'machne learning' still matches 'Machine Learning')."""
        entries, err = self._visible(self.aggregate(), professor=professor, role=role,
                                     identity_label=identity_label)
        if err:
            raise CoordinatorError(err)
        mspec = _resolve_month(month)
        if mspec:
            mm, yy = mspec
            entries = [e for e in entries if e.when and e.when.month == mm
                       and (yy == 0 or e.when.year == yy)]
        if discipline.strip():
            entries = [e for e in entries if _fuzzy_match_discipline(discipline, e.subject)]
        return entries

    def check_deadlines(self, *, professor: str = "", role: str = "",
                        identity_label: str = "") -> list[ClassEntry]:
        """Disciplines whose LAST class already happened and are within the 14-day grace window
        (grades/attendance still due). Keyed by (sheet, professor, subject)."""
        entries, err = self._visible(self.aggregate(), professor=professor, role=role,
                                     identity_label=identity_label)
        if err:
            raise CoordinatorError(err)
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
                        identity_label: str = "") -> list[ClassEntry]:
        """Classes in the next 7 days (inclusive of today)."""
        entries, err = self._visible(self.aggregate(), professor=professor, role=role,
                                     identity_label=identity_label)
        if err:
            raise CoordinatorError(err)
        today = self._today()
        horizon = today + timedelta(days=BRIEFING_HORIZON_DAYS)
        return [e for e in entries if e.when and today <= e.when <= horizon]

    def find_replacement_slot(self, *, professor: str = "", role: str = "",
                              identity_label: str = "") -> list[ClassEntry]:
        """Free slots (FREE_SLOT_LABELS) within the next 21 days — candidates for a swap."""
        today = self._today()
        horizon = today + timedelta(days=REPLACEMENT_HORIZON_DAYS)
        # free slots are not professor-owned; oversight sees all, a professor sees the pool too
        return [e for e in self.aggregate(include_free=True)
                if e.is_free_slot and e.when and today <= e.when <= horizon]

    def ibope_status(self, *, professor: str = "", role: str = "",
                     identity_label: str = "") -> list[ClassEntry]:
        """LAST classes of a discipline that fall on TODAY — the mechanism behind the survey
        (IBOPE) reminder. The specific threshold/wording (e.g. '30% for the bonus') is the
        persona prompt's job; the vertical only identifies WHICH classes need the nudge."""
        entries, err = self._visible(self.aggregate(), professor=professor, role=role,
                                     identity_label=identity_label)
        if err:
            raise CoordinatorError(err)
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
                           identity_label: str = "") -> list[dict[str, str]]:
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
                raise CoordinatorError("You can only view your own faculty details.")
            target = identity_label
        want = _norm(target)
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for sid in self.cfg.spreadsheets.values():
            rows = self.store.read_range(sid, self.cfg.tab_professors, self.cfg.range_professors)
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

    # ── the one write ────────────────────────────────────────────────────────────────
    def confirm_swap(self, *, professor: str, original_date: str, new_date: str,
                     role: str = "", identity_label: str = "") -> tuple[ClassEntry, ClassEntry]:
        """Swap a professor's class (source, by date+professor) into a free slot (dest, by
        date+free-label): exchanges the CONTENT columns, leaving fixed columns (dates) put.
        Returns (source, dest) as they were located. Raises if either can't be found."""
        entries = self.aggregate(include_free=True)
        vis, err = self._visible(entries, professor=professor, role=role,
                                 identity_label=identity_label)
        if err:
            raise CoordinatorError(err)
        src = next((e for e in vis if _date_matches(e.when, e.date_str, original_date)), None)
        if src is None:
            raise CoordinatorError(f"No class found for that professor on {original_date}.")
        dst = next((e for e in entries if e.is_free_slot and e.sheet_id == src.sheet_id
                    and _date_matches(e.when, e.date_str, new_date)), None)
        if dst is None:
            raise CoordinatorError(f"No free slot found on {new_date} in the same schedule.")
        cols = self._resolve_columns(src.header)
        self.store.swap_rows(src.sheet_id, self.cfg.tab_schedule, self.cfg.range_schedule,
                             src.row_idx, dst.row_idx, content_cols=cols.content_indices)
        return src, dst


class CoordinatorError(Exception):
    """A domain error (not configured, not found, or a forbidden cross-professor request)."""
