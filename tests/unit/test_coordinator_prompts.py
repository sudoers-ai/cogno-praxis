"""The COORDINATOR's prompt half — the two promises no code can keep for it.

Everything else in this change is enforced by the vertical: the parser cannot pick a URL slug,
the window cannot return April in September, the refusal cannot arrive labelled ERROR. Two
behaviours have no such lever, because they are about what the assistant SAYS before any tool
runs:

* it must not ask an already-authenticated contact who they are (measured: a professor whose
  identity the system had was answered "poderia me informar qual é o seu M…");
* it must set ``include_past`` only when the past was actually asked for.

A presence assertion is a weak instrument and this file does not pretend otherwise — it pins
that the instruction EXISTS and that no prompt asks for identification. Whether the model obeys
is a live measurement, not a unit test. What it does buy is that a future edit cannot delete the
instruction silently, which is exactly how the first one was never written.

Lives in ``tests/unit/`` because that is the path CI invokes by name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "coordinator" / "prompts"
SLOTS = ("system", "scope", "limits", "voice")


@pytest.mark.parametrize("slot", SLOTS)
def test_every_slot_the_host_loads_exists_and_is_not_empty(slot):
    f = PROMPTS / f"{slot}.txt"
    assert f.exists(), f"the host loads {slot}.txt and an absent one degrades silently"
    assert len(f.read_text(encoding="utf-8").strip()) > 80


@pytest.mark.parametrize("slot", SLOTS)
def test_no_slot_uses_a_placeholder_the_host_does_not_fill(slot):
    """A ``{slot}`` the host has no value for is a KeyError at format time — the whole turn.
    The coordinator persona is rendered with exactly these two."""
    import re
    text = (PROMPTS / f"{slot}.txt").read_text(encoding="utf-8")
    assert set(re.findall(r"\{([a-z_]+)\}", text)) <= {"tenant_name", "identity_label"}


def test_the_executor_is_told_the_contact_is_already_identified():
    system = (PROMPTS / "system.txt").read_text(encoding="utf-8")
    assert "ALREADY IDENTIFIED" in system
    assert "NEVER ask the contact for their name" in system
    # and it is told the seam that makes it possible: an empty `professor` resolves to the caller
    assert "`professor` EMPTY" in system


def test_the_past_is_opt_in_and_the_prompt_says_when():
    system = (PROMPTS / "system.txt").read_text(encoding="utf-8")
    assert "include_past=true" in system
    assert "ONLY when the user explicitly asks about the past" in system
    assert "already\nENDED" in system or "already ENDED" in system.replace("\n", " ")


def test_the_judge_is_told_a_limit_and_an_empty_read_are_correct_answers():
    """The family this persona has already lost turns to: a fail-closed judge reading a truthful
    "I can only show yours" or a truthful "nothing found in your name" as an incomplete goal,
    rejecting it, and exhausting the retry loop into a handoff over a correct reply."""
    limits = (PROMPTS / "limits.txt").read_text(encoding="utf-8")
    assert "COMPLETE and CORRECT" in limits
    assert "não encontrei aulas em nome de" in limits
    assert "TODAY onward" in limits


def test_the_voicer_is_told_a_refusal_is_a_rule_not_a_breakdown():
    voice = (PROMPTS / "voice.txt").read_text(encoding="utf-8")
    assert "não consegui acessar" in voice          # named, as the phrase to NOT produce
    assert "só posso mostrar as suas aulas" in voice
