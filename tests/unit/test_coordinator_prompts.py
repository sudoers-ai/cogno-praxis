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


# ── the calendar export: the half no code can keep ───────────────────────────────────
#
# The vertical enforces everything it can — the tool RAISES on every path that did not send, so
# a refusal can never be stamped as a write, and the recipient is not an argument the model may
# fill. What no code can enforce is the SENTENCE: nothing stops a model from writing "já enviei
# suas aulas" in a turn where the tool answered an error, and a professor who reads that simply
# waits for a calendar that is not coming. These pin that the instruction EXISTS in each of the
# three places that produce or check that sentence — the executor, the judge and the voicer.

def _flat(slot: str) -> str:
    """A prompt with its line WRAPPING removed, so an assertion pins the SENTENCE and not the
    column the sentence happened to be wrapped at. Re-flowing a paragraph is an edit that
    changes nothing and would otherwise turn every check here red."""
    return " ".join((PROMPTS / f"{slot}.txt").read_text(encoding="utf-8").split())


def test_the_executor_is_told_that_only_a_SENT_line_means_an_email_left():
    system = _flat("system")
    assert "send_schedule_to_calendar" in system
    assert 'starts with "SENT:"' in system
    assert "NOTHING was sent" in system
    # named as the phrases to NOT produce, because that is the failure with no visible symptom
    for phrase in ("vou enviar", "estou enviando", "enviei"):
        assert phrase in system, phrase


def test_the_executor_is_told_to_propose_the_send_before_making_it():
    system = _flat("system")
    assert "an e-mail cannot be unsent" in system
    assert "PROPOSE first" in system
    assert "only after an explicit yes" in system
    # the system hold is a BACKSTOP, not permission to call first
    assert "not your excuse to call first" in system


def test_the_judge_is_told_that_a_send_that_did_not_happen_must_be_rejected():
    limits = _flat("limits")
    assert 'answered with a line starting "SENT:"' in limits
    assert "claims a calendar was sent when no SENT: line came back" in limits
    # ...and the other direction: an honest "nothing was sent" is a COMPLETE answer, not a
    # failure to reject. The judge rejecting THAT is how this persona already lost turns.
    assert "COMPLETE and CORRECT answers" in limits


def test_the_voicer_is_told_not_to_announce_a_send_it_did_not_make():
    voice = _flat("voice")
    assert 'ONLY if the tool answered "SENT:"' in voice
    assert 'never "vou enviar" or "enviei" for a send that did not happen' in voice
    assert "never as a system fault" in voice


def test_the_executor_is_told_it_does_not_choose_the_recipient():
    """The rule the code already enforces, said in the prompt too — because a model that
    believes it can pick an address spends the turn asking for one it will never use."""
    system = _flat("system")
    assert "You do NOT choose the recipient" in system
    assert "no argument for it" in system


def test_the_scope_guard_lets_the_request_in_at_all():
    """A capability the intake blocks is a capability nobody can reach."""
    scope = (PROMPTS / "scope.txt").read_text(encoding="utf-8")
    assert "calendar" in scope.lower()


# ── "qual turma é essa?" right after a listing ────────────────────────────────────────
#
# Measured live on the turma matrix (2026-09-06): the persona listed the classes with
# "Turma: ..." on EVERY line, the contact asked «qual turma é essa?», and the reply was
# «poderia me informar a data ou a disciplina…» — asking the contact to look up what the
# assistant itself had just written, in a list both of them could see.
#
# Nothing in code can hold this. There is no tool call to constrain, no argument to validate,
# no output to sanitize: the whole defect is a SENTENCE chosen when the answer was already in
# the previous turn. So these are PRESENCE assertions and nothing more — they pin that the
# instruction exists and that it carries its negative arm, and a future edit cannot delete it
# in silence. Whether the model obeys is a live measurement on the running box; this file's
# own header says the same thing about the two rules above it.

def test_the_executor_is_told_to_read_back_its_own_listing():
    system = _flat("system")
    assert "Never ask for what you just printed" in system
    assert "Qual turma é essa?" in system
    assert "question about YOUR OWN LAST ANSWER" in system
    assert "already on the screen" in system


def test_the_rule_carries_its_NEGATIVE_arm():
    """The twin that keeps the rule from becoming "never ask".

    Without it the instruction is a licence to guess: a contact who opens the conversation with
    «qual turma é essa?» and no listing behind it must still be asked. The rule is about a list
    that EXISTS, and both prompts that carry it say so."""
    system, voice = _flat("system"), _flat("voice")
    assert "If there is genuinely NO previous listing in this conversation, then asking IS right" \
        in system
    assert "Only when no listing was given is a question the right reply." in voice


def test_the_voicer_carries_the_same_rule_because_it_writes_the_sentence():
    voice = _flat("voice")
    assert "ANSWER FROM YOUR OWN LAST REPLY" in voice
    assert "Never ask them for the date or the discipline" in voice


def test_the_judge_reads_a_question_about_a_given_listing_as_INCOMPLETE():
    """The other half: the judge has to be able to reject it. A fail-closed judge with no clause
    for this reads "poderia me informar a data?" as a perfectly reasonable clarification."""
    limits = _flat("limits")
    assert 'A question about a listing ALREADY GIVEN ("qual turma é essa?")' in limits
    assert "is INCOMPLETE, however polite" in limits
    assert "With no previous listing, asking is correct." in limits


# ── the proposal: the three places that produce or check a grounded question ─────────
#
# Measured on a live conversation, 2026-09-06. A professor asked for their September classes to
# be mailed, said yes, and was answered "Confirmo: esta ação — 2026-09. Posso seguir?" — the
# call's own argument, printed at a person. The reason is structural and the code half of it is
# `preview_schedule_to_calendar`: the send is stopped by NAME before it runs, so the skill never
# reads, and a gate cannot ask the skill's question for it. These pin the prompt half — that the
# executor is told to make that read, that the voicer is told to take its numbers from THIS
# turn, and that the judge is told a proposal is a finished answer rather than a half-done send.

def test_the_executor_is_told_to_ground_the_proposal_in_a_read_not_in_memory():
    system = _flat("system")
    assert "preview_schedule_to_calendar" in system
    assert "Do NOT compose that proposal from memory" in system
    # the three facts travel TOGETHER, because a rewrite that re-pairs them can re-pair them wrong
    assert 'on ONE "PROPOSAL:" line' in system
    # ...and WHY the system's own hold cannot stand in for it
    assert "stops the call BEFORE it reads anything" in system


def test_the_voicer_takes_the_proposal_numbers_from_this_turn_not_from_the_history():
    """The measured failure mode of the same conversation: a September request answered with
    October classes, lifted out of a listing given six turns earlier."""
    voice = _flat("voice")
    assert 'put the preview\'s "PROPOSAL:" line to the contact as ONE sentence' in voice
    assert "Never re-assemble them from a listing earlier in the conversation" in voice


def test_the_judge_is_told_a_proposal_is_a_complete_answer():
    """The family this persona has already lost turns to: a fail-closed judge reading a correct
    "here is what would go — may I?" as an incomplete goal and retrying it into a handoff."""
    limits = _flat("limits")
    assert "A PROPOSAL is a COMPLETE and CORRECT answer" in limits
    assert "asking IS the goal of such a turn" in limits


def test_the_executor_is_told_a_bare_yes_is_not_an_answer_to_an_invitation():
    """The one rule the tool cannot enforce for itself, and the reason it is here.

    ``record_class_response`` refuses a call with no date — but it never sees the message, so
    nothing in the vertical can stop the MODEL from supplying a date the contact did not give.
    This house has already measured what that costs on a neighbouring flow: a proposal, one
    unrelated question, then "sim", and the yes belonged to the question in the middle. The
    instruction is the only lever there is, and a presence assertion is what keeps it from being
    deleted silently."""
    system = _flat("system")
    assert "record_class_response(class_date, answer, turma?)" in system
    assert 'A bare "sim" is NOT an answer to this' in system
    assert "Never supply a date the contact did not give in this message" in system
    # the closed field, spelled out, so the model does not pass the contact's own word
    assert "exactly ACCEPTED or DECLINED" in system


def test_the_executor_is_told_that_answering_twice_is_one_answer():
    """The other half of the idempotency, on the side the code cannot reach: the tool reports
    "already recorded", and a model that reads that as a failure retries it into a loop."""
    system = _flat("system")
    assert "Two identical answers are ONE answer" in system
    assert "no change was made and none is needed" in system


def test_the_judge_is_told_an_invitation_left_open_is_a_complete_answer():
    """Same family as the PROPOSAL clause above, and the same measured cost: a fail-closed judge
    reading "I could not tell which class — which one did you mean?" as an unfinished goal, and
    spending the correction budget until the turn ships a handoff over a correct reply."""
    limits = _flat("limits")
    assert "record_class_response" in limits
    assert "an invitation left open is a real answer" in limits
    assert 'was ALREADY recorded ... no change was made' in limits
