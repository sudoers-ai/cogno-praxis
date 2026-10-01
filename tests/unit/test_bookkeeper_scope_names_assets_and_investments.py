"""The BOOKKEEPER's scope names the business's ASSETS and INVESTMENTS, not only its ledger.

## The defect

``bookkeeper/prompts/scope.txt`` opens its ALLOW paragraph with «any message about the business's
finances» and then ENUMERATES — recording income or expenses, summaries by period, searching or
removing transactions, listing clients, AI usage. Every item on that list is an operation of the
LEDGER tools. A business's finances are wider than its ledger: the document a tenant publishes to
the persona can be about what the business OWNS — its wealth, its investments, what its properties
cost to buy, build or renovate — and none of that is a ledger operation.

The relevance guard reads the definition, not the phrase that opens it. Measured on a rehearsal
tenant (the shape, with invented names: a SUPERVISOR asking the BOOKKEEPER what the construction
and renovation of one of the business's properties cost, on a turn whose guard prompt carried the
owner's document outline — twelve section titles, among them «9. <property> — Investimento» —,
the ``consult_documents`` contribution and the tool table), the guard BLOCKED. The sections were
in the prompt, so it was not the STRUCTURE: it was the DEFINITION.

## The repair, and the measurement it rests on (cited, not repeated here)

ONE sentence, appended to the ALLOW paragraph right after its enumeration (``LINE`` below). The
production guard (``gpt-4o-mini``, JSON), the real prompt the served host assembles, n=5:

    the question above         served → BLOCK 5/5     with the sentence → ALLOW 5/5
    out-of-scope control       served → BLOCK 5/5     with the sentence → BLOCK 5/5
    (a carrot-cake recipe)

It is spliced on the SAME line as the enumeration it extends, exactly as the replay spliced it
(``prompt.replace(ANCHOR, ANCHOR + LINE)``), so the bytes that ship are the bytes that were
measured. A line break in ``scope.txt`` is typography to the model; it is still a different byte
string from the one measured, and a prompt change is argued by its measurement.

## What this file pins, and what it does not

Everything here is an assertion about the PROMPT. Whether the model obeys was measured above,
against the served model, and is not what a unit test measures. What this buys is that a future
edit does not delete the sentence in silence, and that the change was THIS sentence and nothing
else:

* the TWIN — the sentence is in the definition the guard receives, in the ALLOW paragraph;
* the CONTROL — remove the sentence and the file is, byte for byte, the file at ``origin/main``
  before it (its digest, pinned), so not a comma of the rest moved;
* the NEIGHBOURS — every other vertical's ``scope.txt`` is byte for byte what it was. The other
  definitions that also enumerate only their tools' operations are NOT widened here: none of them
  was measured.

The pinned digests are a LANDING proof, made to age: a deliberate edit of one of those files
changes its digest with reason, and the digest is then regenerated in the SAME PR that changed
the text (``sha256`` of the file at the new base) — never edited to silence a red.

MUTATIONS:
    remove ``LINE`` from ``bookkeeper/prompts/scope.txt``
    → ``test_the_sentence_is_in_the_definition_the_guard_receives`` and
      ``test_the_sentence_sits_in_the_allow_paragraph`` die; the control dies at its
      PRECONDITION — it refuses to run over a file without the sentence, because that file IS
      main's and the control would pass on it vacuously; the neighbours SURVIVE.
    change one comma elsewhere in the same file
    → ``test_the_rest_of_the_definition_is_byte_for_byte_main`` dies; the twin SURVIVES.
    widen a NEIGHBOUR (append the same sentence to ``coordinator/prompts/scope.txt``)
    → ``test_each_neighbour_scope_is_byte_for_byte_main[coordinator]`` dies, and only it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.unit.test_abusive_is_defined_in_every_scope import PARAGRAPH as ABUSIVE_PARAGRAPH

#: The package the HOST reads the prompt from (``Path(cogno_praxis.__file__).parent /
#: "bookkeeper" / "prompts"`` is its ``_bookkeeper_prompts_dir``) — the installed package, never a
#: path relative to this checkout, so the file under test is the one a host would load.
PKG = Path(__import__("cogno_praxis").__file__).resolve().parent
SCOPE_PATH = PKG / "bookkeeper" / "prompts" / "scope.txt"

#: The end of the enumeration the sentence extends. Counted to exactly one below.
ANCHOR = "listing clients, and AI-usage questions."

#: The sentence, byte for byte as measured (with the one leading space that joins it to ANCHOR).
LINE = (" This includes the business's own ASSETS and INVESTMENTS — its wealth, investments and the "
        "acquisition, construction or renovation costs of its properties — whether they come from "
        "the ledger or from its documents.")

#: ``sha256`` of ``bookkeeper/prompts/scope.txt`` at ``origin/main`` 5ae6ce3, before the sentence.
BOOKKEEPER_AT_MAIN = "3e6b0812521d1c5ea2214736539406aba6d202ba72c44300921e17c241ae269d"

#: ``sha256`` of the file WITH the sentence — the new digest, pinned. Implied by the twin plus the
#: control's first half (main's bytes, the sentence once after ANCHOR); written out so a reader
#: holding a digest can compare it without rebuilding the file.
BOOKKEEPER_NOW = "4f33eb5c6791691c32c7451d735a72bd4e1af2bd4d7809ba73b0ece076bf240d"

#: Paragraphs a LATER PR appended to this file, each pinned by its own test: the definition of
#: "abusive" (``test_abusive_is_defined_in_every_scope.py``). Taken out before the control, so the
#: control keeps measuring THIS sentence and nothing that landed after it.
LATER = (ABUSIVE_PARAGRAPH,)

#: ``sha256`` of every OTHER vertical's ``scope.txt`` at ``origin/main`` 5ae6ce3 — regenerated for
#: the four that later gained the definition of "abusive" (``test_abusive_is_defined_in_every_scope``).
NEIGHBOURS_AT_MAIN = {
    "closer": "92c91dc45dbf3e7538b20f697e38ff99e8b3c69ba4f17d3bcb5b1dce746f3714",
    "companies": "c410e899125d712a7e5cbc9880627febca04e497a61059af9650ab236f00c805",
    "coordinator": "7a03422e0991306317e48df84a8fcd796c9eb507e5c7b4e0291fa8c401d7264b",
    "interviewer": "30e5e7ec214aa76863318bf2d42deb6bc379db544cc8698e79d3b5f19857eafc",
    "scheduler": "633c8edf7cdb568137e31a6b2b64be1746231b16932b157605d43ee99f1ff7eb",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scope() -> str:
    return SCOPE_PATH.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Whitespace collapsed: the model reads the sentence, not the column."""
    return " ".join(text.split())


# ── the twin ─────────────────────────────────────────────────────────────────────────────────
def test_the_sentence_is_in_the_definition_the_guard_receives() -> None:
    """THE TWIN. The file the host hands the guard carries the sentence, once, right after the
    enumeration it widens."""
    scope = _scope()
    assert scope.count(ANCHOR) == 1, "the anchor must be unique, or the splice is a guess"
    assert scope.count(LINE) == 1
    assert ANCHOR + LINE in scope, "the sentence must follow the ledger enumeration it widens"


def test_the_sentence_sits_in_the_allow_paragraph() -> None:
    """In the paragraph that ALLOWS — not in the one that blocks. A sentence about assets landing
    in the BLOCK paragraph would teach the opposite, and a search over the whole file would pass
    all the same. The paragraph (the file's unit of section: it has blank lines, no headers) is a
    proper part of the file, counted."""
    paragraphs = [_flat(p) for p in _scope().split("\n\n") if p.strip()]
    allow = [p for p in paragraphs if p.startswith("Allow any message about the business's finances")]
    assert len(allow) == 1
    assert _flat(LINE) in allow[0]
    assert len(paragraphs) > 1 and all(_flat(LINE) not in p for p in paragraphs if p is not allow[0])


# ── the control ──────────────────────────────────────────────────────────────────────────────
def test_the_rest_of_the_definition_is_byte_for_byte_main() -> None:
    """THE CONTROL. Take the sentence out and what is left is ``origin/main``'s file, byte for
    byte: the digest moved by the sentence and by nothing else — and the new digest is pinned."""
    scope = _scope()
    for later in LATER:
        assert scope.endswith(later), "a later paragraph this control strips is not where it was"
        scope = scope[: -len(later)]
    assert LINE in scope, "the control must be run over the file that HAS the sentence"
    assert _sha(scope.replace(LINE, "", 1)) == BOOKKEEPER_AT_MAIN
    assert _sha(scope) == BOOKKEEPER_NOW != BOOKKEEPER_AT_MAIN


def test_the_neighbours_are_not_widened() -> None:
    """The digest of the scope prompt moved in the BOOKKEEPER only. The denominator first: the
    pinned neighbours are all on disk, so an absent file cannot pass by having nothing to hash."""
    on_disk = {p.parent.parent.name for p in PKG.glob("*/prompts/scope.txt")}
    assert set(NEIGHBOURS_AT_MAIN) <= on_disk and len(NEIGHBOURS_AT_MAIN) == 5
    assert "bookkeeper" in on_disk and "bookkeeper" not in NEIGHBOURS_AT_MAIN


@pytest.mark.parametrize("vertical", sorted(NEIGHBOURS_AT_MAIN))
def test_each_neighbour_scope_is_byte_for_byte_main(vertical: str) -> None:
    text = (PKG / vertical / "prompts" / "scope.txt").read_text(encoding="utf-8")
    assert _sha(text) == NEIGHBOURS_AT_MAIN[vertical], (
        f"{vertical}/prompts/scope.txt moved — if that was deliberate, regenerate its digest in "
        "the SAME PR (see the module docstring); this change widened the BOOKKEEPER only")
