"""The pt clause negation reads «nada» and «nenhuma»/«nenhumas», as it reads «não» and «nenhum».

``LOCALES["pt"].neg`` is the clause-level negation every pt grounding backstop shares: the
verticals here (``affirmed``, ``_affirms_booking``) and the host's generic net, which imports
this same object. It had no «nada», and ``\\bnenhum\\b`` does not match «nenhuma» or
«nenhumas». So an honest «nada foi enviado» over a turn that wrote nothing was read as the
receipt it denies. Measured on a host's production traces: 4 replies and 1 draft blocked as
fabrications were this shape.

The scope does not move: it is the CLAUSE (``clauses``). «Não houve nada de errado, a consulta
foi marcada» still affirms in its second clause. Declared cost, the same class «não» already
has: «nada» inside the SAME clause as a claim masks the claim.

Invented sentences only.
"""

from __future__ import annotations

import re

import pytest

from cogno_praxis.grounding import LOCALES, NEG_RE, ToolCall, affirmed
from cogno_praxis.scheduler.grounding import ground_reply as sched_ground

NEG = LOCALES["pt"].neg

#: A stand-in for a reply vocabulary: the participles a receipt is written with.
_RECEIPT = re.compile(r"enviad[ao]s?|registrad[ao]s?|alterad[ao]s?|marcad[ao]s?", re.IGNORECASE)

#: The four shapes, written fresh. Each one is a RECEIPT the pin before this fix affirmed.
DENIALS = {
    "nada_enviado": "Nada foi enviado ao professor.",
    "nenhuma_mensagem": "Nenhuma mensagem foi enviada ainda.",
    "nenhumas_mensagens": "Nenhumas mensagens foram enviadas.",
    "nada_alterado": "Nada foi alterado no seu cadastro.",
}


@pytest.mark.parametrize("name", sorted(DENIALS))
def test_a_denial_is_not_affirmed(name: str):
    assert affirmed(DENIALS[name], _RECEIPT, neg=NEG) is False


def test_the_negation_already_read_stays():
    """«não» and «nenhum» were there before and stay: a control green in both worlds."""
    assert affirmed("Ainda não foi registrado nenhum lançamento.", _RECEIPT, neg=NEG) is False
    assert affirmed("Nenhum lançamento foi registrado.", _RECEIPT, neg=NEG) is False


def test_an_affirmative_receipt_is_still_affirmed():
    assert affirmed("A mensagem foi enviada ao professor.", _RECEIPT, neg=NEG) is True


def test_nada_in_another_clause_does_not_mask_the_claim():
    """The scope is the clause: the claim after the comma is still a claim."""
    assert affirmed("Não houve nada de errado, a consulta foi marcada para 10/11.",
                    _RECEIPT, neg=NEG) is True


@pytest.mark.parametrize("word", ["nada", "NADA", "Nada", "nenhuma", "NENHUMA", "nenhumas",
                                  "nenhum", "Nenhum"])
def test_the_words_are_matched_in_any_case(word: str):
    assert NEG.search(f"{word} foi enviado")


@pytest.mark.parametrize("text", ["Vamos nadar amanhã.", "O nadador chegou.",
                                  "Uma nadadeira nova.", "Nenhumaa foi enviada."])
def test_a_longer_word_is_not_the_negation(text: str):
    """Word boundaries: a word that only STARTS with «nada»/«nenhuma» is not a negation."""
    assert NEG.search(text) is None


def test_the_back_compat_name_is_the_same_object():
    """The module-level ``NEG_RE`` the older callers import is the locale's, not a copy."""
    assert NEG_RE is NEG


# ── through a real vertical: the scheduler's dated-booking affirmation ─────────────────────
_EMPTY = [ToolCall(tool="list_appointments", ok=True, result="No appointments found.")]


@pytest.mark.parametrize("reply", ["Nenhuma consulta foi marcada para 10/11.",
                                   "Nenhumas consultas foram marcadas para 10/11.",
                                   "Nada foi alterado na sua consulta de 10/11."])
def test_the_scheduler_does_not_read_a_denial_as_a_booking(reply: str):
    assert sched_ground(reply, tools=_EMPTY, locale="pt") is None


def test_the_scheduler_still_reads_a_booking():
    """The control, through the same rule: a dated booking over an empty listing."""
    v = sched_ground("A consulta foi marcada para 10/11.", tools=_EMPTY, locale="pt")
    assert v is not None and v.rule == "fabricated_booking"


def test_the_scheduler_reads_the_claim_in_the_next_clause():
    v = sched_ground("Não houve nada de errado, a consulta foi marcada para 10/11.",
                     tools=_EMPTY, locale="pt")
    assert v is not None and v.rule == "fabricated_booking"
