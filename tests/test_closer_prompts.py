"""The CLOSER's prompt slots — the persona is prompts only, so the file layout IS the contract.

The host loads exactly `{system,scope,limits,voice}.txt` from the package's prompts dir and a
MISSING slot does not raise: it loads as an empty string and the persona quietly runs without
its judge criteria or its voice. So the presence and the shape are worth asserting."""

from __future__ import annotations

from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "closer" / "prompts"
SLOTS = ("system", "scope", "limits", "voice")


@pytest.mark.parametrize("slot", SLOTS)
def test_every_slot_the_host_loads_exists_and_is_not_empty(slot):
    f = PROMPTS / f"{slot}.txt"
    assert f.exists(), f"the host loads {slot}.txt and an absent one degrades silently"
    assert len(f.read_text().strip()) > 80


def test_the_arc_is_ordered_and_the_diagnosis_comes_before_the_pitch():
    system = (PROMPTS / "system.txt").read_text()
    for step in ("1. ABERTURA", "2. DIAGNÓSTICO", "3. DEVOLUTIVA", "4. ENCAIXE", "5. FECHAMENTO"):
        assert step in system
    # the one rule the whole persona rests on
    assert "NUNCA venda antes do passo 3" in system


def test_the_judge_can_approve_a_conversational_turn():
    """The default judge criterion is goal-vs-EXECUTION ("asked X, did X"). A consultative turn
    executes nothing, so without this escape hatch every good reply is rejected and the loop
    burns its retries — the same trap the BOOKKEEPER's limits.txt documents."""
    limits = (PROMPTS / "limits.txt").read_text()
    assert "NÃO exija que uma ação tenha sido realizada" in limits.replace("\n", " ")


def test_the_honesty_rules_are_present_because_they_are_what_make_it_credible():
    system = (PROMPTS / "system.txt").read_text()
    assert "NUNCA invente" in system
    assert "diga isso na cara e não force" in system      # walk away when it does not fit
    assert "responda a verdade" in system                 # "are you an AI?"
