"""Coordinator domain types — a resolved class entry and the column layout of a sheet."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class ColumnLayout:
    """Where each system role sits in a sheet's header, resolved from the config's COLUMN_* names.

    ``professor_idx``/``subject_idx`` are ``None`` when the header has no such column (the sheet
    is then treated as role-less: no RBAC filtering, no free/skip detection)."""
    date_idx: int
    professor_idx: Optional[int]
    subject_idx: Optional[int]
    last_col_idx: int
    fixed_indices: set[int] = field(default_factory=set)
    content_indices: list[int] = field(default_factory=list)
    #: Where the HOUR sits, when the sheet has such a column at all. ``None`` is the common
    #: case and is not a defect: a schedule spreadsheet records a DAY, and the calendar export
    #: renders an all-day event for it. Last, with a default, so nothing that builds a layout
    #: positionally has to change.
    time_idx: Optional[int] = None


@dataclass
class ClassEntry:
    """One aggregated schedule row across all spreadsheets, dates normalized.

    ``cells`` is the full row (for verbatim display + swaps); ``sheet_id``/``row_idx`` locate it
    for a write. ``when`` is the parsed date (None if unparseable — kept but sorted last).

    ``sheet_key`` is the tenant's own label for the spreadsheet ("Turma DSA_33"), which in this
    vertical IS the CLASS GROUP: one spreadsheet per turma. It has been on every entry since the
    vertical shipped and reached a human only inside an error message ("Turma DSA_33: HTTP 404"),
    so a professor teaching four groups got four indistinguishable lists of dates and could not
    tell which class belonged to which group. It is carried, not derived: the display and the
    ``turma`` filter both read THIS field, never a name parsed back out of the row."""
    sheet_id: str
    sheet_key: str
    row_idx: int                 # 0-based index into the sheet's schedule range (row 0 = header)
    when: Optional[date]
    date_str: str                # normalized DD/MM/YYYY for display
    professor: str
    subject: str
    cells: list[str]
    header: list[str]

    @property
    def is_free_slot(self) -> bool:
        return getattr(self, "_free", False)


@dataclass
class SheetReadError:
    """ONE spreadsheet that could not be read, named so the reply can say which.

    The point is the SCOPE: a tenant configures several spreadsheets, and one of them being
    unreachable (a stale id, a revoked share, a 404) used to abort the whole aggregation — the
    professor was told the assistant could not access the schedule while three other course
    spreadsheets were perfectly readable. ``message`` is deliberately terse (``"HTTP 404"``,
    ``"TimeoutException"``): it reaches the model, and from there the contact."""
    sheet_key: str               # the tenant's own label ("Turma DSA_33") — what a human recognises
    sheet_id: str
    message: str


@dataclass
class ReadReport:
    """Out-parameter for the read tools: what a read could NOT do, and what it HID.

    An out-param rather than a wider return type or a field on the service: the service is built
    once per turn but its methods are called independently, so per-call state on ``self`` would
    be a cross-call leak waiting to happen, while a new return type would churn every caller and
    test for a value most of them do not want. Callers that do not care pass nothing and get
    exactly today's behaviour."""
    errors: list[SheetReadError] = field(default_factory=list)
    hidden_past: int = 0         # classes dropped by the "today onward" default (0 = nothing cut)
    #: Did the DEFAULT FORWARD HORIZON cut anything? A BIT, never a count, and the asymmetry
    #: with ``hidden_past`` above it is deliberate — both are windows, both are defaults, and
    #: neither is an incompleteness. ``errors`` is the only field here that measures, because
    #: only there is the answer really partial. See ``server._fmt_report`` for the price a
    #: COUNT was measured to carry: the judge reads a quantified outside as the execution
    #: admitting unfinished work, and spends the turn's correction budget on it.
    beyond_horizon: bool = False
    unmatched_turma: str = ""    # a `turma` filter that matched NO configured class group
    known_turmas: tuple[str, ...] = ()   # the configured group names, so the reply can name them


@dataclass(frozen=True)
class DeadlineDue:
    """One discipline inside the grade/attendance grace window, and HOW LONG is left of it.

    ``days_left`` is what the entry alone cannot say: the window closes ``GRADE_GRACE_DAYS``
    after the discipline's LAST class, so ``0`` means it closes TODAY and ``13`` means the last
    class was yesterday. It is derived here rather than by a reader because a reader that
    re-derives it needs the grace constant, and a second copy of a constant is a second place
    for it to be wrong.

    **The range is ``0..GRADE_GRACE_DAYS - 1`` and never negative, and that is not an accident
    of arithmetic — it is the shape of what the source can see.**
    :meth:`~cogno_praxis.coordinator.service.CoordinatorService.check_deadlines` keeps only
    ``last_class < today <= last_class + GRADE_GRACE_DAYS``, so a deadline that has genuinely
    EXPIRED is filtered out before it ever reaches here. There is no ``days_left < 0``, because
    there is no overdue set to put in one.
    """

    entry: ClassEntry
    days_left: int               # 0 = the grace window closes TODAY


@dataclass(frozen=True)
class DailyChecks:
    """Everything one professor's day holds, read in ONE call — the composition, not a new read.

    Three questions a professor otherwise asks one tool at a time, answered together because
    they are one question ("o que tenho hoje?"). Each field comes from the predicate that
    already owned it — today's classes from the weekly briefing, the deadlines from
    ``check_deadlines``, the survey trigger from ``ibope_status`` — so nothing here re-defines
    what "due" or "last class" means, and a fix to any of those three lands here for free.

    **What is NOT here is the confirmation state**, and it is absent on purpose rather than
    forgotten. The tenant's schedule tab carries an approval column ("Confirmado" /
    "Proposta enviada"), but its HEADER CELL IS BLANK — measured on the live corpus 2026-09-07
    and pinned by ``tests/unit/test_a_swap_does_not_drop_what_it_cannot_name.py`` — and every
    reader in this vertical resolves a column BY NAME. Reading it by POSITION instead would be
    guessing at a STATE field: insert one column in the sheet and the reader starts reporting
    the wrong approval, silently. Carrying a cell you cannot name is safe (that is what #114
    does, and why it is deliberately name-agnostic); INTERPRETING one is not. The block lands
    the day somebody writes those headers in, and needs no code.

    ``empty`` is the whole reason this is a value and not three lists: a day with nothing in it
    must be SAID, once, and never rendered as three empty blocks.
    """

    classes_today: list[ClassEntry] = field(default_factory=list)
    deadlines: list[DeadlineDue] = field(default_factory=list)
    ibope_today: list[ClassEntry] = field(default_factory=list)

    @property
    def due_today(self) -> list[DeadlineDue]:
        """Deadlines whose grace window closes TODAY — the ones that cannot wait a day."""
        return [d for d in self.deadlines if d.days_left == 0]

    @property
    def due_ahead(self) -> list[DeadlineDue]:
        """Deadlines still inside the window with days to spare."""
        return [d for d in self.deadlines if d.days_left > 0]

    @property
    def empty(self) -> bool:
        """Nothing at all today — a real answer, and the one a caller must SAY rather than
        render as three empty sections."""
        return not (self.classes_today or self.deadlines or self.ibope_today)
