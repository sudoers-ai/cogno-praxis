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

import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional

from cogno_praxis.coordinator.config import CoordinatorConfig
from cogno_praxis.coordinator.store import SpreadsheetStore
from cogno_praxis.coordinator.types import ClassEntry, ColumnLayout

_OVERSIGHT_ROLES = frozenset({"SUPERVISOR", "ADMIN", "OWNER"})
GRADE_GRACE_DAYS = 14           # parent parity: grades/attendance due within 14d of the last class
BRIEFING_HORIZON_DAYS = 7
REPLACEMENT_HORIZON_DAYS = 21


def _norm(text: str) -> str:
    """Accent-stripped, lowercased — for label/name comparison ('Ciência'→'ciencia')."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


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


class CoordinatorService:
    def __init__(self, store: SpreadsheetStore, config: CoordinatorConfig,
                 *, today: Optional[object] = None) -> None:
        self.store = store
        self.cfg = config
        self._today = today or (lambda: datetime.now().date())

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
                               identity_label: str = "", month: str = "") -> list[ClassEntry]:
        entries, err = self._visible(self.aggregate(), professor=professor, role=role,
                                     identity_label=identity_label)
        if err:
            raise CoordinatorError(err)
        if month:
            entries = [e for e in entries if e.when and e.when.strftime("%Y-%m") == month]
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
        src = next((e for e in vis if e.date_str == original_date.strip()
                    or (e.when and e.when.strftime("%d/%m/%Y") == original_date.strip())), None)
        if src is None:
            raise CoordinatorError(f"No class found for that professor on {original_date}.")
        dst = next((e for e in entries if e.is_free_slot and e.sheet_id == src.sheet_id
                    and (e.date_str == new_date.strip()
                         or (e.when and e.when.strftime("%d/%m/%Y") == new_date.strip()))), None)
        if dst is None:
            raise CoordinatorError(f"No free slot found on {new_date} in the same schedule.")
        cols = self._resolve_columns(src.header)
        self.store.swap_rows(src.sheet_id, self.cfg.tab_schedule, self.cfg.range_schedule,
                             src.row_idx, dst.row_idx, content_cols=cols.content_indices)
        return src, dst


class CoordinatorError(Exception):
    """A domain error (not configured, not found, or a forbidden cross-professor request)."""
