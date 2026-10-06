"""The COORDINATOR's tool mapping tells the deadlines OPEN now from the deadline RULES.

## The defect

``coordinator/prompts/system.txt`` carries a hard tool mapping, and one of its lines said
``Grade/attendance deadlines → check_deadlines(professor?)``. ``check_deadlines`` reads the
spreadsheets and answers which disciplines are inside the grade/attendance window TODAY: it is a
read of the institution's RECORDS. The RULES a teacher must follow (what is due, by when, after
each class) are not records. When an institution publishes them, they live in its documents, and
the host offers them to the persona through ``consult_documents``.

Measured on a rehearsal tenant (the shape, with no names): a coordination member asked the
COORDINATOR «what deadlines does the teacher have to meet?». The executor called
``check_deadlines`` 5/5 and ``consult_documents`` 0/5. ``consult_documents`` was on the table and
the host's generic documents duty was in the prompt, and both lost to the mapping line: a DUTY
written for every persona does not beat a MAPPING written for this one.

## The repair, and the measurement it rests on (cited, not repeated here)

The one mapping line becomes TWO (``OPEN`` and ``RULES`` below): the deadlines currently OPEN go
to ``check_deadlines``, the deadline RULES go to ``consult_documents``, when it is among this
turn's tools. Offline A/B, calibrated (the base reproduced the live turn, 5/5), the served host's
real executor prompt with the context rebuilt from the live trace, n=5:

    the question above                            served → check_deadlines 5/5
                                                  a generic documents duty → check_deadlines 5/5
                                                  the two mapping lines → consult_documents 5/5
    records control («which disciplines have a    served → check_deadlines 5/5
    grade deadline expiring this week?»)          the two mapping lines → check_deadlines 5/5

The bytes are the replay's: it swapped ``OLD`` for ``OPEN + "\\n" + RULES`` in the rendered
prompt, once, so the two lines are NOT padded to the arrow column the neighbouring lines use.
Aligning them would be typography to the model, and it would still be a different byte string
from the one measured.

The question is AMBIGUOUS (the rules, or the deadlines open now), and the best answer might read
both. This change sends the ambiguous form to the rules. Forcing it to read both was not measured,
so it is not done here.

## The condition that closes the RULES line

``consult_documents`` is the HOST's tool, and the host offers it only on a turn whose reader has a
published document to read. Without a condition, the mapping would send the question to a tool
that is not on that turn's table. So the RULES line ends with ``CONDITION`` («, when it is among
this turn's tools»), AFTER the arrow. That is the version measured above, on turns that had the
tool on the table. A version with the condition BEFORE the arrow scored 4/5 in the same replay and
was discarded.

## The judge, measured with ``limits.txt`` as it is

``coordinator/prompts/limits.txt`` lists the tools a schedule fact may come from, and
``consult_documents`` is not in that list. Measured with that file unchanged: the judge APPROVED
the correct reply 5/5 and REJECTED 5/5 a control reply that invents a deadline. So
``limits.txt`` does not change, and it stays among the NEIGHBOURS below.

## What this file pins, and what it does not

Everything here is an assertion about the PROMPT. Whether the model obeys was measured above, and
is not what a unit test measures. What this buys is that a future edit does not put the old line
back in silence, and that the change was THESE two lines and nothing else:

* the TWIN: the two lines are in the mapping, once each, in the old line's place, and the old line
  is gone; the RULES line ends with its condition, after the arrow;
* the CONTROL: put the old line back and the file is, byte for byte, ``origin/main``'s (its digest,
  pinned), so not a comma of the rest moved;
* the NEIGHBOURS: every other prompt of every vertical is byte for byte what it was.

The pinned digests are a LANDING proof, made to age: a deliberate edit of one of those files
changes its digest with reason, and the digest is then regenerated in the SAME PR that changed the
text (``sha256`` of the file at the new base), never edited to silence a red.

MUTATIONS:
    put ``OLD`` back in place of the two lines (``main``'s file)
    → the three twins die; the control dies at its PRECONDITION (it refuses to run over a file
      without the two lines, because that file IS main's and the control would pass on it
      vacuously); the neighbours SURVIVE.
    swap the two tools between the lines (OPEN → consult_documents, RULES → check_deadlines)
    → the three twins die, and the control at its precondition; the neighbours SURVIVE.
    take the condition off the RULES line (the first cut of this PR)
    → the three twins die, and the control at its precondition; the neighbours SURVIVE.
    move the condition BEFORE the arrow (the variant the replay discarded)
    → the three twins die, and the control at its precondition; the neighbours SURVIVE.
    append ``RULES`` to ``coordinator/prompts/limits.txt``
    → ``test_each_neighbour_prompt_is_byte_for_byte_main[coordinator/limits.txt]`` dies, and only it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

#: The package the HOST reads the prompt from, the installed package and never a path relative to
#: this checkout, so the file under test is the one a host would load.
PKG = Path(__import__("cogno_praxis").__file__).resolve().parent
SYSTEM_PATH = PKG / "coordinator" / "prompts" / "system.txt"

#: The line the two replace, byte for byte as it was at ``origin/main`` 6d1ca3a.
OLD = "- Grade/attendance deadlines             → check_deadlines(professor?)"

#: The two lines, byte for byte as measured. ``RULES`` is its route plus the ``CONDITION`` that
#: closes it.
OPEN = ("- Grade/attendance deadlines currently OPEN (which disciplines are due now) "
        "→ check_deadlines(professor?)")
CONDITION = ", when it is among this turn's tools"
RULES = ("- The deadline RULES a teacher must follow (what is due, by when, after each class) "
         "→ consult_documents(query)" + CONDITION)

#: ``sha256`` of ``coordinator/prompts/system.txt`` at ``origin/main`` 6d1ca3a, with ``OLD``.
SYSTEM_AT_MAIN = "d5c3938722b016ad092126b229c6c52965f2ae6afaa5aca144046c39a4714d16"

#: ``sha256`` of the file WITH the two lines: the new digest, pinned. It follows from the twin plus
#: the control's first half; written out so a reader holding a digest can compare it without
#: rebuilding the file.
SYSTEM_NOW = "5085d29f398179ea208eb2b81f28b2a51489004b12e6c7f2f3527f02dcee1e89"

#: ``sha256`` of every OTHER prompt of every vertical at ``origin/main`` 6d1ca3a — the five
#: ``scope.txt`` that later gained the definition of "abusive" regenerated in that PR
#: (``test_abusive_is_defined_in_every_scope``), and the three that then gained the team-message
#: line (``test_messages_to_the_team_are_in_scope``).
#: The BOOKKEEPER's ``limits.txt`` and ``system.txt`` were regenerated when AI cost started
#: coming from ``token_cost_analytics`` (``test_bookkeeper_ai_cost_comes_from_the_cost_tool``),
#: which pins their old bytes against ``origin/main`` 45d2ed6.
NEIGHBOURS_AT_MAIN = {
    "bookkeeper/limits.txt": "e64431a18082ddbb734a328fbd1a6a2ee51207a2b060036667e7d00ceee5916a",
    "bookkeeper/scope.txt": "ed4a8c112f11d2c2bf480c4e8be806f9d1f707e12c1bf638e541e5f17f3ee342",
    "bookkeeper/system.txt": "8d6535d3326748e703e56a15bdc5ff5c546ae0fb47dc2ba38f876b61c3e45665",
    "bookkeeper/voice.txt": "1b65181573edc71b964a686d96c92ab94b664bb094b88d4911e034536c95d347",
    "closer/limits.txt": "2c8bf84a2625317e363f8fc175029b7d85d9a28fb90190b5c254391981f10e4c",
    "closer/scope.txt": "92c91dc45dbf3e7538b20f697e38ff99e8b3c69ba4f17d3bcb5b1dce746f3714",
    "closer/system.txt": "c5b30b8faf18562ec7936965e16fe59a8570d4bc9d67654c3156f9c170cf623d",
    "closer/voice.txt": "ecf7b265950d2b9797fb2329c430fad558988c07e0e4652228ec81e0a7bb73c1",
    "companies/scope.txt": "c410e899125d712a7e5cbc9880627febca04e497a61059af9650ab236f00c805",
    "coordinator/limits.txt": "693599819f703f755d863a5298caaba2573685fed63091f80690ada60dc7c8d0",
    "coordinator/scope.txt": "7a03422e0991306317e48df84a8fcd796c9eb507e5c7b4e0291fa8c401d7264b",
    "coordinator/voice.txt": "21ca2bcf50fc42613687c6cb61f40ec6c0510b6384061a7c22bf8d45308b9ead",
    "interviewer/limits.txt": "02a8bc07cb85464f3ca8e0df28385329473429b0b479f92a29ec1b4dfad0f918",
    "interviewer/scope.txt": "b25231522c0c48c4658bbf5e1824cf9bc3fc544ecf02b0d09a2b0df1e815a921",
    "interviewer/system.txt": "640c76109c62a142f6304af1b8592b79e1c9808735a3daf067c24f3abc42be27",
    "interviewer/voice.txt": "0dfe458c1778ed53dfcb8cadbcfdc69993ecd8cc7233e7ca3dcc5de9a8b1887e",
    "scheduler/limits.txt": "92becaf1d23c56570833082fe1507e01c0afe3a52922ee8404ed671a53a6a2a4",
    "scheduler/scope.txt": "b2f942c84374955d9aad03f951ce4082d4cc4d0c45638cad4d1c6b9f89b3448f",
    "scheduler/system.txt": "49d2c8ce3706642f1baeef66ea2717be061f2262ccd6fa83f132e08cd93d58b2",
    "scheduler/voice.txt": "68c17d7ea87916af677d8d03f532975de41c729b90e9e4b3587a5ddc5e68ae9b",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _system() -> str:
    return SYSTEM_PATH.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Whitespace collapsed: the old line must not survive under a different column."""
    return " ".join(text.split())


def _mapping(system: str) -> list[str]:
    """The lines of the ``Required tool mapping:`` block, from its header to the blank line that
    closes it. The header is counted to exactly one, or the block is a guess."""
    assert system.count("Required tool mapping:\n") == 1
    block = system.split("Required tool mapping:\n", 1)[1].split("\n\n", 1)[0]
    return block.split("\n")


# ── the twin ─────────────────────────────────────────────────────────────────────────────────
def test_the_two_lines_replace_the_one_in_the_file_the_host_loads() -> None:
    """THE TWIN. The file the host hands the executor carries the two lines, once each, one right
    after the other, and the old line is gone, under any column."""
    system = _system()
    assert system.count(OPEN) == 1
    assert system.count(RULES) == 1
    assert OPEN + "\n" + RULES in system, "the two lines must be adjacent, OPEN first, as measured"
    assert OLD not in system
    assert _flat(OLD) not in _flat(system)


def test_the_two_lines_sit_in_the_mapping_where_the_old_one_sat() -> None:
    """In the MAPPING, in the old line's place: after the schedule entry and its continuation,
    before the week-ahead entry. Each tool is routed by exactly one line of the file, so the
    deadlines open now and the deadline rules cannot both land on one tool while a search over
    the whole file still passes."""
    system = _system()
    block = _mapping(system)
    assert OPEN in block and RULES in block
    i = block.index(OPEN)
    assert block[i + 1] == RULES
    assert block[i - 1].startswith("  Leave `professor` EMPTY"), "the schedule entry precedes it"
    assert block[i + 2].startswith("- Week ahead"), "the week-ahead entry follows it"
    assert system.count("check_deadlines") == 1 and "→ check_deadlines(" in OPEN
    assert system.count("consult_documents") == 1 and "→ consult_documents(" in RULES


def test_the_rules_line_ends_with_its_condition() -> None:
    """The RULES line sends the question to ``consult_documents`` only when the tool is on this
    turn's table, and the condition CLOSES the line, after the arrow, where it was measured. One
    line of the mapping routes to the tool, and the condition appears once in the whole file, so
    it cannot drift onto another line while the route stays."""
    system = _system()
    routes = [line for line in _mapping(system) if "→ consult_documents(" in line]
    assert routes == [RULES]
    assert routes[0].endswith("→ consult_documents(query)" + CONDITION)
    assert system.count(CONDITION) == 1


# ── the control ──────────────────────────────────────────────────────────────────────────────
def test_the_rest_of_the_prompt_is_byte_for_byte_main() -> None:
    """THE CONTROL. Put the old line back and what is left is ``origin/main``'s file, byte for
    byte: the digest moved by the two lines and by nothing else. The new digest is pinned too."""
    system = _system()
    assert OPEN + "\n" + RULES in system, "the control must be run over the file that HAS the lines"
    assert _sha(system.replace(OPEN + "\n" + RULES, OLD, 1)) == SYSTEM_AT_MAIN
    assert _sha(system) == SYSTEM_NOW != SYSTEM_AT_MAIN


# ── the neighbours ───────────────────────────────────────────────────────────────────────────
def _on_disk() -> set[str]:
    return {f"{p.parent.parent.name}/{p.name}" for p in PKG.glob("*/prompts/*.txt")}


def test_the_neighbours_are_all_on_disk() -> None:
    """The denominator first: the 20 pinned prompts are all on disk, so an absent file cannot pass
    by having nothing to hash, and the file this change edits is not among them."""
    on_disk = _on_disk()
    assert len(NEIGHBOURS_AT_MAIN) == 20 and set(NEIGHBOURS_AT_MAIN) <= on_disk
    assert "coordinator/system.txt" in on_disk and "coordinator/system.txt" not in NEIGHBOURS_AT_MAIN


@pytest.mark.parametrize("prompt", sorted(NEIGHBOURS_AT_MAIN))
def test_each_neighbour_prompt_is_byte_for_byte_main(prompt: str) -> None:
    vertical, name = prompt.split("/")
    text = (PKG / vertical / "prompts" / name).read_text(encoding="utf-8")
    assert _sha(text) == NEIGHBOURS_AT_MAIN[prompt], (
        f"{vertical}/prompts/{name} moved. If that was deliberate, regenerate its digest in the "
        "SAME PR (see the module docstring); this change edited the COORDINATOR's system.txt only")
