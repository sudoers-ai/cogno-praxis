"""The scheduler's ``resolve_date`` tool: its description and its error text are contracts.

There are TWO `resolve_date` tools in the ecosystem over the SAME parser: the host's builtin
(`cogno_host.date_tool`) and this one, which the SECRETARY uses because a persona whose
module ships its own keeps it. On 2026-08-04 the parser gained counted relatives and the
host's builtin gained a description that names them and an error that says what to do — and
this one got neither, so the persona the bench actually measures saw no improvement at all.
The bench is what caught it: `resolve_date`'s failure rate did not move.

A tool description is a promise. These assert that this one's promise is kept, and that its
error teaches rather than just reporting.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from cogno_praxis.scheduler.service import SchedulerError, SchedulerService
from cogno_praxis.scheduler.store import InMemoryAppointmentStore

_TODAY = date(2026, 6, 30)          # a Tuesday


def _svc() -> SchedulerService:
    return SchedulerService(InMemoryAppointmentStore(), today=lambda: _TODAY)


def _tool_doc() -> str:
    """The `resolve_date` docstring the model is shown, read off the MCP server source.

    Reading the source rather than building an MCP server keeps this a unit test; the
    docstring IS what `mcp.tool` publishes.
    """
    import inspect

    from cogno_praxis.scheduler import server

    src = inspect.getsource(server)
    m = re.search(r'def resolve_date\(expression: str\) -> str:\n\s*"""(?P<doc>.*?)"""',
                  src, re.S)
    assert m, "resolve_date's docstring moved — this guard reads it by shape"
    return m.group("doc")


def test_every_form_the_description_promises_actually_resolves():
    doc = _tool_doc()
    promise, sep, warning = doc.partition("A vague SPAN")
    assert sep, "the docstring lost its span warning — the split below is meaningless"

    svc = _svc()
    for form in re.findall(r"'([^']+)'", promise):
        try:
            svc.resolve_date(form)
        except SchedulerError as exc:                       # pragma: no cover - failure path
            pytest.fail(f"the tool advertises {form!r} but the parser rejects it: {exc}")


def test_every_form_the_description_warns_against_really_fails():
    """The warning must not be a lie in the other direction either."""
    svc = _svc()
    _, _, warning = _tool_doc().partition("A vague SPAN")
    for form in re.findall(r"'([^']+)'", warning):
        with pytest.raises(SchedulerError):
            svc.resolve_date(form)


def test_the_error_tells_the_model_what_to_do():
    """This message is read by a MODEL: the MCP tool lets it propagate as the tool's error.

    'could not resolve' alone left it rewording the same unresolvable phrase and burning a
    second step on the identical failure.
    """
    with pytest.raises(SchedulerError) as exc:
        _svc().resolve_date("essa semana")
    msg = str(exc.value).lower()
    assert "ask the user" in msg
    assert "do not call this again" in msg
    assert "daqui a 3 dias" in msg          # names a form that DOES work, not only the failure
