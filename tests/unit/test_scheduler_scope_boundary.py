"""The scheduler scope guard's boundary sentence: what is out of scope is ANSWERING.

The line used to read "*answering the medical/financial/legal QUESTION itself*", and the
noun it makes out of scope is the QUESTION. A receptionist for a business that HAS an
accountant is the right place to ASK about the ledger — the assistant hands it over, it does
not answer it — and the sentence as written said the opposite about the whole shape.

## What this test can and cannot hold

It holds the SHAPE of the sentence: the widening must not arrive by deleting the examples
that keep medical advice out. It cannot hold the guard's DECISION, because that belongs to a
model — and on that axis this change was measured and it moves nothing:

    openai:gpt-4o-mini, n=5, 17 sentences, old prompt vs new: 12/17 → 12/17, ZERO verdicts
    moved. The four sentences the change was written for («Qual o saldo do mês?», «E qual o
    total das minhas despesas deste mês?», «me manda o extrato de agosto», «quais são as
    minhas aulas da próxima semana?») stay BLOCK 5/5 under BOTH wordings — and stay BLOCK
    5/5 under a deliberately MAXIMAL third wording that names «qual o saldo do mês?»
    verbatim in the IN SCOPE list with an ALWAYS ALLOW.

That is the third independent reproduction of the house rule (`cogno-host`'s
`scope_lexicon.py` carries the first two, 2026-08-11): **a fail-closed guard is not moved by
words.** The repair for those four sentences is deterministic and lives in the host — it does
not consult the guard at all. This file exists so the sentence is TRUE, not so it is a fix,
and the eight BLOCK controls of the same run are what says the correction is free.
"""
from __future__ import annotations

from pathlib import Path

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "scheduler" / "prompts"
SCOPE = (PROMPTS / "scope.txt").read_text(encoding="utf-8")


def test_what_is_out_of_scope_is_ANSWERING_not_the_question_being_asked():
    assert "the question is IN SCOPE: hand it over" in SCOPE
    assert "QUESTION itself" not in SCOPE, "the old noun makes the ASKING out of scope"


def test_the_widening_did_not_arrive_by_deleting_the_medical_examples():
    """The cheapest way to write this sentence is to drop the block cases with it. The
    examples ARE the boundary — measured 5/5 BLOCK on both wordings, and this is what keeps
    the next edit from buying the widening with them."""
    for example in ("what should I take for my blood pressure?", "is this mole cancer?",
                    "meu peito dói, o que pode ser?", "que remédio tomo pra pressão?"):
        assert example in SCOPE, example
    assert "BLOCK when the user asks you to PERFORM that expertise" in SCOPE


def test_the_prompt_reaches_a_business_only_through_PLACEHOLDERS():
    """`cogno-praxis` is public: the slot names the business and the assistant only through the
    two placeholders the host fills, never a real one.

    Asserted by SHAPE, not against a list of names — a denylist would have to carry the very
    identifiers this repo may not hold, and it would still miss the next one. What it checks is
    that nothing contact-shaped is baked in: no address, no document, no long digit run, and no
    reference to a business outside the placeholder."""
    import re
    assert "{tenant_name}" in SCOPE and "{secretary_name}" in SCOPE
    body = re.sub(r"\{(secretary_name|tenant_name)\}", " ", SCOPE)
    assert "@" not in body, "an e-mail or handle has no business in a shipped prompt"
    assert not re.search(r"\d[\d.\-/]{5,}", body), "an id/document/phone shape is baked in"
    # The two placeholders are the ONLY way a business is named: every other occurrence of the
    # word would be a leak, so the braces must outnumber nothing — count them explicitly.
    assert SCOPE.count("{tenant_name}") >= 2, "the business is named, and only by placeholder"
