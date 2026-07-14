"""GoogleSheetsStore integration — against a REAL Google spreadsheet.

Gated (auto-skips) unless you provide a live OAuth access token + a readable sheet:
  COGNO_TEST_GOOGLE_TOKEN    — a Google OAuth access token with Drive/Sheets read scope
  COGNO_TEST_SHEET_ID        — the file id of a Google Sheet (or uploaded .xlsx) to read
  COGNO_TEST_SHEET_TAB       — the tab/worksheet name (default "Sheet1")
  COGNO_TEST_SHEET_RANGE     — an A1 range whose first row is a header (default "A1:Z50")

Read-only: this never writes. It proves the download → parse → range path end to end.
"""

from __future__ import annotations

import os

import pytest

TOKEN = os.environ.get("COGNO_TEST_GOOGLE_TOKEN")
SHEET = os.environ.get("COGNO_TEST_SHEET_ID")
pytestmark = pytest.mark.skipif(
    not (TOKEN and SHEET),
    reason="set COGNO_TEST_GOOGLE_TOKEN + COGNO_TEST_SHEET_ID to run")


def test_download_parse_read_range_live():
    from cogno_praxis.coordinator.stores.google_sheets import GoogleSheetsStore

    tab = os.environ.get("COGNO_TEST_SHEET_TAB", "Sheet1")
    rng = os.environ.get("COGNO_TEST_SHEET_RANGE", "A1:Z50")
    store = GoogleSheetsStore(TOKEN)

    rows = store.read_range(SHEET, tab, rng)
    assert rows, "expected at least a header row from the live sheet"
    assert all(isinstance(r, list) for r in rows)
    assert all(isinstance(c, str) for r in rows for c in r)   # every cell stringified

    # the second read is served from cache — no exception, same shape
    again = store.read_range(SHEET, tab, rng)
    assert len(again) == len(rows)
