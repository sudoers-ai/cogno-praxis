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

from cogno_praxis.coordinator.ics import CalendarEvent, CalendarSender
from cogno_praxis.coordinator.config import CoordinatorConfig
from cogno_praxis.coordinator.pay import render_pay_block
from cogno_praxis.coordinator.service import (
    CalendarProposal,
    CoordinatorAccessError,
    CoordinatorConfigError,
    CoordinatorError,
    CoordinatorService,
    _norm,
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
    are TRUE and are silent otherwise.

    **Only ONE of these lines is an incompleteness, and they must not be worded alike.** Three
    of the four are windows and filters working; ``errors`` is the one that is not.

    ``errors`` is one: a spreadsheet could not be read, so the answer really is partial and the
    reader needs to know HOW MUCH is missing. It COUNTS, deliberately.

    ``hidden_past`` is not, and neither is ``beyond_horizon`` — they are the same fact said at
    the two ends of one window. The list is whole for the window the tool chose; the window is a
    default, not a failure. So this line carries ONE BIT — *something lies outside the window,
    and here is the argument that widens it* — and never a MEASUREMENT of what is outside.

    **That distinction was bought, not designed.** The line used to quantify the outside
    ("N earlier class(es) matching this request were not listed"). It was written for the
    EXECUTOR, as the offer of a next step. But a tool result has ONE reader-facing string and no
    second channel: ``ToolResult.output`` is a single field, and the SUPEREGO judge is handed the
    same bytes verbatim inside ``<tool_output>``. So the judge read that sentence as the
    execution admitting it had left work undone. Measured over a live conversation on
    2026-09-06: of the four occurrences of one ordinary follow-up question, THREE were rejected
    by the judge, and the critiques quote this line back — "did not clarify that there are N
    previous classes not listed", and, most plainly, "included a note about omitted earlier
    classes ... which could be seen as incomplete". The note had become the accusation. Each
    rejection spent a correction round, and the loop then steered the executor into answering
    about the past instead of the question actually asked.

    A COUNT is only actionable as a deficit, and the one reader that acts on a deficit is the
    one grading completeness. A BIT plus an argument name is actionable by the executor and by
    nobody else — which is as close to addressing a single recipient as this contract allows
    (inventing a second channel is the core's business, not a skill's). The ``unmatched_turma``
    line above already speaks this way: it names the argument to change, not the size of the
    miss. Note also what this line does NOT claim: it never says the list is complete, because a
    failed spreadsheet can be cut from the SAME read and the two lines would then contradict
    each other."""
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
            "(This list covers today onward — this tool's default window. Earlier classes are "
            "one argument away: call again with `include_past=true`, but only if the user asks "
            "about the past.)")
    if report.beyond_horizon:
        lines.append(
            "(This list covers the next 30 days — this tool's default window when no period was "
            "asked for. Later classes are one argument away: call again with `month` set to the "
            "month the user names. Offer to look further ahead; do not say how many are out "
            "there.)")
    if report.errors:
        detail = "; ".join(f"{e.sheet_key}: {e.message}" for e in report.errors)
        lines.append(
            f"PARTIAL RESULT — {len(report.errors)} spreadsheet(s) could not be read: {detail}. "
            f"Everything above was read normally; say which spreadsheet is unavailable.")
    return "\n".join(lines)


#: Month names for the listing header, in the contact's language.
#:
#: Portuguese, and DECLARED here rather than read from ``calendar.month_name`` — the same carve-
#: out the repo grants Portuguese domain data (the slang map, the birth-context regex): this
#: string is not internal prose, it is the text a professor reads. ``calendar.month_name``
#: answers in the SERVER's locale, which on this deployment is the container's, which is C —
#: "September" in the middle of a Portuguese reply.
#:
#: One entry per month, index = month number. Delete one and that month loses its name, which is
#: what ``test_coordinator_listing.py`` exists to catch.
_MONTH_LABELS_PT: tuple[str, ...] = (
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)


def _month_header(when: date) -> str:
    """``*Setembro de 2026*`` — the group header for one month, bold.

    **ONE asterisk, because WhatsApp's bold is ``*text*`` and not ``**text**``.** This shipped
    with two, on the premise that "WhatsApp and Telegram both render ``**text**``". That premise
    is false for the channel these replies actually reach a professor through: WhatsApp renders
    a single pair and passes a double pair through UNCHANGED, so every month header a contact
    received arrived with the asterisks VISIBLE. Nothing anywhere converts markup on the way
    out — not this vertical, not the host, not the gateway — so what this function writes is
    what a person reads, byte for byte.

    ``coordinator/pay.py`` had it right the whole time (``_H = "*{}*"``, with the reason in a
    comment beside it), which is the sharpest evidence available that this was a slip rather
    than a disagreement: one package, two renderers, one of them already correct.

    **This is a DRESSING, not the design.** The real answer is that a vertical emits STRUCTURE
    — grouping, order, which fields — and a GATEWAY translates it to the channel's dialect
    once, at the end, over the whole voiced text (``*x*`` on WhatsApp, ``<b>x</b>`` on Telegram,
    Markdown left alone on the web). That adapter does not exist yet, and until it does this
    single asterisk is what makes WhatsApp work. Whoever builds it should know there is an
    asterisk here waiting to be normalized, and that Telegram TOLERATES this one meanwhile.

    A month the table does not name falls back to its number rather than raising — a listing is
    not the place to discover a bad constant, and ``09/2026`` is still readable."""
    name = _MONTH_LABELS_PT[when.month] if when.month < len(_MONTH_LABELS_PT) else ""
    return f"*{name} de {when.year}*" if name else f"*{when.month:02d}/{when.year}*"


def _entry_status(e: ClassEntry, defaults: tuple[str, ...], column: str) -> str:
    """This row's status, but ONLY when it is not the ordinary one — else ``""``.

    Read by HEADER NAME (the tenant's ``COLUMN_STATUS``), never by position, and compared with
    ``_norm`` so accents and case do not decide whether a professor is warned."""
    want = _norm(column)
    if not want:
        return ""
    for h, c in zip(e.header, e.cells):
        if _norm(h) != want:
            continue
        val = c.strip()
        if not val or any(_norm(val) == _norm(d) for d in defaults):
            return ""
        return val
    return ""


def _fmt_line(e: ClassEntry, *, defaults: tuple[str, ...] = (), status_column: str = "") -> str:
    """One class as the line a professor actually reads: ``08/09 · DE_09 · Bancos NoSQL``.

    Three facts, in the order the eye needs them under a header that already fixed the month:
    the DAY, the class GROUP, the DISCIPLINE. Plus the status, and only when it is not the
    ordinary one.

    **What this drops is the point.** The old line was ``Turma: X | Data: Y | Disciplina: Z``
    with every remaining non-empty column appended as ``Header: value`` — a label on every field
    of every row, repeating on all 33 lines the words the reader learned on the first one, and
    the year repeating under a header that just said it. The class group loses its ``Turma``
    prefix here because the header of the line beside it never needed one either.

    ``_fmt_entry`` above keeps the labelled form, and that is not an oversight: it renders the
    DESCRIPTION of a calendar event, where there is no listing around the line to give a bare
    field its meaning."""
    day = e.when.strftime("%d/%m") if e.when else e.date_str.strip()
    parts = [p for p in (day, e.sheet_key.strip(), e.subject.strip()) if p]
    status = _entry_status(e, defaults, status_column)
    if status:
        parts.append(status)
    return " · ".join(parts) if parts else e.date_str


def _status_args(svc: CoordinatorService) -> dict:
    """The tenant's status vocabulary, as the two keyword arguments the listing takes.

    One reader of ``cfg`` instead of six: the six read tools all render the same lines, and a
    seventh arriving later must not have to remember to pass this."""
    return {"defaults": svc.cfg.status_default_labels, "status_column": svc.cfg.column_status}


def _fmt_list(entries: list[ClassEntry], *, empty: str,
              report: Optional[ReadReport] = None,
              defaults: tuple[str, ...] = (), status_column: str = "") -> str:
    """The listing: classes grouped under a bold month header, in date order.

    **This function is not adding a shape — it is refusing to destroy one.** Measured on the
    box's own turns for 2026-09-06: handed the flat labelled block, the executor's own draft came
    back grouped by month, bold, one line per class, and had even folded four same-discipline
    dates onto one line. Nothing asked it to; that is simply what this data wants to look like.
    Then the voicer discarded that draft's shape and reproduced the flat block instead, because
    ``limits.txt`` told it the raw tool output IS the expected format. The model was right and
    the prompt overruled it. Rendering the shape HERE is what makes the instruction and the
    result the same thing, so nothing downstream has to choose between them.

    Entries whose date could not be parsed keep the labelled ``_fmt_entry`` form and go last,
    with no header of their own: the read deliberately never hides what it cannot date, and a
    row that reached here without a month is exactly the row whose every column is worth
    showing."""
    if not entries:
        body = empty
    else:
        chunks: list[str] = []
        current: Optional[tuple[int, int]] = None
        for e in entries:
            if e.when is None:
                chunks.append(f"- {_fmt_entry(e)}")
                continue
            key = (e.when.year, e.when.month)
            if key != current:
                chunks.append(("\n" if chunks else "") + _month_header(e.when))
                current = key
            chunks.append(f"- {_fmt_line(e, defaults=defaults, status_column=status_column)}")
        body = "\n".join(chunks)
    footer = _fmt_report(report) if report else ""
    return f"{body}\n\n{footer}" if footer else body


def _calendar_proposal_text(p: CalendarProposal,
                            report: Optional[ReadReport] = None) -> str:
    """The question a calendar send owes the professor, GROUNDED in what was just read.

    Every number in it came out of the read: the COUNT is the events that were built, the
    ADDRESS is the one the send would resolve, the PERIOD is the filter that was actually
    applied. Nothing is passed through from the caller's arguments, and nothing is filled in
    when the read did not produce it — a proposal that names a month nobody filtered by, or
    rounds a count, gets an agreement to something other than what arrives.

    **The period clause is CONDITIONAL for exactly that reason.** A request with no month, or
    with a word the resolver could not read as one, filtered by no period at all; the sentence
    then says how many classes and where, and claims no period. The alternative — echoing the
    caller's string — is how "as aulas de outubro" would be proposed as October over a read
    that never filtered.

    It deliberately does NOT start with the ``SENT:`` marker the rest of the system reads as
    proof an e-mail left (``prompts/limits.txt``, ``prompts/voice.txt``): nothing was sent, and
    that marker is how every layer downstream tells the two apart. What it carries instead is a
    ``PROPOSAL:`` marker of its own, and the three facts live on THAT ONE LINE, adjacent.

    **The single line is a defence, not a layout choice.** This text is not what the contact
    reads — a voicer rewrites it first, and on 2026-09-06 that rewrite is exactly where the
    month was lost: the executor's own draft said "1 aula de setembro / 08/09/2026" and the
    reply that reached the professor announced OCTOBER, lifted out of a listing given six turns
    earlier. A count in one sentence and a period in another are two things to re-attach, and a
    re-attachment can go to the wrong list. Glued into one short line they are one fact to copy,
    which is the hardest shape to deform. Nothing here can guarantee the voicer copies it; what
    it can do is make copying the easy path and splitting the deliberate one.
    """
    period = f" of {p.period}" if p.period else ""
    lines = ["NOT SENT — no e-mail has left.",
             f"PROPOSAL: {p.count} class(es){period} → {p.recipient}",
             "Put THAT ONE LINE to the user, the three facts together and unchanged: the count, "
             "the period and the address are a single fact. Splitting them across sentences, or "
             "taking any of them from an earlier listing in this conversation, is how a period "
             "comes to belong to another month's classes. The classes it covers:"]
    lines += [f"  - {_fmt_event(e)}" for e in p.events]
    if p.dropped:
        lines.append(f"({p.dropped} class(es) carry a date this system could not read and would "
                     f"be left out of that count.)")
    lines.append(
        "Only after an explicit yes, call send_schedule_to_calendar with the SAME "
        "professor/month/turma. NOTHING has been sent by this call.")
    footer = _fmt_report(report) if report else ""
    body = "\n".join(lines)
    return f"{body}\n\n{footer}" if footer else body


def _fmt_event(e: CalendarEvent) -> str:
    """One entry a proposal lists, read off the calendar EVENT rather than the sheet row.

    The event is what would actually be created, and it already carries the line a schedule
    read writes (``describe`` renders ``_fmt_entry`` into its description), so the proposal and
    the listing the professor saw a turn earlier read alike instead of being two formats for
    one fact. With no ``describe`` there is still a summary and a day — never nothing, because
    a proposal that lists blank rows is a proposal a person cannot check."""
    return e.description.strip() or f"{e.summary} — {e.day.strftime('%d/%m/%Y')}"


def _fmt_professors(rows: list[dict[str, str]], *, report: Optional[ReadReport] = None) -> str:
    """Faculty records as compact verbatim lines (every non-empty field:value)."""
    body = ("\n".join("- " + " | ".join(f"{k}: {v}" for k, v in r.items() if v.strip())
                      for r in rows) if rows else "No faculty records found.")
    footer = _fmt_report(report) if report else ""
    return f"{body}\n\n{footer}" if footer else body


def build_server(service: Optional[CoordinatorService] = None, *,
                 name: str = "cogno-coordinator",
                 sender: Optional[CalendarSender] = None,
                 tz_name: Optional[str] = None) -> FastMCP:
    """Build a FastMCP server bound to a service (inject a Sheets-backed one in prod/tests).

    ``sender`` is the calendar-mail port. ``None`` falls back to whatever the environment
    declares (:func:`_demo_sender`), and when THAT is ``None`` too the calendar tool refuses
    honestly and sends nothing — the deliberate behaviour of a deployment with no SMTP.

    ``tz_name`` is the tenant's zone NAME for the exported events' ``TZID``; ``None`` reads
    ``COGNO_COORDINATOR_TZ`` (the host stamps it from its own ``tenant_tz``). Absent, the
    export renders all-day events rather than inventing a zone.
    """
    svc = service or _demo_service()
    snd = sender if sender is not None else _demo_sender()
    tz = tz_name if tz_name is not None else os.environ.get("COGNO_COORDINATOR_TZ", "")
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
        except CoordinatorConfigError as exc:
            # A tenant that has not DECLARED something — or declared it wrongly — is not a system
            # that BROKE, and the two must not share a word. "ERROR" is what a model relays as
            # "não consegui acessar"; this has to reach the contact as configuration somebody can
            # go and fix. Same distinction ``NOT PERMITTED`` draws for a rule that worked.
            # Caught by TYPE: the first cut matched a substring of the message across two files,
            # which is a contract nobody can see and that a reworded sentence silently breaks.
            return (f"NOT CONFIGURED: {exc} This is missing or malformed configuration, not a "
                    f"malfunction — say so plainly and estimate nothing.")
        except CoordinatorError as exc:
            return f"ERROR: {exc}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_professor_schedule(professor: str = "", month: str = "", discipline: str = "",
                               turma: str = "", include_past: bool = False,
                               identity_label: str = "", role: str = "") -> str:
        """List a professor's class schedule (aggregated across all course spreadsheets, sorted
        by date, under a bold month header). EVERY line names its class group as its MIDDLE
        field, unlabelled — ``08/09 · DE_09 · Bancos NoSQL`` — so an unfiltered read already
        answers "which group is this class in?".
        Returns the next 30 days, from today onward. ``include_past`` reaches backwards; a named
        ``month`` or ``discipline`` drops the forward cut, ``turma`` does not.
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
            empty="No classes found.", report=report, **_status_args(svc)))

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
            empty="No disciplines within the grade/attendance deadline window.", report=report, **_status_args(svc)))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_weekly_briefing(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Classes in the next 7 days (a coordinator's weekly heads-up) — today onward, never
        the past."""
        report = ReadReport()
        return _guard(lambda: _fmt_list(
            svc.weekly_briefing(professor=professor, identity_label=identity_label, role=role,
                                report=report),
            empty="No classes in the next 7 days.", report=report, **_status_args(svc)))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def check_ibope_status(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Last classes of a discipline happening TODAY — these need the end-of-course survey
        (IBOPE) reminder to the professor."""
        report = ReadReport()
        return _guard(lambda: _fmt_list(
            svc.ibope_status(professor=professor, identity_label=identity_label, role=role,
                             report=report),
            empty="No last classes today — no survey reminders needed.", report=report, **_status_args(svc)))

    # READ-ONLY, and self-only inside the service. The scope this opened is "a professor may
    # ask what THEY earn"; there is no argument here that reaches anybody else's figure, and
    # ``professor`` exists only so a model that tries gets a stated refusal rather than being
    # quietly handed its own numbers under someone else's name.
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def estimate_professor_pay(period: str = "", turma: str = "", professor: str = "",
                               identity_label: str = "", role: str = "") -> str:
        """Estimate what the CALLER'S OWN classes come to: classes × the discipline's hour total
        × the institution's declared hourly rate, plus the IBOPE bonus when a survey result
        exists. Use it for "quanto eu recebo/vou receber", "qual minha remuneração", "quanto dá
        o meu mês". ``period`` is a month exactly like get_professor_schedule's ``month``
        ("setembro", "September", "09", "2026-09"); leave it EMPTY for everything from today
        onward, and call once per month when the user names two. ``turma`` narrows to one class
        group. Nothing is written and nothing is sent.
        This is ONLY ever about the person asking: leave ``professor`` EMPTY. Another
        professor's remuneration is not available here to anyone, whatever their role.
        Its answer is a READY-MADE BLOCK — relay it as it came, keeping the bold headers and the
        lines; do not re-add up, re-round or re-order it. If it says the IBOPE result was NOT
        FOUND, that sentence and the hypotheses under it must survive into the reply, all of
        them: they are what stops a single figure being read as the amount that will be paid.
        If it comes back NOT CONFIGURED, this institution has not declared the pay figures —
        say exactly that and do not estimate anything from memory."""
        report = ReadReport()

        def _run() -> str:
            est = svc.estimate_professor_pay(professor=professor, period=period, turma=turma,
                                             identity_label=identity_label, role=role,
                                             report=report)
            if not est.groups:
                return ("No classes found for this period, so there is nothing to estimate. "
                        "Say that plainly — it is an answer, not a failure.")
            footer = _fmt_report(report)
            block = render_pay_block(est)
            return f"{block}\n\n{footer}" if footer else block

        return _guard(_run)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def find_replacement_slot(professor: str = "", identity_label: str = "", role: str = "") -> str:
        """Open slots (free-slot labels) in the next 21 days — candidates for rescheduling a
        class into via confirm_swap."""
        report = ReadReport()
        return _guard(lambda: _fmt_list(
            svc.find_replacement_slot(professor=professor, identity_label=identity_label,
                                      role=role, report=report),
            empty="No open slots in the next 21 days.", report=report, **_status_args(svc)))

    # READ-ONLY, and that annotation is the point rather than a detail. ``send_schedule_to_
    # calendar`` is held before it runs — by its own ``destructiveHint`` and, on a host that
    # gates every write, by name regardless — so the skill never reads and therefore has
    # nothing to base a question on; the contact is asked about a raw argument. A read is held
    # by nobody, so this one RUNS, reads the same rows the send would, and hands back the
    # sentence the send cannot produce for itself. It is the same relationship
    # ``find_replacement_slot`` has with ``confirm_swap``: the read that grounds the write.
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def preview_schedule_to_calendar(professor: str = "", month: str = "", turma: str = "",
                                     identity_label: str = "", role: str = "",
                                     identity_email: str = "") -> str:
        """What send_schedule_to_calendar WOULD mail — how many classes, for which period, and
        to which address — WITHOUT sending anything. Call this FIRST, every time, before
        send_schedule_to_calendar: it reads the same schedule the send would and answers with
        the exact count, period and recipient, so you can put those numbers to the user and get
        a yes about the real thing. Take the same ``professor``/``month``/``turma`` you intend
        to send with, and then send with EXACTLY those. Its answer starts with "NOT SENT" —
        nothing left, and you must not say anything did — and carries ONE "PROPOSAL:" line with
        the count, the period and the address together: put that line to the user unchanged,
        never re-assembled from an earlier listing. If it comes back as an ERROR, the send would
        fail the same way: relay that instead of proposing.
        """
        report = ReadReport()
        return _guard(lambda: _calendar_proposal_text(
            svc.preview_schedule_to_calendar(
                sender=snd, professor=professor, month=month, turma=turma,
                identity_label=identity_label, role=role, identity_email=identity_email,
                describe=_fmt_entry, report=report),
            report))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    async def send_schedule_to_calendar(professor: str = "", month: str = "", turma: str = "",
                                        identity_label: str = "", role: str = "",
                                        identity_email: str = "") -> str:
        """E-mail the professor's UPCOMING classes as ONE calendar file (.ics) they import in a
        single action — "manda minhas aulas pro meu calendário", "envia meu calendário de
        setembro". ``month`` and ``turma`` narrow it exactly like get_professor_schedule; leave
        ``professor`` EMPTY for the caller's own classes. THIS SENDS AN E-MAIL: call
        preview_schedule_to_calendar FIRST with the same arguments, put ITS count, period and
        address to the user, and get an explicit yes BEFORE calling this —
        the system also holds the call and asks. The recipient is resolved by the system from
        the professor's own records and can NOT be chosen here. A professor may only send their
        own calendar; a coordinator/supervisor may send another professor's.
        On success the answer starts with SENT: — and ONLY then did an e-mail leave. Any error
        means NOTHING was sent: say what it says and never claim otherwise."""
        report = ReadReport()
        try:
            count, to, dropped = await svc.send_schedule_to_calendar(
                sender=snd, professor=professor, month=month, turma=turma,
                identity_label=identity_label, role=role, identity_email=identity_email,
                tz_name=tz, describe=_fmt_entry, report=report)
        except CoordinatorAccessError as exc:
            # RAISED, not returned as text, and the two halves of that are separate.
            # RAISING is the accounting: a FastMCP tool that RETURNS is a successful call, and
            # the MCP bridge stamps a successful call on a non-read-only tool as a write that
            # happened. Nothing was sent here, so nothing may be recorded as sent.
            # The WORDING is the other half — the same sentence `_guard` writes, because a
            # refusal is a rule working and a model handed the bare word "error" reports a
            # breakdown to the contact.
            raise CoordinatorError(
                f"NOT PERMITTED — nothing was sent. {exc} This is an access rule working as "
                f"intended, not a failure: state the limit plainly and offer what IS allowed."
            ) from exc
        detail = _fmt_report(report)
        extra = (f" ({dropped} class(es) had a date this system could not read and were left "
                 f"out.)" if dropped else "")
        return (f"SENT: {count} class(es) e-mailed to {to} as one calendar attachment.{extra}"
                + (f"\n\n{detail}" if detail else ""))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    def confirm_swap(professor: str, original_date: str, new_date: str, reason: str = "",
                     identity_label: str = "", role: str = "") -> str:
        """Move a professor's class (on ``original_date``) into a free slot (on ``new_date``):
        swaps the content columns, leaving dates fixed. Destructive — confirm with the user
        BEFORE calling. Both dates are DD/MM/YYYY."""
        # NOT ``_guard``, and that is the whole point of this call site. ``_guard`` RETURNS a
        # sentence, which is right for the six READ tools above it — a read is stamped
        # ``side_effect=False`` whatever it answers. This tool is MUTATING, so a returned
        # "ERROR: ..." / "NOT PERMITTED: ..." is a successful call on a non-read-only tool, and
        # the bridge stamps it as a write that happened: a refused swap declaring a commit.
        # Raising is the accounting — the same reason ``send_schedule_to_calendar`` above
        # raises, stated in ``service.py``: ``isError`` → ``ok=False`` → ``side_effect=False``.
        # The WORDING is kept verbatim from ``_guard``, because a refusal is a rule working and
        # a model handed the bare word "error" reports a breakdown to the contact.
        try:
            src, dst = svc.confirm_swap(professor=professor, original_date=original_date,
                                        new_date=new_date, identity_label=identity_label,
                                        role=role)
        except CoordinatorAccessError as exc:
            raise CoordinatorError(
                f"NOT PERMITTED — nothing was swapped. {exc} This is an access rule working as "
                f"intended, not a failure — state the limit plainly and offer what IS allowed."
            ) from exc
        return (f"Swapped: {src.professor}'s {src.subject} moved from {src.date_str} "
                f"to {dst.date_str}.")

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


def _demo_sender() -> Optional[CalendarSender]:
    """The calendar mailer for a standalone/subprocess run: whatever SMTP the environment
    declares, else ``None``.

    ``None`` is a real, shipped state and not a degraded one: most deployments have no mail
    server, and the tool's answer there is an honest refusal with zero send. What must never
    happen is the third possibility — a sender that accepts the message and drops it."""
    from cogno_praxis.coordinator.mailer import sender_from_env
    return sender_from_env()


mcp = build_server()

if __name__ == "__main__":
    mcp.run()
