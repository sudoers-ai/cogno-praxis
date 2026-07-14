"""The ``coordinator`` (academic-schedule) vertical as a FastMCP server.

A thin MCP wrapper over :class:`CoordinatorService`. The host connects via ``cogno-mcp``, so the
EGO sees these as ordinary tools; ``confirm_swap`` is annotated destructive so the EGO holds it
for confirmation. ``build_server(service)`` is the injection seam — the host builds a service
over its Google-download :class:`SpreadsheetStore` adapter and the tenant's parsed config. The
module-level demo reads ``COGNO_COORDINATOR_RULES`` (the custom_rules text) + an in-memory sheet
for standalone runs.

RBAC: the host injects ``identity_label`` + ``role`` (its RoleScopedDispatcher) so the service
scopes a professor to their own classes; an oversight role may query anyone.

Run the demo standalone (stdio):  ``python -m cogno_praxis.coordinator.server``
"""

from __future__ import annotations

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cogno_praxis.coordinator.config import CoordinatorConfig
from cogno_praxis.coordinator.service import CoordinatorError, CoordinatorService
from cogno_praxis.coordinator.store import InMemorySpreadsheetStore
from cogno_praxis.coordinator.types import ClassEntry


def _fmt_entry(e: ClassEntry) -> str:
    """One class as a compact, verbatim line — every non-empty header:cell so the model never
    has to guess column meaning (dates already normalized DD/MM/YYYY)."""
    parts = [f"{h}: {c}" for h, c in zip(e.header, e.cells) if c.strip()]
    return " | ".join(parts) if parts else e.date_str


def _fmt_list(entries: list[ClassEntry], *, empty: str) -> str:
    if not entries:
        return empty
    return "\n".join(f"- {_fmt_entry(e)}" for e in entries)


def _fmt_professors(rows: list[dict[str, str]]) -> str:
    """Faculty records as compact verbatim lines (every non-empty field:value)."""
    if not rows:
        return "No faculty records found."
    return "\n".join("- " + " | ".join(f"{k}: {v}" for k, v in r.items() if v.strip())
                     for r in rows)


def build_server(service: Optional[CoordinatorService] = None, *,
                 name: str = "cogno-coordinator") -> FastMCP:
    """Build a FastMCP server bound to a service (inject a Sheets-backed one in prod/tests)."""
    svc = service or _demo_service()
    mcp = FastMCP(name)

    def _guard(fn):
        try:
            return fn()
        except CoordinatorError as exc:
            return f"ERROR: {exc}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_professor_schedule(professor: str = "", month: str = "", discipline: str = "",
                               identity_label: str = "", role: str = "") -> str:
        """List a professor's class schedule (aggregated across all course spreadsheets, sorted
        by date). ``month`` filters by YYYY-MM, a bare number, or a PT-BR month name ("março").
        ``discipline`` filters by subject and is typo-tolerant ("machne learning" still matches).
        A professor sees only their own classes; a supervisor may name any professor or omit it
        for the whole master schedule."""
        return _guard(lambda: _fmt_list(
            svc.get_professor_schedule(professor=professor, month=month, discipline=discipline,
                                       identity_label=identity_label, role=role),
            empty="No classes found."))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_professor_info(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Faculty contact/detail lookup from the professors tab (e.g. discipline, workload,
        e-mail, degree). A professor sees only their own record; a supervisor may name anyone or
        omit ``professor`` to list the whole faculty."""
        return _guard(lambda: _fmt_professors(
            svc.get_professor_info(professor=professor, identity_label=identity_label, role=role)))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def check_deadlines(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Disciplines whose LAST class already happened and are still within the 14-day grade/
        attendance grace window (submission still due)."""
        return _guard(lambda: _fmt_list(
            svc.check_deadlines(professor=professor, identity_label=identity_label, role=role),
            empty="No disciplines within the grade/attendance deadline window."))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_weekly_briefing(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Classes in the next 7 days (a coordinator's weekly heads-up)."""
        return _guard(lambda: _fmt_list(
            svc.weekly_briefing(professor=professor, identity_label=identity_label, role=role),
            empty="No classes in the next 7 days."))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def check_ibope_status(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Last classes of a discipline happening TODAY — these need the end-of-course survey
        (IBOPE) reminder to the professor."""
        return _guard(lambda: _fmt_list(
            svc.ibope_status(professor=professor, identity_label=identity_label, role=role),
            empty="No last classes today — no survey reminders needed."))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def find_replacement_slot(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Open slots (free-slot labels) in the next 21 days — candidates for rescheduling a
        class into via confirm_swap."""
        return _guard(lambda: _fmt_list(
            svc.find_replacement_slot(professor=professor, identity_label=identity_label, role=role),
            empty="No open slots in the next 21 days."))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    def confirm_swap(professor: str, original_date: str, new_date: str, reason: str = "",
                     identity_label: str = "", role: str = "") -> str:
        """Move a professor's class (on ``original_date``) into a free slot (on ``new_date``):
        swaps the content columns, leaving dates fixed. Destructive — confirm with the user
        BEFORE calling. Both dates are DD/MM/YYYY."""
        def _do():
            src, dst = svc.confirm_swap(professor=professor, original_date=original_date,
                                        new_date=new_date, identity_label=identity_label, role=role)
            return (f"Swapped: {src.professor}'s {src.subject} moved from {src.date_str} "
                    f"to {dst.date_str}.")
        return _guard(_do)

    return mcp


def _demo_service() -> CoordinatorService:
    """Standalone/subprocess: config from COGNO_COORDINATOR_RULES; the store is the Google
    adapter when the host passes an OAuth token (COGNO_COORDINATOR_GOOGLE_TOKEN), else an empty
    in-memory fake (dev/demo). The host mints/refreshes the token and injects it per turn."""
    cfg = CoordinatorConfig(os.environ.get("COGNO_COORDINATOR_RULES", ""))
    token = os.environ.get("COGNO_COORDINATOR_GOOGLE_TOKEN", "")
    if token:
        from cogno_praxis.coordinator.stores.google_sheets import GoogleSheetsStore
        return CoordinatorService(GoogleSheetsStore(token), cfg)
    store = InMemorySpreadsheetStore()
    for _, sid in cfg.spreadsheets.items():
        store.put(sid, cfg.tab_schedule, [["Data", "Dia", "Professor", "Disciplina", "Sala"]])
    return CoordinatorService(store, cfg)


mcp = build_server()

if __name__ == "__main__":
    mcp.run()
