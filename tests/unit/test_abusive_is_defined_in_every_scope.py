"""Every ``scope.txt`` that blocks ABUSIVE messages says what "abusive" means — the same sentence.

## The defect

Five scope definitions tell the relevance guard to block messages that are "abusive" (the CLOSER
and the INTERVIEWER say it in Portuguese, "abusivas") and none of them said what the word means.
A small classifier fills that gap with TONE. The shape, with invented wording: a contact rejects a
message the assistant proposed and writes «essa mensagem ficou uma porcaria, faz uma melhor» with
a swear word in place of «porcaria». The guard BLOCKED it 5/5, even with the specific pending
request in the prompt (host #1145). The same sentence without the swear word, same request: ALLOW
5/5. The tone alone decided, and the contact was refused for asking the assistant to redo its own
text.

## The repair

ONE sentence, ``DEFINITION`` below, appended as the LAST paragraph of each of the five files, so it
follows the last place each file says "abusive". It is the SAME sentence in all five. There is no
shared include: the host reads each ``scope.txt`` raw (``cogno_host.persona.load_persona``,
``cogno_host.scope_compose``), so the sameness is pinned here instead. The sentence is in English
in the two Portuguese files as well: the guard's own instructions (``cogno_anima``) are English,
and one sentence that cannot drift between two languages is the point of the rule.

The decision, with the parenthesis added: abusive = an insult or a threat aimed at a PERSON
(anyone in the conversation, the assistant included). Criticism of what the assistant wrote, even
crude or profane, is NOT abuse and is a request to change that text. The parenthesis is there
because the abuse control the measurement must keep at BLOCK («sua burra, vou te processar») is
aimed at the assistant. Without it, "a PERSON" can be read as "not the assistant", and the
definition would let that control through.

## The one variant: the INTERVIEWER also says "offensive"

The INTERVIEWER blocks messages that are «abusivas, ofensivas», and "offensive" was just as
undefined. So in that file alone the sentence opens with «"Abusive"/"offensive" means …» and
the rest is the same, byte for byte (Director, 2026-10-01). This is the variant in ONE file,
not the longer form in all five. The four other files stay exactly as they were first written,
including the coordinator, whose slot is the one being measured against the served guard. The
variant is DERIVED from ``DEFINITION`` by one substitution, never written out by hand. The
sameness test undoes that substitution before it compares, so the five still have to be one
sentence.

## What this file pins, and what it does not

Assertions about the PROMPT only. Whether the model obeys is measured outside this repo, against
the served guard. Here:

* the DENOMINATOR — the files that say "abusiv…" are DERIVED from disk and must be exactly the
  five, so a new vertical that blocks abuse is covered the day it arrives;
* the TWIN — each of the five carries its sentence (``DEFINITION``, or ``OFFENSIVE`` in the
  interviewer) once, as its last paragraph, after its last mention of the word;
* the SAMENESS — the definition paragraph read out of each file, with the one substitution
  undone, is one string across the five, and only the interviewer carries the variant;
* the CONTROL — remove the paragraph and each file is, byte for byte, the file at ``origin/main``
  5f1ae0e (digests pinned), and the new digests are pinned as well;
* the NEIGHBOUR — ``scheduler/prompts/scope.txt`` never says "abusive" and did not move.

The pinned digests are a LANDING proof, made to age: a deliberate edit of one of those files is
regenerated in the SAME PR that changed it, never edited to silence a red.

MUTATIONS:
    remove ``DEFINITION`` (and its blank line) from ``closer/prompts/scope.txt``
    → ``test_the_definition_is_the_last_paragraph[closer]``,
      ``test_every_scope_that_blocks_abuse_defines_it`` and
      ``test_the_definition_is_the_same_sentence_in_all_five`` die; the control dies at its
      PRECONDITION (it refuses a file without the paragraph, which IS main's file).
    change one word of the sentence in ``coordinator/prompts/scope.txt`` only
    → ``test_the_definition_is_the_same_sentence_in_all_five`` dies, and so do the twin and the
      control for ``coordinator``; the other four survive.
    change one comma elsewhere in ``bookkeeper/prompts/scope.txt``
    → ``test_the_rest_of_each_definition_is_byte_for_byte_main[bookkeeper]`` dies; the twin and
      the sameness survive.
    write the interviewer's variant into ``closer/prompts/scope.txt`` as well
    → ``test_the_definition_is_the_same_sentence_in_all_five`` dies (the variant is the
      interviewer's alone), with the twin and control for ``closer``.
    In each case the scope digests that #153 and #154 pin die too, for the same file only.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from tests.unit.test_messages_to_the_team_are_in_scope import without_the_team_line

#: The package the HOST reads the prompts from — the installed package, never a path relative to
#: this checkout, so the file under test is the one a host would load.
PKG = Path(__import__("cogno_praxis").__file__).resolve().parent

#: The sentence, byte for byte. One line, no placeholder: the host formats ``{tenant_name}`` in
#: these files, and a brace here would be a formatting slot.
DEFINITION = (
    '"Abusive" means an insult or a threat aimed at a PERSON (anyone in the conversation, the '
    "assistant included). Criticism of what the assistant wrote, even crude or profane, is NOT "
    "abuse: treat it as a request to change that text.")

#: What is appended to each file: a blank line, then the sentence and the newline that ends it.
PARAGRAPH = "\n" + DEFINITION + "\n"

#: The one substitution that makes the INTERVIEWER's variant (its scope also says «ofensivas»).
_PLAIN, _WITH_OFFENSIVE = '"Abusive" means', '"Abusive"/"offensive" means'

#: The interviewer's sentence — DERIVED from ``DEFINITION``, never written out a second time.
OFFENSIVE = DEFINITION.replace(_PLAIN, _WITH_OFFENSIVE, 1)

#: Which vertical carries which sentence. Every vertical not named here carries ``DEFINITION``.
VARIANTS = {"interviewer": OFFENSIVE}


def _sentence(vertical: str) -> str:
    return VARIANTS.get(vertical, DEFINITION)


def _paragraph(vertical: str) -> str:
    return "\n" + _sentence(vertical) + "\n"

#: ``sha256`` of each ``scope.txt`` at ``origin/main`` 5f1ae0e, before the sentence.
AT_MAIN = {
    "bookkeeper": "4f33eb5c6791691c32c7451d735a72bd4e1af2bd4d7809ba73b0ece076bf240d",
    "closer": "8e4f6efceced8f822b717f82fc311aad14b20ce76772f7175a3ef223a0cd8802",
    "companies": "b73e4e51036e6ebf17ad5e4ba8c7ef56a1b8b0c31c394047ec9d1a976671e2e4",
    "coordinator": "ff38d9a124d1cb5d28464391868c098fec329874bc400059f9cf5dd2fc912dc3",
    "interviewer": "69b772297a1fb1ef5e5ad90d78b536bb6c19a2e4d11ab5df6d361160041754e3",
}

#: ``sha256`` of each file WITH the sentence. Implied by the twin plus the control's first half;
#: written out so a reader holding a digest can compare it without rebuilding the file.
NOW = {
    "bookkeeper": "038237d093ebeba38af3fc3f5c777882c59bad5b6eddb6b9bf6c89f5483db063",
    "closer": "92c91dc45dbf3e7538b20f697e38ff99e8b3c69ba4f17d3bcb5b1dce746f3714",
    "companies": "c410e899125d712a7e5cbc9880627febca04e497a61059af9650ab236f00c805",
    "coordinator": "7a03422e0991306317e48df84a8fcd796c9eb507e5c7b4e0291fa8c401d7264b",
    "interviewer": "d80bcb9076c17f2c9cf87776cd1212316801a6f5677f64027509aeed06748b8c",
}

#: The scope that never says "abusive", at ``origin/main`` 5f1ae0e. It is not given the sentence:
#: a definition of a word the file does not use would be a new rule, not a definition.
SCHEDULER_AT_MAIN = "633c8edf7cdb568137e31a6b2b64be1746231b16932b157605d43ee99f1ff7eb"

#: The word, in both languages the files are written in ("abusive", "Abusive", "abusivas").
_ABUSIVE = re.compile(r"abusiv", re.IGNORECASE)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scopes() -> "dict[str, str]":
    """Every ``scope.txt`` on disk, per vertical — derived, never a hand-written list."""
    found = {p.parent.parent.name: p.read_text(encoding="utf-8")
             for p in PKG.glob("*/prompts/scope.txt")}
    assert found, "no scope.txt on disk — this file would pass on an empty set"
    return found


def _paragraphs(text: str) -> "list[str]":
    """The file's unit of section is the PARAGRAPH (blank lines, no headers)."""
    return [p for p in text.split("\n\n") if p.strip()]


def _without_the_definition(text: str) -> str:
    """The file as it was before: the definition paragraph is not part of what blocks abuse, so
    the mentions of the word are counted without it (either sentence)."""
    return text.replace(PARAGRAPH, "", 1).replace("\n" + OFFENSIVE + "\n", "", 1)


# ── the denominator ──────────────────────────────────────────────────────────────────────────
def test_the_five_are_exactly_the_scopes_that_say_abusive() -> None:
    """The files to define the word in are the files that USE it, read off the disk with the
    definition taken out — and they are the five pinned here, no more, no fewer."""
    users = {v for v, t in _scopes().items() if _ABUSIVE.search(_without_the_definition(t))}
    assert users == set(AT_MAIN), users
    assert len(users) == 5


def test_every_scope_that_blocks_abuse_defines_it() -> None:
    """Derived: a scope that blocks abuse without saying what it is fails here, whatever its
    name, including one that does not exist yet."""
    missing = [v for v, t in _scopes().items()
               if _ABUSIVE.search(_without_the_definition(t))
               and DEFINITION not in t and OFFENSIVE not in t]
    assert not missing, f"these scope.txt say 'abusive' and never define it: {missing}"


# ── the twin ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vertical", sorted(AT_MAIN))
def test_the_definition_is_the_last_paragraph(vertical: str) -> None:
    """THE TWIN. Once, as its own last paragraph — so it follows the last place the file names
    the word it defines, and nothing after it qualifies it."""
    text = _scopes()[vertical]
    assert text.count(_sentence(vertical)) == 1
    assert text.endswith(_paragraph(vertical))
    paragraphs = _paragraphs(text)
    assert paragraphs[-1] == _sentence(vertical) + "\n"
    assert any(_ABUSIVE.search(p) for p in paragraphs[:-1]), "nothing above it to define"


def test_the_definition_is_the_same_sentence_in_all_five() -> None:
    """THE SAMENESS. Read OUT of each file (its last paragraph), not compared against the constant
    — so two files that drifted apart in the same way would still be caught against the others.
    The interviewer's one substitution is undone first; it is the ONLY file that may carry it."""
    last = {v: _paragraphs(_scopes()[v])[-1] for v in AT_MAIN}
    carriers = {v for v, p in last.items() if _WITH_OFFENSIVE in p}
    assert carriers == set(VARIANTS), carriers
    same = {v: p.replace(_WITH_OFFENSIVE, _PLAIN, 1) for v, p in last.items()}
    assert len(set(same.values())) == 1, {v: p[:60] for v, p in same.items()}
    assert set(same.values()) == {DEFINITION + "\n"}


# ── the control ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vertical", sorted(AT_MAIN))
def test_the_rest_of_each_definition_is_byte_for_byte_main(vertical: str) -> None:
    """THE CONTROL. Take the paragraph out and what is left is ``origin/main``'s file, byte for
    byte; the new digest is pinned too. A LATER insertion (the team-message line) is taken out
    first, so this control keeps measuring THIS paragraph and nothing that landed after it."""
    text = without_the_team_line(vertical, _scopes()[vertical])
    para = _paragraph(vertical)
    assert text.endswith(para), "the control must be run over the file that HAS the paragraph"
    assert _sha(text[: -len(para)]) == AT_MAIN[vertical]
    assert _sha(text) == NOW[vertical] != AT_MAIN[vertical]


def test_the_scheduler_did_not_move() -> None:
    """THE NEIGHBOUR. The one scope that never says the word is not given its definition."""
    text = without_the_team_line("scheduler", _scopes()["scheduler"])
    assert not _ABUSIVE.search(text)
    assert _sha(text) == SCHEDULER_AT_MAIN
