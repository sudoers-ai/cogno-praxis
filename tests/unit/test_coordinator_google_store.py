"""GoogleSheetsStore adapter — parse/cache/range/swap logic with the HTTP seams mocked.

No network: ``_fetch`` (download) and ``_push_values`` (write) are the only network methods and
are patched. The parse test builds a real ``.xlsx`` with openpyxl (skipped if it's absent)."""

from __future__ import annotations

import io
import logging

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
        def request(self, method, url, params=None, headers=None, **kw):
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


def test_swap_rows_follows_the_values_with_a_format_update(monkeypatch):
    """After the VALUES go (byte-for-byte as before), the per-cell FORMATTING follows: one
    ``updateCells`` per row, on the right ``GridRange`` (0-based rows/cols, the tab's sheetId),
    A's format written into B's cell and B's into A's, ``fields`` pinned to ``userEnteredFormat``.

    The formats are INVENTED opaque tokens; ``_read_formats`` is the mocked seam that hands them
    back with the tab's numeric sheetId."""
    xlsx = _xlsx("Secretaria", [
        ["Data", "Dia", "Professor", "Disciplina", "Sala"],
        ["16/07/2026", "Ter", "Ana", "Redes", "101"],       # abs row 2 (1-based) → range row 1
        ["18/07/2026", "Qui", "", "Livre", "205"],          # abs row 3 → range row 2
    ])
    monkeypatch.setattr(GoogleSheetsStore, "_fetch", lambda self, sid: xlsx)
    pushed_values = {}
    monkeypatch.setattr(GoogleSheetsStore, "_push_values",
                        lambda self, sid, data: pushed_values.update({"sid": sid, "data": data}))
    fmt_a = {2: {"w": "A-C"}, 3: {"w": "A-D"}, 4: {"w": "A-E"}}
    fmt_b = {2: {"w": "B-C"}, 3: {"w": "B-D"}, 4: {"w": "B-E"}}
    monkeypatch.setattr(GoogleSheetsStore, "_read_formats",
                        lambda self, sid, tab, rows: (77, {rows[0]: fmt_a, rows[1]: fmt_b}))
    pushed_reqs = {}
    monkeypatch.setattr(GoogleSheetsStore, "_push_requests",
                        lambda self, sid, requests: pushed_reqs.update({"sid": sid, "r": requests}))
    store = GoogleSheetsStore("tok")

    store.swap_rows("SID", "Secretaria", "A1:E10", 1, 2, content_cols=[2, 3, 4])

    # (a) the VALUES call is identical to the formatting-free swap of before
    def _cell(col: str, row: int) -> str:
        return f"'Secretaria'!{col}{row}"

    ranges = {d["range"]: d["values"][0][0] for d in pushed_values["data"]}
    assert ranges[_cell("C", 2)] == "" and ranges[_cell("C", 3)] == "Ana"
    assert ranges[_cell("D", 2)] == "Livre" and ranges[_cell("D", 3)] == "Redes"
    assert _cell("A", 2) not in ranges and _cell("B", 2) not in ranges

    # (b) two updateCells, one per row, with the swapped formats on the right GridRange
    reqs = pushed_reqs["r"]
    assert len(reqs) == 2
    by_row = {rq["updateCells"]["range"]["startRowIndex"]: rq["updateCells"] for rq in reqs}
    assert set(by_row) == {1, 2}                             # sheet rows 2 and 3, 0-based
    cell_a = by_row[1]                                       # row A's position gets B's format
    assert cell_a["range"] == {"sheetId": 77, "startRowIndex": 1, "endRowIndex": 2,
                               "startColumnIndex": 2, "endColumnIndex": 5}
    assert cell_a["fields"] == "userEnteredFormat"
    assert [v["userEnteredFormat"] for v in cell_a["rows"][0]["values"]] == \
        [fmt_b[2], fmt_b[3], fmt_b[4]]
    cell_b = by_row[2]                                       # row B's position gets A's format
    assert [v["userEnteredFormat"] for v in cell_b["rows"][0]["values"]] == \
        [fmt_a[2], fmt_a[3], fmt_a[4]]


def test_swap_rows_swaps_the_values_even_when_the_format_path_fails(monkeypatch, caplog):
    """If the formatting read or write fails, the CONTENTS are already swapped — today's state,
    never worse — and the adapter logs one closed line and returns without raising."""
    xlsx = _xlsx("Secretaria", [
        ["Data", "Professor", "Disciplina"],
        ["16/07/2026", "Ana", "Redes"],                     # abs row 2 → range row 1
        ["18/07/2026", "", "Livre"],                        # abs row 3 → range row 2
    ])
    monkeypatch.setattr(GoogleSheetsStore, "_fetch", lambda self, sid: xlsx)
    pushed_values = {}
    monkeypatch.setattr(GoogleSheetsStore, "_push_values",
                        lambda self, sid, data: pushed_values.update({"data": data}))

    def boom(self, sid, tab, rows):
        raise RuntimeError("the formatting read did not come back")

    monkeypatch.setattr(GoogleSheetsStore, "_read_formats", boom, raising=False)
    store = GoogleSheetsStore("tok")

    with caplog.at_level(logging.WARNING):
        store.swap_rows("SID", "Secretaria", "A1:C10", 1, 2, content_cols=[1, 2])   # no raise

    ranges = {d["range"]: d["values"][0][0] for d in pushed_values["data"]}
    assert ranges["'Secretaria'!B2"] == "" and ranges["'Secretaria'!B3"] == "Ana"   # values moved
    msgs = [r.getMessage() for r in caplog.records]
    assert any("event=sheet_format_swap_failed" in m for m in msgs), msgs


def test_write_cell_pushes_one_range_and_drops_the_cache(monkeypatch):
    """One cell, one range, and the cached workbook thrown away.

    The cache drop is the half worth pinning: the adapter answers reads out of a workbook it
    downloaded up to ten minutes ago, so a write that left it in place would be followed by a
    read still reporting the OLD status — an answer recorded and then denied by the very next
    listing. ``swap_rows`` drops it for the same reason."""
    xlsx = _xlsx("Secretaria", [
        ["Data", "Dia", "Professor", "Disciplina", "Status"],
        ["16/07/2026", "Ter", "Ana", "Redes", ""],          # abs row 2 (1-based) → range row 1
    ])
    monkeypatch.setattr(GoogleSheetsStore, "_fetch", lambda self, sid: xlsx)
    pushed = {}
    monkeypatch.setattr(GoogleSheetsStore, "_push_values",
                        lambda self, sid, data: pushed.update({"sid": sid, "data": data}))
    store = GoogleSheetsStore("tok")
    store.read_range("SID", "Secretaria", "A1:E10")                   # warm the cache
    assert "SID" in store._cache

    store.write_cell("SID", "Secretaria", "A1:E10", 1, 4, "Aceita")

    assert pushed["sid"] == "SID"
    assert pushed["data"] == [{"range": "'Secretaria'!E2", "values": [["Aceita"]]}]
    assert "SID" not in store._cache


def test_write_cell_refuses_a_cell_the_download_never_reached(monkeypatch):
    """A row or column outside the sheet it read is a coordinate the caller cannot have MEANT.

    The Sheets API would happily create it; this raises instead, so a wrong index becomes a
    failed call rather than a status written into empty space nobody will ever look at."""
    xlsx = _xlsx("Secretaria", [["Data", "Status"], ["16/07/2026", ""]])
    monkeypatch.setattr(GoogleSheetsStore, "_fetch", lambda self, sid: xlsx)
    pushed = []
    monkeypatch.setattr(GoogleSheetsStore, "_push_values",
                        lambda self, sid, data: pushed.append(data))
    store = GoogleSheetsStore("tok")

    with pytest.raises(IndexError):
        store.write_cell("SID", "Secretaria", "A1:B10", 9, 1, "Aceita")
    with pytest.raises(IndexError):
        store.write_cell("SID", "Secretaria", "A1:B10", 1, 9, "Aceita")

    assert pushed == [], "a refused coordinate must not reach the API"


# ── IPv4-first connect with an IPv6/any fallback (the broken-IPv6 hotfix) ──────────────
import httpx  # noqa: E402

from cogno_praxis.coordinator.stores import google_sheets as _gs  # noqa: E402


class _RecordingTransport:
    """Stands in for ``httpx.HTTPTransport`` to record the ``local_address`` without opening a
    socket; the IPv4 attempt builds one, the fallback builds none."""
    made: list[dict] = []

    def __init__(self, **kw):
        self.kw = kw
        _RecordingTransport.made.append(kw)


class _ScriptedClient:
    """Stands in for ``httpx.Client``. Each construction records its ``timeout``/``transport`` and
    pops the next outcome (an ``Exception`` to raise from ``.request`` or an ``httpx.Response`` to
    return)."""
    builds: list[dict] = []
    outcomes: list = []

    def __init__(self, *, timeout=None, transport=None):
        _ScriptedClient.builds.append({"timeout": timeout, "transport": transport})
        self._outcome = _ScriptedClient.outcomes.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def request(self, method, url, **kw):
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


def _install_script(monkeypatch, outcomes):
    _RecordingTransport.made = []
    _ScriptedClient.builds = []
    _ScriptedClient.outcomes = list(outcomes)
    monkeypatch.setattr(_gs.httpx, "HTTPTransport", _RecordingTransport)
    monkeypatch.setattr(_gs.httpx, "Client", _ScriptedClient)


def test_request_tries_ipv4_first_and_returns(monkeypatch):
    _install_script(monkeypatch, [httpx.Response(200, content=b"ok")])
    store = GoogleSheetsStore("tok")
    r = store._request("GET", "https://example/x")
    assert r.content == b"ok"
    # exactly one attempt, bound to IPv4 (0.0.0.0) with the short connect cap
    assert len(_ScriptedClient.builds) == 1
    assert _RecordingTransport.made == [{"local_address": "0.0.0.0"}]
    assert _ScriptedClient.builds[0]["transport"].kw == {"local_address": "0.0.0.0"}
    assert _ScriptedClient.builds[0]["timeout"].connect == _gs._CONNECT_IPV4_S


def test_request_falls_back_to_default_path_on_connect_error(monkeypatch, caplog):
    _install_script(monkeypatch,
                    [httpx.ConnectError("ipv6 route broken"), httpx.Response(200, content=b"v4")])
    store = GoogleSheetsStore("tok")
    with caplog.at_level(logging.INFO):
        r = store._request("GET", "https://example/x")
    assert r.content == b"v4"
    assert len(_ScriptedClient.builds) == 2
    # the fallback carries no IPv4 bind and uses the longer connect cap
    assert _ScriptedClient.builds[1]["transport"] is None
    assert _ScriptedClient.builds[1]["timeout"].connect == _gs._CONNECT_FALLBACK_S
    assert any("event=google_ipv4_connect_failed" in r.getMessage() for r in caplog.records)


def test_request_falls_back_on_connect_timeout(monkeypatch):
    _install_script(monkeypatch,
                    [httpx.ConnectTimeout("slow"), httpx.Response(200, content=b"v4")])
    store = GoogleSheetsStore("tok")
    assert store._request("GET", "https://example/x").content == b"v4"
    assert len(_ScriptedClient.builds) == 2


def test_request_propagates_cleanly_when_both_paths_fail(monkeypatch):
    _install_script(monkeypatch,
                    [httpx.ConnectError("v4 also broken"), httpx.ConnectError("and v6")])
    store = GoogleSheetsStore("tok")
    with pytest.raises(httpx.ConnectError):
        store._request("GET", "https://example/x")
    assert len(_ScriptedClient.builds) == 2


def test_read_timeout_is_not_retried(monkeypatch):
    # A ReadTimeout may mean the request left; the batchUpdate writes are not idempotent, so the
    # connect-only retry must NOT fire — exactly one attempt.
    _install_script(monkeypatch, [httpx.ReadTimeout("hung")])
    store = GoogleSheetsStore("tok")
    with pytest.raises(httpx.ReadTimeout):
        store._request("GET", "https://example/x")
    assert len(_ScriptedClient.builds) == 1


def test_all_four_network_methods_go_through_request(monkeypatch):
    calls: list[tuple[str, str]] = []

    class _Probe(Exception):
        pass

    def _rec(self, method, url, **kw):
        calls.append((method, url))
        raise _Probe()

    monkeypatch.setattr(GoogleSheetsStore, "_request", _rec)
    store = GoogleSheetsStore("tok")
    for invoke in (
        lambda: store._fetch("SID"),
        lambda: store._push_values("SID", [{"range": "'T'!A1", "values": [["x"]]}]),
        lambda: store._read_formats("SID", "T", [1]),
        lambda: store._push_requests("SID", [{"updateCells": {}}]),
    ):
        with pytest.raises(_Probe):
            invoke()
    assert len(calls) == 4
    assert calls[0][0] == "GET" and calls[0][1].endswith("/export")
    assert calls[1] == ("POST", f"{_gs._SHEETS}/SID/values:batchUpdate")
    assert calls[2] == ("GET", f"{_gs._SHEETS}/SID")
    assert calls[3] == ("POST", f"{_gs._SHEETS}/SID:batchUpdate")


def test_connect_budget_fits_the_dispatcher_ceiling():
    # 3 (IPv4 connect) + 8 (fallback connect) + 15 (default read/write/pool) = 26 ≤ 27 < 30 s cap.
    budget = _gs._CONNECT_IPV4_S + _gs._CONNECT_FALLBACK_S + GoogleSheetsStore("tok")._timeout
    assert budget <= 27
