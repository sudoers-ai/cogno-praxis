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
