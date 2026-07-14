"""``SpreadsheetStore`` — the coordinator vertical's I/O port (infra-agnostic).

The vertical owns the DOMAIN (aggregation, deadlines, swaps); the transport — how a spreadsheet
is actually read/written — is the host's job, injected as a ``SpreadsheetStore``. In production
the host adapter DOWNLOADS the file from Google Drive (via the Google API + the tenant's OAuth
token) and parses it locally (pandas/openpyxl), caching by TTL; tests use
:class:`InMemorySpreadsheetStore`. The domain never learns whether a read came from a live API,
a downloaded ``.xlsx``, or a fake — exactly like the scheduler's ``AppointmentStore``.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class SpreadsheetStore(Protocol):
    """Read (and, for swaps, write) a spreadsheet's cells as a 2-D string grid.

    A range is A1 notation (``"A4:E110"``); the return is rows of trimmed string cells, header
    row first. Coordinates are 0-based row indices INTO the returned grid (row 0 = header)."""

    def read_range(self, sheet_id: str, tab: str, a1_range: str) -> list[list[str]]: ...

    def swap_rows(self, sheet_id: str, tab: str, a1_range: str, row_a: int, row_b: int,
                  *, content_cols: list[int]) -> None:
        """Exchange the ``content_cols`` cells between two rows (fixed columns like dates stay).
        ``row_a``/``row_b`` are indices INTO the ``a1_range`` grid (0 = its header row), the same
        coordinate system ``read_range`` returns. Write path — the host adapter re-uploads or
        batch-updates; ``read_range``-only adapters may raise :class:`NotImplementedError`."""
        ...


class InMemorySpreadsheetStore:
    """A zero-infra ``SpreadsheetStore`` for tests/dev: an in-memory ``{(sheet_id, tab): grid}``.

    ``a1_range`` is honoured coarsely — the leading row of the range offsets into the grid so a
    ``A4:…`` schedule range skips the metadata rows exactly like the live sheet."""

    def __init__(self, sheets: Optional[dict[tuple[str, str], list[list[str]]]] = None) -> None:
        # key = (sheet_id, tab) → full grid (row 0 is the sheet's row 1)
        self._sheets: dict[tuple[str, str], list[list[str]]] = sheets or {}

    def put(self, sheet_id: str, tab: str, grid: list[list[str]]) -> None:
        self._sheets[(sheet_id, tab)] = [list(r) for r in grid]

    @staticmethod
    def _first_row(a1_range: str) -> int:
        """The 1-based starting row of an A1 range (``"A4:E110"`` → 4); default 1."""
        import re
        m = re.search(r"[A-Za-z]+(\d+)", a1_range or "")
        return int(m.group(1)) if m else 1

    def read_range(self, sheet_id: str, tab: str, a1_range: str) -> list[list[str]]:
        grid = self._sheets.get((sheet_id, tab), [])
        start = self._first_row(a1_range) - 1
        return [[str(c).strip() for c in row] for row in grid[start:]]

    def swap_rows(self, sheet_id: str, tab: str, a1_range: str, row_a: int, row_b: int,
                  *, content_cols: list[int]) -> None:
        grid = self._sheets.get((sheet_id, tab))
        off = self._first_row(a1_range) - 1                 # range-relative → absolute grid rows
        ga, gb = off + row_a, off + row_b
        if grid is None or ga >= len(grid) or gb >= len(grid):
            raise IndexError(f"swap_rows out of range: {row_a}/{row_b} in {sheet_id}/{tab}")
        for c in content_cols:
            if c < len(grid[ga]) and c < len(grid[gb]):
                grid[ga][c], grid[gb][c] = grid[gb][c], grid[ga][c]
