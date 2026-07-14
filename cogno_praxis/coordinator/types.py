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
