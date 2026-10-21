"""A SEED of classes for the coordinator, read from a FILE, for ONE tenant.

The coordinator's classes come from the tenant's Google spreadsheets. With no OAuth token the
stdio subprocess serves an EMPTY in-memory store (``server._demo_service``), and that is what a
rehearsal tenant — one with no Google grant — gets: no classes, nothing to rehearse. The
scheduler solved the same problem for harnesses with ``COGNO_SCHEDULER_SEED``.

``COGNO_COORDINATOR_SEED_FILE`` names a JSON file::

    {"tenant": "<the tenant id this seed belongs to>",
     "sheets": {"<spreadsheet id>": {"<tab name>": [[<row 1 cells>], [<row 2 cells>], ...]}}}

A grid is the tab as it is in the spreadsheet, row 1 first (the metadata rows above a
``RANGE_SCHEDULE`` of ``A4:…`` included), every cell a string.

**The tenant is the guard, and it is the point.** The subprocess inherits the box's environment,
so a seed file set on the box reaches the coordinator of EVERY tenant. The file is applied only
when the tenant the host names for this turn, ``COGNO_COORDINATOR_TENANT``, is EXACTLY the file's
own; absent, blank, or another tenant, and the store is the empty one of today. Three more
limits, each fail-closed:

* never over a Google token — the caller applies the seed on the in-memory path only;
* only the spreadsheet ids the tenant's own rules name (``CoordinatorConfig.spreadsheets``);
* a file that cannot be read whole (missing, not JSON, not the shape above) seeds nothing.

What the seed is NOT: durable. The store lives as long as the subprocess, so a write the
coordinator makes over a seeded sheet (an attendance, a swap) is not there on a later read by a
new subprocess. It is a rehearsal's fixture.

The lines it writes say how many and which kind (``LOGGING.md``) — never the tenant, a
spreadsheet id, a tab, the path or a cell.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterable, Mapping, Optional

log = logging.getLogger(__name__)

#: The path of the seed file. Unset → nothing here runs.
SEED_FILE_ENV = "COGNO_COORDINATOR_SEED_FILE"
#: The tenant the HOST says this turn runs for. Unset or blank → no seed is ever applied.
TENANT_ENV = "COGNO_COORDINATOR_TENANT"


def _grid(raw: Any) -> "Optional[list[list[str]]]":
    """A tab's grid when ``raw`` is a list of rows of strings; ``None`` otherwise."""
    if not isinstance(raw, list):
        return None
    out: "list[list[str]]" = []
    for row in raw:
        if not isinstance(row, list) or not all(isinstance(c, str) for c in row):
            return None
        out.append(list(row))
    return out


def read_seed(path: str) -> "Optional[tuple[str, dict[str, dict[str, list[list[str]]]]]]":
    """``(tenant, {spreadsheet id: {tab: grid}})`` from the file at ``path`` — or ``None``, with
    one WARNING that names the KIND of the problem. A file is used whole or not at all."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        log.warning("stage=coordinator event=seed_unreadable reason=missing")
        return None
    try:
        data = json.loads(text)
    except ValueError:
        log.warning("stage=coordinator event=seed_unreadable reason=not_json")
        return None
    tenant = data.get("tenant") if isinstance(data, Mapping) else None
    sheets = data.get("sheets") if isinstance(data, Mapping) else None
    if not isinstance(tenant, str) or not isinstance(sheets, Mapping):
        log.warning("stage=coordinator event=seed_unreadable reason=not_the_shape")
        return None
    out: "dict[str, dict[str, list[list[str]]]]" = {}
    for sheet_id, tabs in sheets.items():
        if not isinstance(sheet_id, str) or not isinstance(tabs, Mapping):
            log.warning("stage=coordinator event=seed_unreadable reason=not_the_shape")
            return None
        out[sheet_id] = {}
        for tab, raw in tabs.items():
            grid = _grid(raw)
            if not isinstance(tab, str) or grid is None:
                log.warning("stage=coordinator event=seed_unreadable reason=not_the_shape")
                return None
            out[sheet_id][tab] = grid
    return tenant.strip(), out


def apply_seed(store: Any, spreadsheet_ids: "Iterable[str]",
               env: "Optional[Mapping[str, str]]" = None) -> int:
    """Put the seed's grids into ``store`` (an ``InMemorySpreadsheetStore``) when the file is
    THIS tenant's, and return how many rows went in (``0`` = nothing was seeded). Never raises."""
    env = os.environ if env is None else env
    path = (env.get(SEED_FILE_ENV) or "").strip()
    if not path:
        return 0
    running = (env.get(TENANT_ENV) or "").strip()
    if not running:
        log.debug("stage=coordinator event=seed_skipped reason=no_tenant")
        return 0
    seed = read_seed(path)
    if seed is None:
        return 0
    owner, sheets = seed
    if not owner or owner != running:
        log.debug("stage=coordinator event=seed_skipped reason=other_tenant")
        return 0
    named = set(spreadsheet_ids)
    mine = {sid: tabs for sid, tabs in sheets.items() if sid in named}
    if not mine:
        log.debug("stage=coordinator event=seed_skipped reason=no_sheet_for_rules")
        return 0
    rows = 0
    for sheet_id, tabs in mine.items():
        for tab, grid in tabs.items():
            store.put(sheet_id, tab, grid)
            rows += len(grid)
    log.info("stage=coordinator event=seed_applied sheets=%d rows=%d", len(mine), rows)
    return rows
