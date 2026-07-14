"""GoogleSheetsStore adapter — parse/cache/range/swap logic with the HTTP seams mocked.

No network: ``_fetch`` (download) and ``_push_values`` (write) are the only network methods and
are patched. The parse test builds a real ``.xlsx`` with openpyxl (skipped if it's absent)."""

from __future__ import annotations

import io

import pytest

openpyxl = pytest.importorskip("openpyxl")

from cogno_praxis.coordinator.stores.google_sheets import (  # noqa: E402
    GoogleSheetsStore, _col_letter)


def _xlsx(tab: str, rows: list[list[str]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tab
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_col_letter():
    assert [_col_letter(i) for i in (0, 1, 25, 26, 27)] == ["A", "B", "Z", "AA", "AB"]


def test_parse_and_read_range_downloads_once(monkeypatch):
    xlsx = _xlsx("Secretaria", [
        ["meta"], [""], [""],
        ["Data", "Professor", "Disciplina"],
        ["13/07/2026", "Ana", "Redes"],
    ])
    calls = {"n": 0}

    def fake_fetch(self, sheet_id):
        calls["n"] += 1
        return xlsx

    monkeypatch.setattr(GoogleSheetsStore, "_fetch", fake_fetch)
    store = GoogleSheetsStore("tok")
    got = store.read_range("SID", "Secretaria", "A4:C10")     # skips the 3 metadata rows
    assert got[0] == ["Data", "Professor", "Disciplina"]
    assert got[1] == ["13/07/2026", "Ana", "Redes"]
    # a second read of the same sheet is served from cache → still one download
    store.read_range("SID", "Secretaria", "A4:C10")
    assert calls["n"] == 1


def test_cache_ttl_expiry_refetches(monkeypatch):
    clock = {"t": 0.0}
    calls = {"n": 0}

    def fake_fetch(self, sheet_id):
        calls["n"] += 1
        return _xlsx("Secretaria", [["Data"], ["13/07/2026"]])

    monkeypatch.setattr(GoogleSheetsStore, "_fetch", fake_fetch)
    store = GoogleSheetsStore("tok", ttl_seconds=100.0, now=lambda: clock["t"])
    store.read_range("SID", "Secretaria", "A1:A2")
    clock["t"] = 50.0
    store.read_range("SID", "Secretaria", "A1:A2")            # within TTL → cache
    assert calls["n"] == 1
    clock["t"] = 201.0
    store.read_range("SID", "Secretaria", "A1:A2")            # past TTL → refetch
    assert calls["n"] == 2


def test_fetch_falls_back_to_media_on_403(monkeypatch):
    # A native Sheet exports fine; an uploaded .xlsx 403s on export → media fallback. Simulate
    # by asserting the fallback path is reachable via a fake httpx client.
    seen = {"paths": []}

    class _Resp:
        def __init__(self, status):
            self.status_code = status
            self.content = b"xlsxbytes"

        def raise_for_status(self):
            if self.status_code >= 400 and self.status_code != 403:
                raise RuntimeError(self.status_code)

    class _Client:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None, headers=None):
            seen["paths"].append(("export" if url.endswith("/export") else "media", params))
            return _Resp(403 if url.endswith("/export") else 200)

    monkeypatch.setattr("cogno_praxis.coordinator.stores.google_sheets.httpx.Client", _Client)
    store = GoogleSheetsStore("tok")
    assert store._fetch("SID") == b"xlsxbytes"
    assert [p[0] for p in seen["paths"]] == ["export", "media"]      # tried export, fell back


def test_swap_rows_builds_batch_update(monkeypatch):
    xlsx = _xlsx("Secretaria", [
        ["Data", "Dia", "Professor", "Disciplina", "Sala"],
        ["16/07/2026", "Ter", "Ana", "Redes", "101"],       # abs row 2 (1-based) → range row 1
        ["18/07/2026", "Qui", "", "Livre", "205"],          # abs row 3 → range row 2
    ])
    monkeypatch.setattr(GoogleSheetsStore, "_fetch", lambda self, sid: xlsx)
    pushed = {}
    monkeypatch.setattr(GoogleSheetsStore, "_push_values",
                        lambda self, sid, data: pushed.update({"sid": sid, "data": data}))
    store = GoogleSheetsStore("tok")
    store.swap_rows("SID", "Secretaria", "A1:E10", 1, 2, content_cols=[2, 3, 4])
    ranges = {d["range"]: d["values"][0][0] for d in pushed["data"]}
    # content cols (C,D,E) exchanged between sheet rows 2 and 3; Data/Dia (A,B) untouched
    assert ranges["'Secretaria'!C2"] == "" and ranges["'Secretaria'!C3"] == "Ana"
    assert ranges["'Secretaria'!D2"] == "Livre" and ranges["'Secretaria'!D3"] == "Redes"
    assert "'Secretaria'!A2" not in ranges and "'Secretaria'!B2" not in ranges
