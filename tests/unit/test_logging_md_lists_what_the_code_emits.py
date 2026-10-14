"""``LOGGING.md`` lists the log events this package emits — the code's list, both ways.

The page was a reading of ``grep`` "on the day it was written", and it said so. It described
the coordinator's lines as "plain sentences prefixed ``coordinator:``, with no ``event=`` key",
and it had to carry a warning of its own: one WARNING held two professors' names and four held
a spreadsheet's id. Measured on ``5e7a452`` with the reader this file uses: 19 log calls, 15 of
them with no event name, 12 of them carrying somebody's text or an identifier.

So the table in ``LOGGING.md`` is held to the code, in both directions:

* every log call of the package has a row — logger, event, level, the ``key=`` fields of its
  message and whether it carries a traceback;
* every row is a call the package still makes.

The events are read from the source by AST (``tests/unit/_log_calls.py``), never listed here, so
a new call fails this file until the page says what it is. The same goes for the modules that
log nothing and for what the "Level policy" section says about each level. What a VALUE may be
is the other file's: ``test_logs_carry_no_third_party_text.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import cogno_praxis
from tests.unit import _log_calls as reader

PACKAGE = Path(cogno_praxis.__file__).parent
DOC = PACKAGE.parent / "LOGGING.md"

Row = "tuple[str, str, str, frozenset[str], bool]"


def documented(text: str) -> "list[Row]":
    """The five facts of every row of the events table. A row is
    ``| `logger` | `event` (fields) | LEVEL | when |``; a pipe inside a cell is written ``\\|``.
    The fields are the backticked names in the event cell after the event (``key`` or
    ``key=…``); "traceback" in the level cell is the mark of a line that carries one."""
    out = []
    for line in text.splitlines():
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())]
        if len(cells) != 6 or cells[0] or cells[-1]:
            continue
        logger = re.fullmatch(r"`(cogno_praxis[\w.]*)`", cells[1])
        event = re.match(r"`(\w+)`", cells[2])
        level = re.match(r"([A-Z]+)\b", cells[3])
        if not (logger and event and level):
            continue
        fields = frozenset(re.findall(r"`(\w+)(?:=[^`]*)?`", cells[2][event.end():]))
        out.append((logger.group(1), event.group(1), level.group(1), fields,
                    "traceback" in cells[3]))
    return out


CALLS, STRANGERS = reader.package_calls(PACKAGE)
CODE = [call.row for call in CALLS]
TEXT = DOC.read_text(encoding="utf-8")
PAGE = documented(TEXT)


# ── the two directions ─────────────────────────────────────────────────────────────────────

def test_every_event_the_code_emits_has_a_row():
    missing = sorted(set(CODE) - set(PAGE), key=str)
    assert not missing, f"emitted and not on the page (or not as the page says): {missing}"


def test_every_row_is_an_event_the_code_still_emits():
    stale = sorted(set(PAGE) - set(CODE), key=str)
    assert not stale, f"on the page and not emitted (or not as the page says): {stale}"


def test_no_row_appears_twice():
    """One row per (logger, event, level, fields, traceback). Two calls that share all five
    share a row (``smtp_env_ignored`` is two calls, told apart by a literal ``reason=``)."""
    assert len(PAGE) == len(set(PAGE)), "a row appears twice"
    assert {(row[0], row[1]) for row in PAGE} == {(row[0], row[1]) for row in CODE}


# ── the controls: the readers can see what they look for ───────────────────────────────────

def test_control_the_code_reader_finds_the_calls_known_today():
    """A reader that found nothing would agree with an empty page. The count is a floor, not a
    pin; the three loggers named are the three VARIABLE names the package uses (``_log``,
    ``log``, ``logger``), so a reader that knew one spelling would be missing two of them."""
    assert not STRANGERS
    assert len(CALLS) >= 16
    events = {(row[0], row[1], row[2]) for row in CODE}
    assert {("cogno_praxis.coordinator.service", "sheet_unreadable", "WARNING"),
            ("cogno_praxis.scheduler.engine", "holidays_unavailable", "WARNING"),
            ("cogno_praxis.scheduler.stores.postgres", "slot_uniqueness_built_concurrently",
             "DEBUG"),
            ("cogno_praxis.coordinator.mailer", "herald_not_installed", "INFO")} <= events


def test_control_a_planted_call_is_read_and_a_planted_row_is_read():
    planted = ('import logging\n'
               '_odd_name = logging.getLogger("cogno_praxis.x")\n'
               'def f():\n'
               '    _odd_name.warning("stage=x event=made_up reason=%s attempt=%d — and so on",\n'
               '                      1, 2, exc_info=True)\n')
    calls, strangers = reader.read(planted, "cogno_praxis.x")
    assert not strangers
    assert [c.row for c in calls] == [
        ("cogno_praxis.x", "made_up", "WARNING", frozenset({"reason", "attempt"}), True)]
    row = ("| `cogno_praxis.x` | `made_up` (`reason=a\\|b`, `attempt`) "
           "| WARNING, with a traceback | never |")
    assert documented(row) == [c.row for c in calls]


@pytest.mark.parametrize("line, why", [
    ('logger.info(some_variable)', "not a string literal"),
    ('logger.info("coordinator: %r could not be read", "k")', "without event="),
    ('logger.info("event=x failed (%s)", "e")', "is not key=value"),
    ('logger.info("event=x a=%s", 1, 2)', "argument(s) for"),
    ('logger.info("event=x a=1 — tail=%r", "t")', "in the prose"),
    ('logger.info("event=x a=%s", 1, extra={"k": 1})', "keyword(s)"),
    ('logger.log(30, "event=x")', "hides the level"),
    ('logging.warning("event=x")', "not on a module-level logger"),
    ('logging.getLogger("y").warning("event=x")', "not on a module-level logger"),
])
def test_control_a_call_the_reader_cannot_name_is_refused(line, why):
    """Each of these is a shape this package had, or a shape that would leave the reader
    agreeing with a page about a call it never saw."""
    source = f"import logging\nlogger = logging.getLogger(__name__)\n{line}\n"
    with pytest.raises(reader.LogGrammarError, match=re.escape(why)):
        reader.read(source, "cogno_praxis.x")


def test_control_a_level_call_on_something_else_is_a_stranger():
    calls, strangers = reader.read("def f(parser):\n    parser.error('usage')\n", "cogno_praxis.x")
    assert calls == [] and strangers == ["cogno_praxis.x:2 parser.error"]


def test_control_the_comparison_fails_on_the_page_as_it_was():
    """The coordinator's table as it was on ``5e7a452``, read by the same reader: its rows have
    no logger and no event, so every event the code emits is missing."""
    old = ("| level | where | means | carries |\n|---|---|---|---|\n"
           "| WARNING | `service` | a spreadsheet, its hours tab, its IBOPE tab or its "
           "professors tab could not be read | the sheet's KEY, **its id**, and the exception |\n"
           "| WARNING | `mailer` | the calendar mail was not accepted by the server | nothing |\n")
    assert documented(old) == []
    assert len(set(CODE) - set(documented(old))) == len(set(CODE)) >= 15


# ── the lists beside the table ─────────────────────────────────────────────────────────────

def _section(title: str) -> str:
    start = TEXT.index(f"## {title}")
    end = TEXT.find("\n## ", start + 1)
    return TEXT[start:end if end > 0 else len(TEXT)]


def test_the_modules_that_log_nothing_are_the_modules_that_log_nothing():
    modules = set(reader.modules(PACKAGE))
    loud = {call.module for call in CALLS}
    listed = set(re.findall(r"`(cogno_praxis[\w.]*)`", _section("Modules that log nothing")))
    assert listed == modules - loud


@pytest.mark.parametrize("level", ["ERROR", "WARNING", "INFO", "DEBUG"])
def test_the_level_policy_says_how_many_calls_each_level_has(level):
    """Each level has one bullet. It says "never emitted" exactly when no call of the package
    is at that level, and otherwise how many calls are."""
    bullets = [ln for ln in _section("Level policy").splitlines()
               if ln.startswith(f"- **{level}**")]
    assert len(bullets) == 1, level
    count = sum(1 for call in CALLS if call.level == level)
    assert ("never emitted" in bullets[0]) == (count == 0), bullets[0]
    if count:
        said = re.search(r"— (\d+) calls?\b", bullets[0])
        assert said and int(said.group(1)) == count, (bullets[0], count)


def test_no_call_is_at_a_level_the_policy_does_not_name():
    assert {call.level for call in CALLS} <= {"WARNING", "INFO", "DEBUG"}


def test_the_stage_of_a_line_is_the_vertical_of_its_logger():
    """``stage=`` is not a field of the table, so it is held here: every line says the vertical
    its logger belongs to."""
    assert CALLS
    for call in CALLS:
        assert call.stage == call.logger.split(".")[1], call
    assert {call.stage for call in CALLS} == {"coordinator", "scheduler"}
