"""A message to the team — composed, rewritten or corrected — is IN SCOPE wherever the tool is offered.

## The defect

On a SECRETARY turn, a staff member declined a message the assistant had proposed to a colleague
and asked for a better one. The relevance guard BLOCKED it 5/5. That held for the crude wording
and for the CLEAN one, both with the specific pending request in the prompt (host #1145). The
same clean sentence on a COORDINATOR turn: ALLOW 5/5. So it was neither the tone nor the pending
request. It was the SCOPE. The scheduler's definition lists scheduling, appointments, the agenda,
the directory, reception and triage, and nothing about writing to a colleague. The notification
tool (``notify_user``) was on the table all the same.

The guard prompt already says that a request another capability offered on this turn serves is
in scope. It did not carry this request. The lever is the DEFINITION, the same lesson as the
bookkeeper's assets sentence (C3, #153).

## The repair

ONE line, ``LINE`` below, word for word as the measurement proposed it, in the IN SCOPE part of
every vertical whose persona is offered ``notify_user``. The host's catalog makes it a system
skill for staff, and probing the host's production surface per persona and role puts it on the
table of the SECRETARY (``scheduler``), the BOOKKEEPER, the COORDINATOR and the INTERVIEWER, for
SUPERVISOR and EMPLOYEE alike; never for a GUEST, and never for the CLOSER. None of the four
definitions covers it in its text. Three take the line:

* ``scheduler`` — as a bullet at the end of its ``IN SCOPE (ALLOW):`` list;
* ``bookkeeper``, ``interviewer`` — their definitions are prose with no list, so the same bullet
  goes under an ``Also allow:`` lead, as its own paragraph right before the BLOCK paragraph (the
  interviewer's lead is English like the line; the file is Portuguese).

Not given the line:
* ``coordinator`` — a MEASURED prompt that already answers this request ALLOW 5/5 (the same clean
  sentence with the pending request). A measured file is not changed for consistency without a
  measurement that asks for it (Director, 2026-10-01);
* ``closer`` — no tools, so its guard is skipped and the tool is never offered;
* ``companies`` — a CONTRIBUTION to a SECRETARY's guard that "speaks only for those records". The
  SECRETARY's base (``scheduler``) carries the line for her.

## What this file pins, and what it does not

Assertions about the PROMPT only. Whether the guard obeys is measured outside this repo, against
the served guard. Here:

* the TWIN — each of the three carries the bullet once, in the part of the file that ALLOWS;
* the CONTROL — take the insertion out and each file is, byte for byte, the file at
  ``origin/main`` 5c57490 (digests pinned), and the new digests are pinned as well;
* the NEIGHBOURS — ``coordinator``, ``closer`` and ``companies`` do not carry the line and did
  not move.

The pinned digests are a LANDING proof, made to age: a deliberate edit of one of those files is
regenerated in the SAME PR that changed it, never edited to silence a red.

MUTATIONS:
    remove the bullet (and, in prose files, its ``Also allow:`` paragraph) from
    ``scheduler/prompts/scope.txt``
    → ``test_the_line_is_in_the_allow_part[scheduler]`` dies; the control dies at its
      PRECONDITION (it refuses the file without the insertion, which IS main's file).
    move the scheduler's bullet into its ``OUT OF SCOPE (BLOCK):`` list
    → ``test_the_line_is_in_the_allow_part[scheduler]`` dies; the bullet is still in the file.
    give the line to ``coordinator/prompts/scope.txt`` too
    → ``test_the_neighbours_did_not_move[coordinator]`` dies.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

#: The package the HOST reads the prompts from — the installed package, never a path relative to
#: this checkout, so the file under test is the one a host would load.
PKG = Path(__import__("cogno_praxis").__file__).resolve().parent

#: The line, word for word as measured.
LINE = ("Messages to the team: composing, rewriting or sending a message/notification to a staff "
        "member — including the user's corrections to a message just proposed or declined.")

#: As it sits in every file: a bullet.
BULLET = "- " + LINE

#: The lead of the paragraph that carries the bullet in a prose definition.
LEAD = "Also allow:\n"

#: What was inserted in each file, and the text it was inserted BEFORE (each counted to one).
INSERTS = {
    "scheduler": (BULLET + "\n", "\nOUT OF SCOPE (BLOCK):"),
    "bookkeeper": (LEAD + BULLET + "\n\n", "Block ONLY messages that are abusive"),
    "interviewer": (LEAD + BULLET + "\n\n", "BLOQUEIE apenas mensagens abusivas"),
}

#: ``sha256`` of each file at ``origin/main`` 5c57490, before the line.
AT_MAIN = {
    "bookkeeper": "038237d093ebeba38af3fc3f5c777882c59bad5b6eddb6b9bf6c89f5483db063",
    "interviewer": "d80bcb9076c17f2c9cf87776cd1212316801a6f5677f64027509aeed06748b8c",
    "scheduler": "633c8edf7cdb568137e31a6b2b64be1746231b16932b157605d43ee99f1ff7eb",
}

#: ``sha256`` of each file WITH the line.
NOW = {
    "bookkeeper": "ed4a8c112f11d2c2bf480c4e8be806f9d1f707e12c1bf638e541e5f17f3ee342",
    "interviewer": "b25231522c0c48c4658bbf5e1824cf9bc3fc544ecf02b0d09a2b0df1e815a921",
    "scheduler": "b2f942c84374955d9aad03f951ce4082d4cc4d0c45638cad4d1c6b9f89b3448f",
}

#: The scopes NOT given the line, at ``origin/main`` 5c57490.
NEIGHBOURS_AT_MAIN = {
    "closer": "92c91dc45dbf3e7538b20f697e38ff99e8b3c69ba4f17d3bcb5b1dce746f3714",
    "companies": "c410e899125d712a7e5cbc9880627febca04e497a61059af9650ab236f00c805",
    "coordinator": "7a03422e0991306317e48df84a8fcd796c9eb507e5c7b4e0291fa8c401d7264b",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scope(vertical: str) -> str:
    return (PKG / vertical / "prompts" / "scope.txt").read_text(encoding="utf-8")


def without_the_team_line(vertical: str, text: str) -> str:
    """The file as it was before the line. Other files' controls call this before measuring
    THEIR own sentence; a vertical that never took the line is returned untouched."""
    if vertical not in INSERTS:
        return text
    inserted, before = INSERTS[vertical]
    return text.replace(inserted + before, before, 1)


def _allow_part(vertical: str, text: str) -> str:
    """The part of the file that ALLOWS. The scheduler has a list with a header, from
    ``IN SCOPE (ALLOW):`` to ``OUT OF SCOPE (BLOCK):``. The prose files have paragraphs: the one
    that opens with the lead."""
    if vertical == "scheduler":
        assert text.count("IN SCOPE (ALLOW):") == 1 and text.count("OUT OF SCOPE (BLOCK):") == 1
        return text.split("IN SCOPE (ALLOW):", 1)[1].split("OUT OF SCOPE (BLOCK):", 1)[0]
    leads = [p for p in text.split("\n\n") if p.startswith(LEAD)]
    assert len(leads) == 1, f"{vertical}: the {LEAD!r} paragraph must be unique"
    return leads[0]


# ── the twin ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vertical", sorted(INSERTS))
def test_the_line_is_in_the_allow_part(vertical: str) -> None:
    """THE TWIN. Once in the file, and inside the part that ALLOWS, not merely somewhere in the
    file. A bullet in the BLOCK list would teach the opposite, and a search over the whole file
    would pass all the same."""
    text = _scope(vertical)
    assert text.count(LINE) == 1
    assert BULLET in _allow_part(vertical, text)


# ── the control ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vertical", sorted(INSERTS))
def test_the_rest_of_each_definition_is_byte_for_byte_main(vertical: str) -> None:
    """THE CONTROL. Take the insertion out and what is left is ``origin/main``'s file, byte for
    byte; the new digest is pinned too."""
    text = _scope(vertical)
    inserted, before = INSERTS[vertical]
    assert text.count(before) == 1, "the anchor must be unique, or the strip is a guess"
    assert inserted + before in text, "the control must be run over the file that HAS the line"
    assert _sha(without_the_team_line(vertical, text)) == AT_MAIN[vertical]
    assert _sha(text) == NOW[vertical] != AT_MAIN[vertical]


# ── the neighbours ───────────────────────────────────────────────────────────────────────────
def test_the_set_is_every_scope_on_disk() -> None:
    """The denominator: the three given the line and the three not given it are every scope.txt on
    disk, so a new vertical has to be placed in one set or the other."""
    on_disk = {p.parent.parent.name for p in PKG.glob("*/prompts/scope.txt")}
    assert on_disk == set(INSERTS) | set(NEIGHBOURS_AT_MAIN)
    assert not set(INSERTS) & set(NEIGHBOURS_AT_MAIN)


@pytest.mark.parametrize("vertical", sorted(NEIGHBOURS_AT_MAIN))
def test_the_neighbours_did_not_move(vertical: str) -> None:
    text = _scope(vertical)
    assert LINE not in text
    assert _sha(text) == NEIGHBOURS_AT_MAIN[vertical]
