"""Google-download ``SpreadsheetStore`` adapter (Drive API + openpyxl).

The read path is DOWNLOAD-centric (the design decision): instead of per-cell Sheets API queries,
it downloads the whole file once (Drive ``files.export`` → xlsx for a native Google Sheet, or
``files.get?alt=media`` for an uploaded ``.xlsx``), parses it locally with openpyxl, and caches
the parsed workbook by ``sheet_id`` with a TTL. Auth is the tenant's OAuth access token (the host
mints/refreshes it and passes it in; the scheduler's DSN analogue). Writes (``swap_rows``,
``write_cell``) go back surgically via the Sheets ``values.batchUpdate`` API so formatting/other
tabs are untouched.

A ``swap_rows`` moves the row CONTENTS through ``values.batchUpdate`` (RAW), which carries no
formatting, and THEN moves the per-cell formatting after it, through the Sheets ``batchUpdate``
of ``updateCells`` requests. The two paths are independent on purpose: the values are the proven
write and go first unchanged, and the formatting is a best-effort follow-up — if it fails the
contents are already swapped (today's behaviour, never worse) and the adapter logs and returns.

``pip install cogno-praxis[coordinator]`` (openpyxl + httpx). The four HTTP seams — ``_fetch``
and ``_push_values`` (download / values) plus ``_read_formats`` and ``_push_requests`` (the
formatting pair) — are the only network methods, so unit tests mock them and exercise the parse
/ cache / range / swap-request logic with zero network.
"""

from __future__ import annotations

import io
import logging
import time
from typing import Callable, Optional

import httpx

_log = logging.getLogger(__name__)

_DRIVE = "https://www.googleapis.com/drive/v3/files"
_SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_FORMAT_FIELDS = "sheets(properties(sheetId,title),data(rowData(values(userEnteredFormat))))"
_DEFAULT_TTL = 600.0                 # 10 min, parent parity


class GoogleSheetsStore:
    """A :class:`~cogno_praxis.coordinator.store.SpreadsheetStore` backed by Google Drive.

    Bound to one tenant's OAuth token at construction (single-tenant-per-instance, like the
    scheduler's Pg adapter). ``now`` is injectable for deterministic cache-TTL tests."""

    def __init__(self, access_token: str, *, ttl_seconds: float = _DEFAULT_TTL,
                 timeout: float = 30.0, now: Optional[Callable[[], float]] = None) -> None:
        self._token = access_token
        self._ttl = ttl_seconds
        self._timeout = timeout
        self._now: Callable[[], float] = now or time.monotonic
        # sheet_id → (fetched_at, {tab_lower: grid})
        self._cache: dict[str, tuple[float, dict[str, list[list[str]]]]] = {}

    # ── network seams (mocked in unit tests) ─────────────────────────────────────────
    def _fetch(self, sheet_id: str) -> bytes:
        """Download the spreadsheet as xlsx bytes. Try export (native Google Sheet); on 403
        failedPrecondition (an uploaded .xlsx can't be exported) fall back to raw media."""
        headers = {"Authorization": f"Bearer {self._token}"}
        with httpx.Client(timeout=self._timeout) as c:
            r = c.get(f"{_DRIVE}/{sheet_id}/export", params={"mimeType": _XLSX_MIME},
                      headers=headers)
            if r.status_code == 403:
                r = c.get(f"{_DRIVE}/{sheet_id}", params={"alt": "media"}, headers=headers)
            r.raise_for_status()
            return r.content

    def _push_values(self, sheet_id: str, data: list[dict]) -> None:
        """Sheets values.batchUpdate — ``data`` = ``[{"range": "Tab!A2:C2", "values": [[...]]}]``."""
        headers = {"Authorization": f"Bearer {self._token}"}
        body = {"valueInputOption": "RAW", "data": data}
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(f"{_SHEETS}/{sheet_id}/values:batchUpdate", headers=headers, json=body)
            r.raise_for_status()

    def _read_formats(self, sheet_id: str, tab: str,
                      abs_rows: list[int]) -> tuple[int, dict[int, dict[int, object]]]:
        """Read the ``userEnteredFormat`` of the cells in ``abs_rows`` (0-based sheet rows) of
        ``tab``, and the tab's numeric ``sheetId``.

        Returns ``(sheet_id_num, {abs_row: {col: userEnteredFormat}})`` — only the cells that
        carry a format appear, so a cell without one is simply absent. ``spreadsheets.get`` with
        ``ranges`` restricted to those rows and ``fields`` to the format subtree keeps the payload
        small; the same call hands back the tab's ``sheetId`` (needed for the ``updateCells``
        ``GridRange``)."""
        headers = {"Authorization": f"Bearer {self._token}"}
        pairs = tuple(("ranges", f"'{tab}'!{r + 1}:{r + 1}") for r in abs_rows) \
            + (("fields", _FORMAT_FIELDS),)
        with httpx.Client(timeout=self._timeout) as c:
            r = c.get(f"{_SHEETS}/{sheet_id}", params=pairs, headers=headers)
            r.raise_for_status()
            payload = r.json()
        want = tab.strip().lower()
        sheet = next((s for s in payload.get("sheets", [])
                      if str(s.get("properties", {}).get("title", "")).strip().lower() == want),
                     payload.get("sheets", [{}])[0] if payload.get("sheets") else {})
        grid_id = int(sheet.get("properties", {}).get("sheetId", 0))
        out: dict[int, dict[int, object]] = {}
        for abs_row, data in zip(abs_rows, _first_data_rows(sheet)):
            cells: dict[int, object] = {}
            for col, value in enumerate(data):
                fmt = value.get("userEnteredFormat") if isinstance(value, dict) else None
                if fmt is not None:
                    cells[col] = fmt
            out[abs_row] = cells
        return grid_id, out

    def _push_requests(self, sheet_id: str, requests: list[dict]) -> None:
        """Sheets ``spreadsheets.batchUpdate`` — ``requests`` is the list of request objects
        (here ``updateCells``), the formatting path's write."""
        headers = {"Authorization": f"Bearer {self._token}"}
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(f"{_SHEETS}/{sheet_id}:batchUpdate", headers=headers,
                       json={"requests": requests})
            r.raise_for_status()

    # ── parse + cache ────────────────────────────────────────────────────────────────
    @staticmethod
    def _parse(xlsx: bytes) -> dict[str, list[list[str]]]:
        """xlsx bytes → ``{tab_lower: [[cell,…],…]}`` (all cells stringified, None→'')."""
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True)
        out: dict[str, list[list[str]]] = {}
        for ws in wb.worksheets:
            grid: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                grid.append(["" if v is None else str(v).strip() for v in row])
            out[ws.title.strip().lower()] = grid
        wb.close()
        return out

    def _tabs(self, sheet_id: str) -> dict[str, list[list[str]]]:
        hit = self._cache.get(sheet_id)
        if hit and (self._now() - hit[0]) < self._ttl:
            return hit[1]
        tabs = self._parse(self._fetch(sheet_id))
        self._cache[sheet_id] = (self._now(), tabs)
        return tabs

    @staticmethod
    def _first_row(a1_range: str) -> int:
        import re
        m = re.search(r"[A-Za-z]+(\d+)", a1_range or "")
        return int(m.group(1)) if m else 1

    # ── the port ─────────────────────────────────────────────────────────────────────
    def read_range(self, sheet_id: str, tab: str, a1_range: str) -> list[list[str]]:
        grid = self._tabs(sheet_id).get(tab.strip().lower(), [])
        start = self._first_row(a1_range) - 1
        return [list(r) for r in grid[start:]]

    def write_cell(self, sheet_id: str, tab: str, a1_range: str, row: int, col: int,
                   value: str) -> None:
        """Set one range-relative cell, then drop this sheet's cache so the next read sees it.

        The bounds check is against the CACHED grid and the write is not: a Sheets cell exists
        whether or not the downloaded copy reached it, and this refuses rather than creating one
        — the row/column a caller could not have read is the row/column it cannot have meant."""
        grid = self._tabs(sheet_id).get(tab.strip().lower(), [])
        abs_row = self._first_row(a1_range) - 1 + row
        if abs_row >= len(grid) or col >= len(grid[abs_row]):
            raise IndexError(f"write_cell out of range: {row}/{col} in {sheet_id}/{tab}")
        a1 = f"{_col_letter(col)}{abs_row + 1}"             # Sheets rows/cols are 1-based
        self._push_values(sheet_id, [{"range": f"'{tab}'!{a1}", "values": [[value]]}])
        self._cache.pop(sheet_id, None)                     # force a fresh read next time

    def swap_rows(self, sheet_id: str, tab: str, a1_range: str, row_a: int, row_b: int,
                  *, content_cols: list[int]) -> None:
        """Swap the ``content_cols`` between two range-relative rows: first the VALUES, then the
        per-cell FORMATTING, both back via the Sheets API (dates/fixed columns stay put).
        Invalidates the cache for this sheet.

        (a) The values go through ``values.batchUpdate`` (RAW) exactly as before — the proven
        path does not move. (b) Then the ``userEnteredFormat`` of each swapped cell follows
        through ``spreadsheets.batchUpdate``: one ``updateCells`` per row per contiguous run of
        ``content_cols``, A's format written into B's cell and B's into A's, ``fields`` restricted
        to ``userEnteredFormat`` so the fixed columns are untouched. ``values.batchUpdate`` is RAW
        and carries no formatting, which is why (b) exists at all.

        If (b) fails, the CONTENTS are already swapped — today's state, never worse — and the
        adapter logs one closed line and returns without raising, so the caller reports the swap
        as it does today.

        Out of scope (and deliberately so): :meth:`write_cell` writes one VALUE and no format;
        conditional formatting and data validation are RANGE rules that follow a row's POSITION,
        not its contents, so a value swap already leaves them where they belong."""
        grid = self._tabs(sheet_id).get(tab.strip().lower(), [])
        off = self._first_row(a1_range) - 1
        abs_a, abs_b = off + row_a, off + row_b            # 0-based absolute rows in the sheet
        if abs_a >= len(grid) or abs_b >= len(grid):
            raise IndexError(f"swap_rows out of range: {row_a}/{row_b} in {sheet_id}/{tab}")
        row_a_vals, row_b_vals = list(grid[abs_a]), list(grid[abs_b])
        updates: list[dict] = []
        cols: list[int] = []
        for c in content_cols:
            if c < len(row_a_vals) and c < len(row_b_vals):
                cols.append(c)
                a1_a = f"{_col_letter(c)}{abs_a + 1}"       # Sheets rows/cols are 1-based
                a1_b = f"{_col_letter(c)}{abs_b + 1}"
                updates.append({"range": f"'{tab}'!{a1_a}", "values": [[row_b_vals[c]]]})
                updates.append({"range": f"'{tab}'!{a1_b}", "values": [[row_a_vals[c]]]})
        if not updates:
            return
        self._push_values(sheet_id, updates)               # (a) values — the proven path
        self._cache.pop(sheet_id, None)                    # force a fresh read next time
        try:                                               # (b) formatting — best effort
            grid_id, fmts = self._read_formats(sheet_id, tab, [abs_a, abs_b])
            requests = _format_swap_requests(grid_id, abs_a, abs_b,
                                             fmts.get(abs_a, {}), fmts.get(abs_b, {}), cols)
            if requests:
                self._push_requests(sheet_id, requests)
        except Exception:
            # The contents are swapped; the formatting is not. Never raise over it — the swap is
            # reported as before. No cell text in the line: a closed event is all it carries.
            _log.warning("stage=coordinator event=sheet_format_swap_failed — the row values "
                         "swapped and the cell formatting did not")


def _first_data_rows(sheet: dict) -> list[list[dict]]:
    """For each requested range (in order), the cells of its single ``rowData`` row — ``[]`` for
    a range the API returned empty. The ``spreadsheets.get`` of :meth:`_read_formats` asks for one
    row per range, so each ``GridData`` here holds at most one ``rowData``."""
    out: list[list[dict]] = []
    for grid_data in sheet.get("data", []):
        rows = grid_data.get("rowData", [])
        out.append(rows[0].get("values", []) if rows else [])
    return out


def _contiguous_runs(cols: list[int]) -> list[list[int]]:
    """``[2, 3, 4, 7]`` → ``[[2, 3, 4], [7]]`` — consecutive columns grouped so each becomes one
    ``GridRange``. ``cols`` is already in ``content_cols`` order and the runs follow it."""
    runs: list[list[int]] = []
    for c in cols:
        if runs and c == runs[-1][-1] + 1:
            runs[-1].append(c)
        else:
            runs.append([c])
    return runs


def _format_swap_requests(grid_id: int, abs_a: int, abs_b: int,
                          fmt_a: dict[int, object], fmt_b: dict[int, object],
                          cols: list[int]) -> list[dict]:
    """The ``updateCells`` requests that put row A's formats onto row B and B's onto A, for the
    ``cols`` only: one request per row per contiguous run. ``fmt_a``/``fmt_b`` map col →
    ``userEnteredFormat``; a col missing from a side swaps in an EMPTY format (``{}``), which
    clears the target — absence travels with the cell exactly as a value would. ``fields`` is
    pinned to ``userEnteredFormat`` so the fixed (date) columns are never touched."""
    out: list[dict] = []
    for abs_row, src in ((abs_a, fmt_b), (abs_b, fmt_a)):     # A's cell gets B's format, and back
        for run in _contiguous_runs(cols):
            values = [{"userEnteredFormat": src.get(c, {})} for c in run]
            out.append({"updateCells": {
                "range": {"sheetId": grid_id,
                          "startRowIndex": abs_row, "endRowIndex": abs_row + 1,
                          "startColumnIndex": run[0], "endColumnIndex": run[-1] + 1},
                "rows": [{"values": values}],
                "fields": "userEnteredFormat"}})
    return out


def _col_letter(idx0: int) -> str:
    """0-based column index → spreadsheet letter (0→A, 25→Z, 26→AA)."""
    s = ""
    n = idx0 + 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s
