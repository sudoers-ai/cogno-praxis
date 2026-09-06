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


@dataclass
class ClassEntry:
    """One aggregated schedule row across all spreadsheets, dates normalized.

    ``cells`` is the full row (for verbatim display + swaps); ``sheet_id``/``row_idx`` locate it
    for a write. ``when`` is the parsed date (None if unparseable — kept but sorted last)."""
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
