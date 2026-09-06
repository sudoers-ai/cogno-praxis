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

from datetime import date

from cogno_praxis.coordinator.config import CoordinatorConfig
from cogno_praxis.coordinator.service import (
    CoordinatorAccessError,
    CoordinatorError,
    CoordinatorService,
    _parse_date,
)
from cogno_praxis.coordinator.store import InMemorySpreadsheetStore
from cogno_praxis.coordinator.types import ClassEntry, ReadReport


def _says_the_same_date(cell: str, e: ClassEntry) -> bool:
    """Is this cell just the entry's date said again?

    A tenant's sheet may spend three columns on one day — the live layout is ``Mês | Dia | Data``
    and all three carry the identical value, which reached the model as
    ``Mês: 2026-09-08 00:00:00 | Dia: 2026-09-08 00:00:00 | Data: 2026-09-08 00:00:00``. Three
    readings of one fact is noise the reader has to reconcile before it can answer, and it
    crowded out the one thing the line did NOT say: which class group the class belongs to.

    The test is the DATE, not the column name: a column is folded away only when it parses to the
    very same day (or repeats the raw string verbatim, for a date that could not be parsed at
    all). A ``Dia`` holding "Terça" is a different fact and survives; so does a second, DIFFERENT
    date. Nothing is guessed from a header."""
    if cell.strip() == e.date_str.strip():
        return True
    parsed = _parse_date(cell)
    return bool(e.when and parsed and parsed == e.when)


def _fmt_entry(e: ClassEntry) -> str:
    """One class as a compact line: its CLASS GROUP, ONE date, then every other non-empty
    header:cell verbatim, so the model never has to guess column meaning.

    ``Turma`` leads because it is the field a professor teaching four groups needs first and the
    only one the line never had: the group is the spreadsheet's own key, the tenant's label, and
    it reached a human only inside an error message. The date follows once, normalized
    DD/MM/YYYY like the rest of the system."""
    parts: list[str] = []
    if e.sheet_key.strip():
        parts.append(f"Turma: {e.sheet_key.strip()}")
    if e.date_str.strip():
        parts.append(f"Data: {e.date_str.strip()}")
    parts += [f"{h}: {c}" for h, c in zip(e.header, e.cells)
              if c.strip() and not _says_the_same_date(c, e)]
    return " | ".join(parts) if parts else e.date_str


def _fmt_report(report: ReadReport) -> str:
    """The footer lines a read owes the reader: what was HIDDEN, and what could not be READ.

    Both are conditional, and that is the whole design. A permanent "showing from today onward"
    would train the reader to believe things are being withheld on every turn, including the
    turns where nothing was; a permanent "all spreadsheets read" is noise. They appear when they
    are TRUE and are silent otherwise."""
    lines: list[str] = []
    if report.unmatched_turma:
        known = ", ".join(report.known_turmas) or "(none configured)"
        lines.append(
            f'NO SUCH CLASS GROUP: "{report.unmatched_turma}" does not name any configured class '
            f"group. The groups are: {known}. If the request was not about a class group at all, "
            f"call again with `turma` empty — a word like \"de\" is usually a preposition, not a "
            f"group.")
    if report.hidden_past:
        lines.append(
            f"(Showing from today onward. {report.hidden_past} earlier class(es) matching this "
            f"request were not listed — say so explicitly to see past classes.)")
    if report.errors:
        detail = "; ".join(f"{e.sheet_key}: {e.message}" for e in report.errors)
        lines.append(
            f"PARTIAL RESULT — {len(report.errors)} spreadsheet(s) could not be read: {detail}. "
            f"Everything above was read normally; say which spreadsheet is unavailable.")
    return "\n".join(lines)


def _fmt_list(entries: list[ClassEntry], *, empty: str,
              report: Optional[ReadReport] = None) -> str:
    body = "\n".join(f"- {_fmt_entry(e)}" for e in entries) if entries else empty
    footer = _fmt_report(report) if report else ""
    return f"{body}\n\n{footer}" if footer else body


def _fmt_professors(rows: list[dict[str, str]], *, report: Optional[ReadReport] = None) -> str:
    """Faculty records as compact verbatim lines (every non-empty field:value)."""
    body = ("\n".join("- " + " | ".join(f"{k}: {v}" for k, v in r.items() if v.strip())
                      for r in rows) if rows else "No faculty records found.")
    footer = _fmt_report(report) if report else ""
    return f"{body}\n\n{footer}" if footer else body


def build_server(service: Optional[CoordinatorService] = None, *,
                 name: str = "cogno-coordinator") -> FastMCP:
    """Build a FastMCP server bound to a service (inject a Sheets-backed one in prod/tests)."""
    svc = service or _demo_service()
    mcp = FastMCP(name)

    def _guard(fn):
        """Run a domain call, turning its two failure KINDS into two different sentences.

        An access refusal is a RULE that worked, not a malfunction — labelling it ``ERROR`` is
        how "you may only see your own schedule" came back to a professor as "I could not access
        the schedule". The word the model reads is the word the contact eventually hears."""
        try:
            return fn()
        except CoordinatorAccessError as exc:
            return (f"NOT PERMITTED: {exc} This is an access rule working as intended, not a "
                    f"failure — state the limit plainly and offer what IS allowed.")
        except CoordinatorError as exc:
            return f"ERROR: {exc}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_professor_schedule(professor: str = "", month: str = "", discipline: str = "",
                               turma: str = "", include_past: bool = False,
                               identity_label: str = "", role: str = "") -> str:
        """List a professor's class schedule (aggregated across all course spreadsheets, sorted
        by date). EVERY line names its class group ("Turma: ..."), so an unfiltered read already
        answers "which group is this class in?".
        Returns UPCOMING classes only — from today onward — unless ``include_past``.
        ``month`` filters by YYYY-MM, a bare number, or a month name in Portuguese or English
        ("março", "September"). ``discipline`` filters by subject and is typo-tolerant ("machne
        learning" still matches). ``turma`` narrows to one class group or a family of them: a
        bare prefix takes the whole family ("DSA" → DSA_33 and DSA_34) and separators, case and
        spacing do not matter ("DE_09", "de 09", "DE09"). Fill ``turma`` ONLY with a group
        DESIGNATOR the user actually named — never a sentence and never a stray word; a group
        prefix can also be an ordinary Portuguese word, so in "as aulas de outubro" the "de" is a
        preposition and ``turma`` must stay EMPTY. Set ``include_past=True`` ONLY when the user
        explicitly asks about the past ("what I already taught", "my August classes", "the
        history") — naming a month that is already over counts as asking, and needs no flag;
        asking about OTHER CLASS GROUPS is not asking about the past. A professor sees only
        their own classes; a supervisor may name any professor or omit it for the whole master
        schedule."""
        report = ReadReport()
        return _guard(lambda: _fmt_list(
            svc.get_professor_schedule(professor=professor, month=month, discipline=discipline,
                                       turma=turma, include_past=include_past, report=report,
                                       identity_label=identity_label, role=role),
            empty="No classes found.", report=report))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_professor_info(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Faculty contact/detail lookup from the professors tab (e.g. discipline, workload,
        e-mail, degree). A professor sees only their own record; a supervisor may name anyone or
        omit ``professor`` to list the whole faculty."""
        report = ReadReport()
        return _guard(lambda: _fmt_professors(
            svc.get_professor_info(professor=professor, identity_label=identity_label,
                                   role=role, report=report), report=report))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def check_deadlines(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Disciplines whose LAST class already happened and are still within the 14-day grade/
        attendance grace window (submission still due)."""
        report = ReadReport()
        return _guard(lambda: _fmt_list(
            svc.check_deadlines(professor=professor, identity_label=identity_label, role=role,
                                report=report),
            empty="No disciplines within the grade/attendance deadline window.", report=report))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_weekly_briefing(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Classes in the next 7 days (a coordinator's weekly heads-up) — today onward, never
        the past."""
        report = ReadReport()
        return _guard(lambda: _fmt_list(
            svc.weekly_briefing(professor=professor, identity_label=identity_label, role=role,
                                report=report),
            empty="No classes in the next 7 days.", report=report))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def check_ibope_status(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Last classes of a discipline happening TODAY — these need the end-of-course survey
        (IBOPE) reminder to the professor."""
        report = ReadReport()
        return _guard(lambda: _fmt_list(
            svc.ibope_status(professor=professor, identity_label=identity_label, role=role,
                             report=report),
            empty="No last classes today — no survey reminders needed.", report=report))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def find_replacement_slot(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Open slots (free-slot labels) in the next 21 days — candidates for rescheduling a
        class into via confirm_swap."""
        report = ReadReport()
        return _guard(lambda: _fmt_list(
            svc.find_replacement_slot(professor=professor, identity_label=identity_label,
                                      role=role, report=report),
            empty="No open slots in the next 21 days.", report=report))

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
    # WHERE "today" COMES FROM. Not the process clock: this server runs as a stdio subprocess of
    # the host, and the host's container boots in UTC on purpose — so between 21:00 and midnight
    # in São Paulo the process would already believe it is tomorrow, and a class happening TODAY
    # would silently drop out of a list that is now cut at "today onward". The host stamps its
    # OWN anchor (the same date it renders as [HOJE] in the prompt) into COGNO_COORDINATOR_TODAY;
    # reading it is what makes the tool and the prompt incapable of disagreeing. The host has
    # been setting it since the vertical shipped — nothing here read it. Unset (a standalone run)
    # → the real date, exactly like the scheduler and bookkeeper servers.
    iso = os.environ.get("COGNO_COORDINATOR_TODAY")
    clock = (lambda: date.fromisoformat(iso)) if iso else None
    token = os.environ.get("COGNO_COORDINATOR_GOOGLE_TOKEN", "")
    if token:
        from cogno_praxis.coordinator.stores.google_sheets import GoogleSheetsStore
        return CoordinatorService(GoogleSheetsStore(token), cfg, today=clock)
    store = InMemorySpreadsheetStore()
    for _, sid in cfg.spreadsheets.items():
        store.put(sid, cfg.tab_schedule, [["Data", "Dia", "Professor", "Disciplina", "Sala"]])
    return CoordinatorService(store, cfg, today=clock)


mcp = build_server()

if __name__ == "__main__":
    mcp.run()
