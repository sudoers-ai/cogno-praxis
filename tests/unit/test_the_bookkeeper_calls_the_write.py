"""The bookkeeper CALLS the write and lets the system ask — and a question records nothing.

The defect is the double confirmation. The bookkeeper's prompt used to say "present a summary,
ask the user to confirm, and call add_income/add_outcome ONLY after an explicit affirmative",
and its two tool descriptions said "Confirm the summary with the user BEFORE calling this". A
host that holds every write until the user agrees (the reference host does) then asked TWICE:
the executor asked in prose on the first turn, holding nothing; the "sim" made it call; the
system held that call and asked again. Measured on a reference bench: the first turn of
`record_income` / `record_outcome` held the write in 4 of 15 runs, and the executor's own draft
said the entry "ainda aguarda sua confirmação". The scheduler has carried the opposite
convention since 2026-07-04 — "Confirmation is the SYSTEM's job — CALL the tool, never negotiate
it in prose" — and its writes were held on the first turn in 21 of 24 runs of the same bench.

This file pins the convention, the same words as the scheduler's, and the three things it must
NOT turn into a call. Those come FIRST, as the cases below, written before the prompt changed:

* a QUESTION about an entry ("quanto ficaria se eu lançasse…?", "posso lançar depois?") is not
  an entry. The rule that says "call it" must say, beside it, that a question is answered and
  calls no write tool;
* a MISSING detail is asked for, not guessed — a legitimate question is not the defect;
* a polite request ("será que dá para lançar…?") is a request, and may be held; it is never
  committed, because the hold is the system's and only a "sim" releases it.

What this file cannot measure is what a MODEL does with the text: that is a bench run over the
same phrases, before and after, and it is outside a unit suite on purpose. What it does pin is
that the text a model reads states each rule, and that the old instruction — the one that
produced the double question — is gone from the prompt AND from the two descriptions, so the
executor is not told two opposite things.

`remove_by_search` is deliberately untouched. Its first call already RUNS (it reads and
proposes; gate C holds it), so its double question has another cause — the query it is given —
and changing its text here would mix two fixes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cogno_praxis.bookkeeper.server import build_server

_PROMPTS = Path(__file__).resolve().parents[2] / "cogno_praxis"
_SYSTEM = (_PROMPTS / "bookkeeper" / "prompts" / "system.txt").read_text(encoding="utf-8")
_SCHEDULER = (_PROMPTS / "scheduler" / "prompts" / "system.txt").read_text(encoding="utf-8")

#: The scheduler's header, the convention this persona is brought to — the SAME words.
_CONVENTION = "## Confirmation is the SYSTEM's job — CALL the tool, never negotiate it in prose"

# ── the cases, written BEFORE the prompt changed ────────────────────────────────────────────
# (message, class). Portuguese: they are the contact's input under test. The names are invented.
# The same phrases are the bench scenarios a model run measures; here each CLASS must have a
# rule in the prompt that decides it.
QUESTION = "question"      # asks about an entry, records nothing  → answer; call no write tool
MISSING = "missing"        # an entry with a detail missing        → ask for THAT detail
REQUEST = "request"        # a polite request                      → may be held, never committed

CASES: "list[tuple[str, str]]" = [
    ("quanto ficaria meu saldo se eu lançasse 200 reais de entrada?", QUESTION),
    ("posso lançar essa despesa depois?", QUESTION),
    ("compensa lançar o aluguel como despesa ou não?", QUESTION),
    ("se eu registrar 80 de luz hoje, entra no mês de outubro?", QUESTION),
    ("recebi do Otávio Quelme pelo corte", MISSING),
    ("paguei a conta de luz", MISSING),
    ("será que dá para lançar 150 do Otávio Quelme?", REQUEST),
]

#: The sentence of the prompt that decides each class. A class with no rule is a case the new
#: convention would turn into a call by default.
_RULE_FOR = {
    QUESTION: "answer the question; call no write tool",
    MISSING: "ask for THAT detail and call nothing yet",
    REQUEST: "The SYSTEM holds the call",
}


def _section(text: str, header: str) -> str:
    start = text.index(header)
    nxt = text.find("\n## ", start + len(header))
    return text[start:] if nxt < 0 else text[start:nxt]


def _flat(text: str) -> str:
    """One line: the prompt is wrapped prose, and a phrase across a newline is one phrase."""
    return " ".join(text.split())


def test_the_cases_cover_every_class():
    """The table is the guard's input — a class with no case is a rule nobody checks."""
    assert {c for _, c in CASES} == set(_RULE_FOR)


def test_the_bookkeeper_carries_the_schedulers_convention():
    assert _CONVENTION in _SCHEDULER, "the molde moved — re-read it before copying it"
    assert _CONVENTION in _SYSTEM


def test_the_convention_names_the_two_writes_and_forbids_the_prose_question():
    rule = _flat(_section(_SYSTEM, _CONVENTION))
    assert "CALL add_income/add_outcome" in rule
    assert "do NOT write" in rule and "confirmation question" in rule
    assert "say yes twice" in rule


@pytest.mark.parametrize("message,klass", CASES,
                         ids=[f"{k}-{i}" for i, (_, k) in enumerate(CASES)])
def test_each_case_has_its_rule(message, klass):
    rule = _flat(_section(_SYSTEM, _CONVENTION))
    assert _RULE_FOR[klass] in rule, f"{klass!r} ({message!r}) has no rule in the convention"


def test_the_instruction_that_asked_twice_is_gone():
    flat = _flat(_SYSTEM)
    assert "ONLY after an explicit affirmative" not in flat
    assert "## Confirmation Before Recording" not in flat


async def test_the_two_descriptions_do_not_say_the_opposite():
    """The description reaches the executor beside the prompt; "confirm BEFORE calling" there
    would be the old instruction, one line from the new one."""
    tools = {t.name: t for t in await build_server().list_tools()}
    for name in ("add_income", "add_outcome"):
        text = _flat(tools[name].description or "")
        assert "BEFORE calling" not in text, name
        assert "The system holds the call" in text, name


def test_the_removal_paragraph_did_not_move():
    """Out of scope on purpose (see the module docstring): the removal text is byte for byte."""
    assert ("remove_by_search is destructive, and the system holds it AFTER the first call, on "
            "the entry that\ncall read") in _SYSTEM


async def test_the_presupposition_is_a_host_that_holds_every_write():
    """What "the SYSTEM holds the call" rests on, said where a reader of this lib can see it.

    The two writes are MUTATING and not destructive: cogno-mcp reports `is_mutating=True` and
    `requires_confirmation=False` for both. So THIS library does not hold them — a host does,
    by holding every write until the user agrees (the reference host's write policy). A host
    without that gate must add its own confirmation instruction: telling a model to CALL a write
    nobody holds is telling it to record without asking. `docs/BOOKKEEPER.md` says so."""
    pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")
    from cogno_mcp import MCPDispatcher

    d = MCPDispatcher(None, await build_server().list_tools())
    for name in ("add_income", "add_outcome"):
        assert d.is_mutating(name) is True, name
        assert d.requires_confirmation(name) is False, name
    doc = _flat((_PROMPTS.parent / "docs" / "BOOKKEEPER.md").read_text(encoding="utf-8"))
    assert "presumes a host that holds every write" in doc
