"""No ``scope.txt`` in this repo may speak for the WHOLE assistant.

## The defect, measured twice before one line of this prose changed

The relevance guard is handed ONE ``scope.txt`` — the persona's primary capability — and
decides with it a turn on which the persona holds SEVERAL. At a school, a contact asking «que
materiais posso usar para estudar?» was refused by that guard **before the executor ran**, on a
turn holding the very tool whose whole job is that question.

Two repairs were tried and each closed one hypothesis:

* put the TOOL TABLE into the guard's prompt (host #926) — measured: the table arrives
  (``tool_table 1658 chars``, 15 tools offered) **and the model blocks all the same**;
* put the capability ABOVE the definition, under a two-step decision rule (anima #170) —
  measured live on ``gpt-4o-mini``: correct order 10/10 and **BLOCK 6/6** on the same requests.

What was left was the TEXT. ``scheduler/prompts/scope.txt`` said, in two sentences::

    OUT OF SCOPE (BLOCK): … homework
    This is a HARD boundary: the assistant ONLY handles {tenant_name}, its departments, and
    scheduling

For a school, «que materiais posso usar para estudar?» IS homework and is NOT scheduling. The
model obeyed the hard boundary and the example list, and **a two-step rule stacked on top does
not outweigh an explicit** ``ONLY``. A ``scope.txt`` is ONE capability's scope; none of them
knows what else the turn is holding, so none of them may claim exclusivity over the assistant.

## The two halves, and the second is what makes the first worth anything

Stripping ``ONLY`` from everything until the guard lets everything through is not a repair — it
is the guard removed under another name. So this file has a RETRACTION half (no capability
claims the assistant) and a PRESERVATION half (what is forbidden because it is dangerous stays
forbidden, and the retraction says so in its own text).

MUTATION (the retraction):
    put ``the assistant ONLY handles {tenant_name}, its departments, and scheduling`` back into
    ``scheduler/prompts/scope.txt``
    → ``test_no_scope_claims_the_whole_assistant[scheduler]`` dies
    → the whole PRESERVATION half SURVIVES, which is what must survive: it knows nothing about
      exclusivity

MUTATION (the preservation):
    in the same file, swap ``The specialist bullet is the one exception and is never waived``
    for ``The specialist bullet is waived like the others``
    → ``test_the_retraction_does_not_lift_the_hard_prohibition`` dies
    → ``test_no_scope_claims_the_whole_assistant`` SURVIVES: still no ``ONLY``
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PKG = ROOT / "cogno_praxis"


def _scopes() -> "dict[str, str]":
    """The ``scope.txt`` files on disk, per vertical. DERIVED, never a hand-written list: a new
    vertical is covered the day it arrives instead of the day somebody remembers."""
    found = {p.parent.parent.name: p.read_text(encoding="utf-8")
             for p in PKG.glob("*/prompts/scope.txt")}
    assert found, "no scope.txt on disk — this file would pass on an empty set"
    return found


def _flat(text: str) -> str:
    """The text with whitespace collapsed.

    A ``scope.txt`` line break is TYPOGRAPHY — the columns were chosen so a diff fits a screen —
    and the model reads the sentence, not the column. An assertion over the raw text would
    depend on where a word happened to wrap: it fails on a reflow and passes on a rewrite that
    breaks the sentence in the right place.
    """
    return " ".join(text.split())


#: Ways a text claims the whole assistant instead of describing its OWN capability. Closed and
#: lower-case; the measured form plus its obvious neighbours.
_EXCLUSIVE = (
    "assistant only handles",
    "assistant only deals",
    "only handles",
    "handles only",
    "this is a hard boundary",
)


def test_the_measured_set_is_all_here():
    """The denominator, stated before the assertions: the verticals that really ship a scope.

    Without it, deleting a ``scope.txt`` would make this file pass by having nothing to measure
    — and a suite that goes green by going empty is the failure mode ``test_packaging.py`` next
    door already documents for this repo's prompts.
    """
    assert set(_scopes()) >= {"scheduler", "bookkeeper", "coordinator", "companies"}


@pytest.mark.parametrize("vertical", sorted(_scopes()))
def test_no_scope_claims_the_whole_assistant(vertical):
    """THE RETRACTION. A ``scope.txt`` describes its capability; the assistant is their UNION.

    The measured ``ONLY`` was not sloppy writing: it was the most restrictive instruction in the
    prompt, read FIRST by a small classifier, and it beat any rule stacked above it.
    """
    text = _flat(_scopes()[vertical]).lower()
    claims = [f for f in _EXCLUSIVE if f in text]
    assert not claims, (
        f"{vertical}/prompts/scope.txt claims the whole assistant with {claims} — this file is "
        "ONE capability's scope and the turn carries several")


@pytest.mark.parametrize("vertical", ["scheduler", "bookkeeper", "coordinator", "companies"])
def test_every_scope_declares_that_another_capability_may_serve(vertical):
    """The other half of the retraction: SAYING it, not merely ceasing to say the opposite.

    A BLOCK list without this clause keeps blocking by example («homework») even when the
    capability that serves the request is on the table — which is what was measured.
    """
    text = _flat(_scopes()[vertical]).lower()
    assert "another capability" in text and "on this turn" in text, (
        f"{vertical}/prompts/scope.txt never says another capability offered on this turn may "
        "serve the request — without that sentence its BLOCK list speaks for the whole "
        "assistant")


def test_the_retraction_does_not_lift_the_hard_prohibition():
    """PRESERVATION, and it is what separates "it opened" from "it was fixed".

    Two prohibitions are not about TOPIC and no table may lift them: performing the specialist's
    own work (diagnose, prescribe) and abuse. The retraction excludes them in its own text, and
    that is what is asserted here — not a comment.
    """
    scheduler = _flat(_scopes()["scheduler"])
    assert "The specialist bullet is the one exception and is never waived" in scheduler
    # the measured C2 control's own example is still in the file, still on the BLOCK side
    after = scheduler.split("NAMING A SPECIALTY IS NOT OUT OF SCOPE", 1)[1]
    assert 'BLOCK: "meu peito dói' in after

    for vertical in ("bookkeeper", "coordinator", "companies"):
        assert "Abusive or unsafe is never in scope" in _flat(_scopes()[vertical]), vertical


def test_the_transversal_capability_finally_has_a_scope():
    """``companies`` is bound to the SECRETARY beside ``scheduler`` and had no scope at all.

    While it had none, a host composing the persona's scope had nothing to compose for it, and
    that vertical's only repair was a deterministic BYPASS of the guard (``scope_lexicon`` in
    the host records three turns blocked over exactly this). A ``scope.txt`` puts the capability
    in the DEFINITION instead of in a detour around it.
    """
    companies = _flat(_scopes()["companies"])
    assert "{tenant_name}" in companies, "the scope must speak of the turn's tenant"
    for word in ("cnpj", "segment"):
        assert word in companies.lower(), word
    # the referent-dependent sentence the host's lexicon documents as measured-and-blocked
    assert "already named earlier in the conversation" in companies
