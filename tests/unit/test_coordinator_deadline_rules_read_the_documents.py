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
to ``check_deadlines``, the deadline RULES go to ``consult_documents``. Offline A/B, calibrated
(the base reproduced the live turn, 5/5), the served host's real executor prompt with the context
rebuilt from the live trace, n=5:

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

## What this file pins, and what it does not

Everything here is an assertion about the PROMPT. Whether the model obeys was measured above, and
is not what a unit test measures. What this buys is that a future edit does not put the old line
back in silence, and that the change was THESE two lines and nothing else:

* the TWIN: the two lines are in the mapping, once each, in the old line's place, and the old line
  is gone;
* the CONTROL: put the old line back and the file is, byte for byte, ``origin/main``'s (its digest,
  pinned), so not a comma of the rest moved;
* the NEIGHBOURS: every other prompt of every vertical is byte for byte what it was.

The pinned digests are a LANDING proof, made to age: a deliberate edit of one of those files
changes its digest with reason, and the digest is then regenerated in the SAME PR that changed the
text (``sha256`` of the file at the new base), never edited to silence a red.

MUTATIONS:
    put ``OLD`` back in place of the two lines (``main``'s file)
    → both twins die; the control dies at its PRECONDITION (it refuses to run over a file without
      the two lines, because that file IS main's and the control would pass on it vacuously); the
      neighbours SURVIVE.
    swap the two tools between the lines (OPEN → consult_documents, RULES → check_deadlines)
    → both twins die, and the control at its precondition; the neighbours SURVIVE.
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

#: The two lines, byte for byte as measured.
OPEN = ("- Grade/attendance deadlines currently OPEN (which disciplines are due now) "
        "→ check_deadlines(professor?)")
RULES = ("- The deadline RULES a teacher must follow (what is due, by when, after each class) "
         "→ consult_documents(query)")

#: ``sha256`` of ``coordinator/prompts/system.txt`` at ``origin/main`` 6d1ca3a, with ``OLD``.
SYSTEM_AT_MAIN = "d5c3938722b016ad092126b229c6c52965f2ae6afaa5aca144046c39a4714d16"

#: ``sha256`` of the file WITH the two lines: the new digest, pinned. It follows from the twin plus
#: the control's first half; written out so a reader holding a digest can compare it without
#: rebuilding the file.
SYSTEM_NOW = "1882c35cca1b7c8bcdf72793ab70cd91befa5b828b5a3d6f5136882ed61046c1"

#: ``sha256`` of every OTHER prompt of every vertical at ``origin/main`` 6d1ca3a.
NEIGHBOURS_AT_MAIN = {
    "bookkeeper/limits.txt": "d1e1abdbb376861fe42b923037bf3341927306836c4e181247887b48608b7c54",
    "bookkeeper/scope.txt": "4f33eb5c6791691c32c7451d735a72bd4e1af2bd4d7809ba73b0ece076bf240d",
    "bookkeeper/system.txt": "8fc3ec6856ef0964406e59c16b032fad2f5d9a24ae5613895dd8c9db9bf30596",
    "bookkeeper/voice.txt": "1b65181573edc71b964a686d96c92ab94b664bb094b88d4911e034536c95d347",
    "closer/limits.txt": "2c8bf84a2625317e363f8fc175029b7d85d9a28fb90190b5c254391981f10e4c",
    "closer/scope.txt": "8e4f6efceced8f822b717f82fc311aad14b20ce76772f7175a3ef223a0cd8802",
    "closer/system.txt": "c5b30b8faf18562ec7936965e16fe59a8570d4bc9d67654c3156f9c170cf623d",
    "closer/voice.txt": "ecf7b265950d2b9797fb2329c430fad558988c07e0e4652228ec81e0a7bb73c1",
    "companies/scope.txt": "b73e4e51036e6ebf17ad5e4ba8c7ef56a1b8b0c31c394047ec9d1a976671e2e4",
    "coordinator/limits.txt": "693599819f703f755d863a5298caaba2573685fed63091f80690ada60dc7c8d0",
    "coordinator/scope.txt": "ff38d9a124d1cb5d28464391868c098fec329874bc400059f9cf5dd2fc912dc3",
    "coordinator/voice.txt": "21ca2bcf50fc42613687c6cb61f40ec6c0510b6384061a7c22bf8d45308b9ead",
    "interviewer/limits.txt": "02a8bc07cb85464f3ca8e0df28385329473429b0b479f92a29ec1b4dfad0f918",
    "interviewer/scope.txt": "69b772297a1fb1ef5e5ad90d78b536bb6c19a2e4d11ab5df6d361160041754e3",
    "interviewer/system.txt": "640c76109c62a142f6304af1b8592b79e1c9808735a3daf067c24f3abc42be27",
    "interviewer/voice.txt": "0dfe458c1778ed53dfcb8cadbcfdc69993ecd8cc7233e7ca3dcc5de9a8b1887e",
    "scheduler/limits.txt": "92becaf1d23c56570833082fe1507e01c0afe3a52922ee8404ed671a53a6a2a4",
    "scheduler/scope.txt": "633c8edf7cdb568137e31a6b2b64be1746231b16932b157605d43ee99f1ff7eb",
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
