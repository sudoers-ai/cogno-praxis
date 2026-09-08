"""The listing a professor reads — and the two ends of the window it answers.

Both halves come out of ONE measured conversation on the box (2026-09-06, the tenant's own
coordinator persona), and neither is the repair for the incident that conversation is famous for.

**The shape.** Handed the flat labelled block, the executor's own draft came back grouped by
month, bold, one line per class — and had even folded four same-discipline dates onto one line.
Nothing asked it to. Then the voicer discarded that draft and reproduced the flat block, because
``limits.txt`` said the raw tool output IS the expected format. So the work here is not "add
grouping": the grouping was already being produced and then thrown away. Rendering it in the tool
is what stops the prompt from overruling the model.

**The window.** The same turn, "traga minhas aulas" with no period named, answered with 33
classes running to June 2027 — the whole academic year. The read now stops about a month out and
says which argument goes further.

**What these tests do NOT cover, stated because the title would otherwise imply it:** the class
that vanished from that listing and came back seven minutes later. That class was 24 days out,
INSIDE the new horizon, and the identical unfiltered read returned it later the same minute-span.
Whatever ate it lives upstream of everything asserted here.
"""

from __future__ import annotations

import asyncio
from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ReadReport,
)
from cogno_praxis.coordinator.server import _fmt_line, _month_header, build_server

_SID = "1QwErTy-UiOpAsDfGhJkLzXcVbNm45678"
_RULES = (f"SPREADSHEETS:\nTurma DE_09 = {_SID}\n"
          'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:F200"\n'
          'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
          'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n')
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Status"]

_TODAY = date(2026, 9, 6)

#: Three classes across two months, inside the horizon. The gémeo of the brief.
_THREE = [
    ["08/09/2026", "Ter", "Ana", "NoSQL and Distributed Databases", "Confirmado"],
    ["30/09/2026", "Qua", "Ana", "Workshop de Abertura", "Confirmado"],
    ["02/10/2026", "Sex", "Ana", "Fundamentals of Data Engineering", "Remarcada"],
]

#: The year as the live sheet holds it: near classes, and a tail running well past the horizon.
_YEAR = _THREE + [
    ["17/05/2027", "Seg", "Ana", "Foundations of Machine Learning", "Confirmado"],
    ["07/06/2027", "Seg", "Ana", "Foundations of Machine Learning", "Confirmado"],
]


def _svc(rows=None, *, today=_TODAY, horizon_days=None):
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria",
              [[""] * 5, [""] * 5, [""] * 5, list(_HEADER)] + [list(r) for r in (rows or _YEAR)])
    return CoordinatorService(store, cfg, today=lambda: today, horizon_days=horizon_days)


def _listing(rows=None, **args) -> str:
    mcp = build_server(_svc(rows))

    async def run():
        res = await mcp.call_tool("get_professor_schedule",
                                  {"role": "SUPERVISOR", "identity_label": "Sofia", **args})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")

    return asyncio.run(run())


# ── GÉMEO 1: three classes over two months → two headers, three lines, IN ORDER ───────
def test_three_classes_over_two_months_render_as_two_headers_and_three_lines():
    out = _listing(_THREE)
    body = [ln for ln in out.splitlines() if ln.strip()]
    # exactly the shape asked for, and the ORDER is the assertion — a set would pass on a
    # listing that put October before September, which is the one thing a calendar may not do.
    assert body[:5] == [
        "*Setembro de 2026*",
        "- 08/09 · Turma DE_09 · NoSQL and Distributed Databases",
        "- 30/09 · Turma DE_09 · Workshop de Abertura",
        "*Outubro de 2026*",
        "- 02/10 · Turma DE_09 · Fundamentals of Data Engineering · Remarcada",
    ]


def test_the_month_header_is_bold_and_in_the_contacts_language():
    # ONE asterisk. WhatsApp's bold is ``*text*``; a DOUBLE pair is not bold there, it is passed
    # through and the contact SEES the asterisks. Nothing in any repo converts markup on the way
    # out, so this string is read byte for byte by a person. ``pay.py``'s ``_H`` says the same.
    assert _month_header(date(2026, 9, 30)) == "*Setembro de 2026*"
    assert _month_header(date(2027, 3, 1)) == "*Março de 2027*"


def test_a_status_prints_only_when_it_is_not_the_ordinary_one():
    out = _listing(_THREE)
    # "Confirmado" is declared ordinary and is spent on two of the three rows — printing it would
    # be a column of every line saying "normal", which is how the row that says something else
    # stops standing out.
    assert "Confirmado" not in out
    assert "· Remarcada" in out


def test_no_repeated_labels_and_no_repeated_year():
    out = _listing(_THREE)
    # the measured flat block: "Turma: X | Data: Y | Disciplina: Z", a label on every field of
    # every row, plus the year repeated under a header that had just said it.
    for label in ("Turma:", "Data:", "Disciplina:", "Professor:", "Status:"):
        assert label not in out, label
    assert "/2026" not in out.replace("de 2026", "")


def test_an_undatable_row_keeps_its_labels_and_goes_last():
    # The read deliberately never hides what it cannot date; a row with no month has no group to
    # sit under, and it is exactly the row whose every column is worth showing.
    rows = _THREE + [["a combinar", "?", "Ana", "Seminário", "Pendente"]]
    body = [ln for ln in _listing(rows).splitlines() if ln.strip()]
    assert body[-1].startswith("- Turma: Turma DE_09 | Data: a combinar")
    assert body[0] == "*Setembro de 2026*"


# ── GÉMEO 2: no period named → ≤30 days, and the continuation is offered ──────────────
def test_no_period_asked_stops_at_thirty_days_and_says_so():
    out = _listing(_YEAR)                      # today = 06/09/2026 → horizon 06/10/2026
    assert "08/09" in out and "30/09" in out   # inside
    assert "02/10" in out                      # inside, and it is the far edge of the window
    assert "17/05" not in out and "07/06" not in out and "2027" not in out
    # the continuation: the argument that widens it, and a BIT — never a count
    assert "next 30 days" in out and "`month`" in out
    assert "33" not in out and "not listed" not in out


def test_naming_a_period_suppresses_the_forward_cut():
    # The horizon answers the question nobody narrowed. A month the contact NAMED is the
    # question, however far out it is, and asking for the past is asking for a window too.
    assert "17/05" in _listing(_YEAR, month="May")
    assert "17/05" in _listing(_YEAR, include_past=True)
    for out in (_listing(_YEAR, month="May"), _listing(_YEAR, include_past=True)):
        assert "next 30 days" not in out


def test_a_discipline_lookup_is_not_narrowed_by_the_horizon():
    # "when is the opening workshop?" must not be answered "nothing" by a default window. This
    # is the incident's own shape reappearing in a new place, and the reason `discipline`
    # suppresses the cut while `turma` does not.
    out = _listing(_YEAR, discipline="Foundations of Machine Learning")
    assert "17/05" in out and "07/06" in out


def test_the_horizon_note_appears_only_when_something_was_actually_cut():
    # the same conditional rule the "today onward" note follows: a permanent note teaches the
    # reader that things are always being withheld, including on the turns where nothing was.
    assert "next 30 days" not in _listing(_THREE)


def test_the_read_records_the_cut_as_a_bit():
    report = ReadReport()
    _svc().get_professor_schedule(role="SUPERVISOR", identity_label="Sofia", report=report)
    assert report.beyond_horizon is True
    near = ReadReport()
    _svc(_THREE).get_professor_schedule(role="SUPERVISOR", identity_label="Sofia", report=near)
    assert near.beyond_horizon is False


def test_the_horizon_is_injectable_and_zero_restores_the_old_window():
    svc = _svc(horizon_days=0)
    got = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia")
    assert "17/05/2027" in [e.date_str for e in got]


# ── the declared tables, mutated by DELETION as well as by violation ──────────────────
def test_every_month_number_has_a_declared_name():
    # Deleting a row from _MONTH_LABELS_PT is the mutation this catches: the month then loses
    # its name and falls back to a number, which is readable but is not what a tenant reads.
    from cogno_praxis.coordinator.server import _MONTH_LABELS_PT
    assert len(_MONTH_LABELS_PT) == 13 and _MONTH_LABELS_PT[0] == ""
    assert len(set(_MONTH_LABELS_PT[1:])) == 12
    for m in range(1, 13):
        assert _month_header(date(2026, m, 1)) == f"*{_MONTH_LABELS_PT[m]} de 2026*"


def test_every_declared_default_status_is_actually_suppressed():
    # Deleting a value from STATUS_DEFAULT_LABELS is the mutation this catches — the table is a
    # DECLARATION, and a declaration nothing exercises is a back door.
    cfg = CoordinatorConfig(_RULES)
    assert cfg.status_default_labels, "the tenant vocabulary must not be empty by default"
    for declared in cfg.status_default_labels:
        rows = [["08/09/2026", "Ter", "Ana", "NoSQL", declared]]
        assert declared not in _listing(rows), declared


def test_a_status_the_tenant_did_not_declare_still_prints():
    rows = [["08/09/2026", "Ter", "Ana", "NoSQL", "Cancelada"]]
    assert "· Cancelada" in _listing(rows)


def test_the_status_column_is_read_by_name_not_by_position():
    e = _svc(_THREE).get_professor_schedule(role="SUPERVISOR", identity_label="Sofia")[0]
    assert _fmt_line(e, defaults=("Confirmado",), status_column="Status").endswith("Databases")
    # a tenant whose sheet has no such column simply gets no status, never a crash or a guess
    assert _fmt_line(e, defaults=("Confirmado",), status_column="Situação").endswith("Databases")
    assert _fmt_line(e, defaults=(), status_column="Status").endswith("· Confirmado")


# ── the marker itself: one asterisk, everywhere, measured on what is PRODUCED ─────────
#
# The sonda that motivated this, made permanent. `_month_header` shipped emitting `**` on the
# premise that WhatsApp renders it; it does not — it renders `*text*` and passes `**text**`
# through unchanged, so the contact SAW the asterisks. Nothing in any repo converts markup on
# the way out, so a renderer's bytes are what a person reads.
#
# Asserted on the OUTPUT rather than by grepping the source, so it needs no exception list: the
# power operator in `bookkeeper/arithmetic.py`'s error message is a `**` nobody wants flagged,
# and a lexical sweep would have to carve it out by name. This one simply never sees it.

def test_no_renderer_in_this_vertical_emits_a_DOUBLE_asterisk():
    """One marker for the whole vertical. Fixing `_month_header` and leaving a sibling behind
    would trade a defect a professor sees every day for one they see some days, which is the
    harder of the two to notice and the harder to report."""
    from cogno_praxis.coordinator.pay import _H

    rendered = [
        _listing(),                                   # the schedule listing, headers and all
        _listing(_THREE),
        _month_header(date(2026, 9, 30)),
        _H.format("Base"),                            # the pay block's own header template
    ]
    for text in rendered:
        assert "**" not in text, f"double asterisk is not bold on WhatsApp: {text[:60]!r}"
        assert "*" in text, "…and the single-asterisk bold must actually be there"


def test_the_unnamed_month_FALLBACK_uses_the_same_single_asterisk(monkeypatch):
    """The branch a real ``date`` can never reach, reached on purpose.

    ``_month_header`` falls back to ``09/2026`` when the label table does not name the month —
    and with a 13-entry table and ``date.month`` in 1..12 that is unreachable, so a mutation
    that restores ``**`` on THAT branch alone survives the whole suite. Measured: it did.
    Unreachable is not the same as correct — the table is one deletion away from being short,
    which is exactly the mutation the test above this file's fixtures already guards — so the
    branch is exercised by shortening the table, the same lever."""
    import cogno_praxis.coordinator.server as srv

    monkeypatch.setattr(srv, "_MONTH_LABELS_PT", ("", "Janeiro"))
    out = srv._month_header(date(2026, 12, 1))

    assert out == "*12/2026*"
    assert "**" not in out


def test_the_two_renderers_of_this_vertical_agree_on_the_marker():
    """`pay.py` was right before this fix and `server.py` was wrong — one package, two
    renderers, one convention. Pinned so the next one to arrive cannot pick a third."""
    from cogno_praxis.coordinator.pay import _H

    assert _H == "*{}*"
    assert _month_header(date(2026, 9, 30)) == "*Setembro de 2026*"
