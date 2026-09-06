"""The scheduler's ``resolve_date``: its description, its error and its answer are contracts.

There are TWO ``resolve_date`` tools in the ecosystem over the SAME parser: the host's
builtin (``cogno_host.date_tool``), which every non-scheduler persona sees, and this one,
which the SECRETARY uses because a persona whose module ships its own keeps it. On
2026-08-04 the parser gained counted relatives and the host's builtin gained a description
that names them and an error that says what to do — and this one got neither, so the persona
the bench actually measures saw no improvement at all. The bench is what caught it:
``resolve_date``'s failure rate did not move. That was the FIRST time the two texts drifted.

There was a second, found 2026-09-06 while measuring an extraction: **six** differences —
the weekday example ('sexta que vem' vs 'próxima sexta'), the imperative ("NEVER compute"
vs "Always call this"), and four inside the unparseable-phrase error ("from" vs "from:",
"Resolvable forms:" vs "Resolvable:", the ISO example quoted or not, and the one that cost
something: the host's copy omitted ``'depois de amanhã'`` from a list the parser has always
accepted, so half the personas were never told about a working form).

So the words are now defined ONCE, in ``scheduler.service``, beside the parser that has to
honour them — and both shells import them. These tests pin the praxis half: that this
vertical publishes the shared text and adds only its declared tail, that the service's error
and answer ARE the shared functions and not re-typed copies, and that every form the text
names behaves the way it is advertised to, in both directions. The host's half of the twin —
that its builtin publishes byte-for-byte the same core — lives in the host repo, because
that is the only place able to import both.

A tool description is a promise, and it is the only thing a model reads before deciding
whether to call. These assert the promise is kept.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date

import pytest

from cogno_praxis.scheduler import (
    RESOLVE_DATE_DESCRIPTION,
    RESOLVE_DATE_SCHEDULER_SUFFIX,
    SchedulerError,
    SchedulerService,
    build_server,
    resolve_date_answer,
    resolve_date_error,
)
from cogno_praxis.scheduler.store import InMemoryAppointmentStore

_TODAY = date(2026, 6, 30)          # a Tuesday


def _svc() -> SchedulerService:
    return SchedulerService(InMemoryAppointmentStore(), today=lambda: _TODAY)


def _published_description() -> str:
    """The description a MODEL actually receives, read off the rendered MCP tool list.

    It used to be read out of the module SOURCE by regex, matching the docstring, because
    the docstring was what ``mcp.tool`` published. That is precisely how this vertical came
    to hold a second description: the text lived in a docstring nobody compared to anything.
    Reading the rendered schema is the one place that cannot lie — and it keeps the guard
    honest if the publishing mechanism changes again.
    """
    srv = build_server(_svc())
    for tool in asyncio.run(srv.list_tools()):
        if tool.name == "resolve_date":
            return tool.description or ""
    raise AssertionError("resolve_date is not in the rendered tool list")


# ── one source, two shells ───────────────────────────────────────────────────────────────

def test_the_mcp_tool_publishes_the_shared_core_verbatim_plus_its_own_tail():
    """The core is byte-identical to what every other shell publishes; the scheduler-only
    sentence is APPENDED and declared, never woven into the core.

    That split is the design: the tail names ``check_availability`` / ``book_appointment``,
    tools only this vertical has. Folding it into the core would point a BOOKKEEPER or an SDR
    at a tool they were never offered — which is why the two texts could not simply be made
    identical and left at that."""
    published = _published_description()
    assert published == RESOLVE_DATE_DESCRIPTION + RESOLVE_DATE_SCHEDULER_SUFFIX
    assert "check_availability" not in RESOLVE_DATE_DESCRIPTION, (
        "a scheduler-only tool name leaked into the SHARED core — every persona reads this")


def test_the_tool_has_no_docstring_left_to_drift_from():
    """The docstring WAS the second copy. FastMCP prefers ``description=`` but falls back to
    ``__doc__``, so a docstring re-added here would sit one edit away from being published
    again the day someone drops the parameter. There must be nothing to fall back to."""
    import inspect

    from cogno_praxis.scheduler import server

    src = inspect.getsource(server)
    body = src.split("def resolve_date(expression: str) -> str:", 1)[1]
    head = body.split("iso = svc.resolve_date", 1)[0]
    assert '"""' not in head, (
        "resolve_date grew a docstring again — that is the second description coming back")


def test_the_service_error_is_the_shared_text_not_a_local_copy():
    """The unparseable-phrase message the MCP tool propagates IS ``resolve_date_error``.

    Pinned by identity, not by keyword: an ``in`` check stays green while a second copy
    drifts around the words it happens to sample — which is exactly how "from" became
    "from:" and "Resolvable forms:" became "Resolvable:" without anything going red."""
    with pytest.raises(SchedulerError) as exc:
        _svc().resolve_date("semana que vem")
    assert str(exc.value) == resolve_date_error("semana que vem")


def test_the_success_payload_is_the_shared_text_and_carries_the_spoken_form():
    """The ISO date AND the words for it — the model must never name a weekday itself.

    The live incident behind this: a persona read the anchor "2026-07-25 (Saturday)" and
    still voiced "sexta-feira". Handing it the words removes the arithmetic. Asserted on the
    RENDERED tool output against the shared function, not by grepping the source for a
    literal, so a re-typed copy fails instead of passing on a substring."""
    out = str(asyncio.run(build_server(_svc()).call_tool(
        "resolve_date", {"expression": "amanhã"})))
    assert resolve_date_answer("2026-07-01", "quarta-feira, 1 de julho de 2026") in out


def test_both_shells_CALL_the_shared_text_rather_than_holding_a_copy():
    """The output guards above compare TEXT, and text comparison cannot see a copy that has
    not drifted yet — a byte-identical re-type passes every one of them, then drifts next
    week. Measured: re-typing the success answer inline defeated the whole file.

    So this asserts the STRUCTURE the other tests assume: each shell calls the shared
    function. That is the property "one source" actually names; sameness of output is only
    its symptom today."""
    import inspect

    from cogno_praxis.scheduler import server, service

    srv_src = inspect.getsource(server)
    tool = srv_src.split("def resolve_date(expression: str) -> str:", 1)[1].split("\n    @", 1)[0]
    assert "resolve_date_answer(" in tool, (
        "the MCP tool stopped calling resolve_date_answer — an inline copy of the answer is "
        "how the two shells drifted the first time")
    assert "format_date" in tool, (
        "the tool no longer renders the spoken form — a model handed only an ISO date goes "
        "back to computing the weekday, which is the failure this exists to prevent")

    parser = inspect.getsource(service.SchedulerService.resolve_date)
    assert "resolve_date_error(" in parser, (
        "the parser stopped calling resolve_date_error — an inline copy of the error is how "
        "'from' became 'from:' and 'Resolvable forms:' became 'Resolvable:'")


# ── every promise in the text is kept ────────────────────────────────────────────────────

def test_every_form_the_description_promises_actually_resolves():
    """Run each quoted example through the parser.

    Split on the span warning rather than skip-listing the spans: a skip-list fails open —
    move a span into the promise half and it stays green because the name is on the list
    either way."""
    promise, sep, _warning = _published_description().partition("A vague SPAN")
    assert sep, "the description lost its span warning — the split below is meaningless"

    svc = _svc()
    promised = re.findall(r"'([^']+)'", promise)
    assert len(promised) >= 9, f"the description stopped naming its forms: {promised}"
    for form in promised:
        try:
            svc.resolve_date(form)
        except SchedulerError as exc:                       # pragma: no cover - failure path
            pytest.fail(f"the tool advertises {form!r} but the parser rejects it: {exc}")


def test_every_form_the_description_warns_against_really_fails():
    """The warning must not be a lie in the other direction either."""
    svc = _svc()
    _, _, warning = _published_description().partition("A vague SPAN")
    warned = re.findall(r"'([^']+)'", warning)
    assert warned, "the span warning names no example"
    for form in warned:
        with pytest.raises(SchedulerError):
            svc.resolve_date(form)


def test_every_form_the_error_lists_actually_resolves():
    """The error text is a SECOND promise — it tells a stuck model what will work. The
    host's copy listed forms its own sentence never verified; this one is verified."""
    svc = _svc()
    listed = re.findall(r"'([^']+)'",
                        resolve_date_error("xyzzy").split("Resolvable forms:")[1])
    assert len(listed) >= 8, f"the error stopped listing forms: {listed}"
    for form in listed:
        svc.resolve_date(form)          # 'sexta' is named as "a weekday ('sexta')"


def test_the_error_lists_depois_de_amanha_the_form_the_host_copy_had_dropped():
    """The one drift with a user-visible cost, pinned by name.

    Two copies of this list existed; only praxis's named ``depois de amanhã``. The parser has
    always accepted it, so every persona on the host's copy was told a working form did not
    exist. If this regresses it will be because someone re-typed the list instead of
    importing it."""
    assert "'depois de amanhã'" in resolve_date_error("x")
    assert _svc().resolve_date("depois de amanhã") == "2026-07-02"


def test_the_error_tells_the_model_what_to_do():
    """This message is read by a MODEL: the MCP tool lets it propagate as the tool's error.

    'could not resolve' alone left it rewording the same unresolvable phrase and burning a
    second step on the identical failure."""
    with pytest.raises(SchedulerError) as exc:
        _svc().resolve_date("essa semana")
    msg = str(exc.value).lower()
    assert "ask the user" in msg
    assert "do not call this again" in msg
    assert "daqui a 3 dias" in msg          # names a form that DOES work, not only the failure
    assert "essa semana" in msg             # quotes back the phrase it choked on


def test_the_description_forbids_the_model_computing_dates_itself():
    """The anti-fabrication imperative is the reason this tool exists — a persona that reads
    the anchor and derives the weekday itself is the live incident. Both copies carried one;
    they were different sentences ("NEVER compute" vs "Always call this"). This is the one."""
    assert "NEVER compute or guess" in RESOLVE_DATE_DESCRIPTION


def test_the_answer_hands_over_both_the_iso_date_and_the_words():
    """Both halves, or the model derives the missing one — the failure this seam removes."""
    out = resolve_date_answer("2026-07-25", "sábado, 25 de julho de 2026")
    assert "2026-07-25" in out and "sábado, 25 de julho de 2026" in out
    assert "ISO date in tool calls" in out and "speaking to the user" in out


def test_the_spoken_form_never_uses_the_server_locale():
    """Names by index, never strftime/%A: %A follows the SERVER locale, and an English
    weekday is exactly what got mistranslated into the wrong day."""
    from cogno_praxis.scheduler.service import format_date

    d = date(2026, 7, 25)                        # a Saturday
    assert format_date(d, "pt") == "sábado, 25 de julho de 2026"
    assert format_date(d, "en") == "Saturday, July 25, 2026"
    assert format_date(d, "es") == "sábado, 25 de julio de 2026"
    assert format_date(d, "pt-BR") == format_date(d, "pt")      # region suffix tolerated
    assert format_date(d, "xx") == format_date(d, "pt")         # unknown falls back
    # and the rendering must not go through strftime at all — %A/%B follow the SERVER
    # locale. (Grepping for "%A" alone would match the comment that says not to use it.)
    import inspect

    from cogno_praxis.scheduler import service
    src = inspect.getsource(service)
    assert "strftime(" not in src, "strftime is locale-dependent; render by index"
