"""The AFTERSALES prompt slots — the persona is prompts only, so the file layout IS the contract.

The host loads exactly ``{system,scope,limits,voice}.txt`` from the package's prompts dir and a
MISSING slot does not raise: it loads as an empty string and the persona quietly runs without its
judge criteria or its voice. So the presence and the shape are worth asserting.

AFTERSALES (Pós-venda) enters after the sale, with the customer already using the product: it
checks in, answers usage questions, measures satisfaction IN TEXT (it has no poll tool), and
catches early the signal that a customer might leave. It does not charge and does not renegotiate
price on its own initiative. What it knows about the product comes from the DOCUMENTS the company
published for it, read this turn with ``consult_documents`` — never a fixed product block. The
moment to read is a usage doubt.

Lives in ``tests/unit/`` because that is what CI RUNS: ``.github/workflows/ci.yml`` invokes
``pytest tests/unit`` and ``pytest tests/integration`` by name, never a bare ``pytest``."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "aftersales" / "prompts"
SLOTS = ("system", "scope", "limits", "voice")


@pytest.mark.parametrize("slot", SLOTS)
def test_every_slot_the_host_loads_exists_and_is_not_empty(slot):
    f = PROMPTS / f"{slot}.txt"
    assert f.exists(), f"the host loads {slot}.txt and an absent one degrades silently"
    assert len(f.read_text().strip()) > 80


def test_the_arc_is_ordered_checkin_listen_satisfaction_path():
    system = (PROMPTS / "system.txt").read_text()
    for step in ("1. CHECK-IN", "2. ESCUTA E RESOLVE", "3. SATISFAÇÃO", "4. CAMINHO"):
        assert step in system


def test_the_aftersales_prompts_cite_the_documents_not_a_fixed_product_block():
    """The persona serves ANY company, so its prompts must not name a specific product. What it
    knows about the product comes from the company's DOCUMENTS, read this turn with
    ``consult_documents`` — not a fixed [PRODUTO] block, and not a product-specific build path."""
    system = (PROMPTS / "system.txt").read_text()
    limits = (PROMPTS / "limits.txt").read_text()
    for name, text in (("system.txt", system), ("limits.txt", limits)):
        assert not re.search(r"\bcogno\b", text, re.IGNORECASE), f"{name} names a specific product"
        assert not re.search(r"\bmcp\b", text, re.IGNORECASE), f"{name} names MCP, a product-specific path"
        assert "[PRODUTO]" not in text, f"{name} still points at the fixed product block"
        assert "documentos" in text.lower(), f"{name} must point the facts at the company's documents"
    assert "consult_documents" in system           # the tool that reads them this turn
    voice = (PROMPTS / "voice.txt").read_text()
    assert "documentos da empresa" in voice and "[PRODUTO]" not in voice


def test_the_when_to_read_is_a_usage_doubt():
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "O momento de consultar é uma dúvida de uso:" in system


def test_satisfaction_is_measured_in_text():
    """Satisfaction is measured IN TEXT — a word or a 0–10 read, living in the conversation. The
    old poll-tool directive («se houver uma ferramenta de enquete entre as do turno, use-a») is
    gone from the system: this persona has no poll tool, and the earlier fixed absence of one is
    gone too. The judge's limits clause is unchanged in this change and still guards against
    confusing the text measure with a poll tool."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    assert "Você NÃO tem ferramenta de enquete" not in system      # the fixed absence is gone
    assert "se houver uma ferramenta de enquete entre as do turno, use-a" not in system.lower()
    assert "meça **em texto**" in system
    assert "não a confunda com uma ferramenta de enquete, que esta persona não tem" in limits


def test_the_satisfaction_examples_are_business_neutral_not_the_products_own_pain():
    """The satisfaction check's example answers must be neutral — words a customer of ANY business
    might use, not a specific product's own pain. The old examples cited a busy-morning workload
    («hoje a manhã está 'tranquila', 'corrida' ou 'um caos'»), which only one kind of business
    lives; the closed question and the short-answer examples are now neutral and identical across
    the three slots that carry them."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    voice = (PROMPTS / "voice.txt").read_text()
    limits = (PROMPTS / "limits.txt").read_text()
    # the new, neutral closed question in the system
    assert "está 'ótimo', 'ok' ou 'ruim'?" in system
    # the short-answer example set is the same in the voice and in the judge's limits
    assert '"ótimo", "ok", "uns 7"' in voice
    assert '"ótimo", "ok", "uns 7"' in limits
    # the product's-own-pain example is gone from every slot that carried it
    for name, text in (("system.txt", system), ("voice.txt", voice), ("limits.txt", limits)):
        for pain in ("hoje a manhã", "um caos", "corrida", "tranquila"):
            assert pain not in text, f"{name} still cites the busy-morning example: {pain}"


def test_the_persona_does_not_charge_or_renegotiate_on_its_own():
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    assert "NUNCA cobre nem renegocie preço por iniciativa própria." in system
    assert "Cobra ou renegocia preço por iniciativa própria — REJEITE." in limits


def test_the_judge_rubric_classifies_the_turn_then_ranks_truth_above_answering():
    limits = (PROMPTS / "limits.txt").read_text()
    flat = " ".join(limits.split())
    assert "## 0." in limits and "## 1. VERDADE" in limits and "## 2. RESPONDER" in limits
    assert limits.index("## 0.") < limits.index("## 1. VERDADE") < limits.index("## 2. RESPONDER")
    assert "O cliente RESPONDEU" in flat and "O cliente PERGUNTOU" in flat
    assert "documentos lidos neste turno" in flat
    assert "Forma NÃO é critério seu" in flat


def test_the_company_rules_govern_the_how():
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "As regras de quem te contratou" in system
    assert "mandam no COMO" in system
    assert '# Tenant-specific direction' in system


def test_the_voice_carries_the_onboarding_checklist_clause():
    voice = " ".join((PROMPTS / "voice.txt").read_text().split())
    assert "bloco de onboarding" in voice
    assert "SUBSTITUI enquanto existir" in voice


def test_the_handoff_fallback_promises_no_action_without_a_tool_and_is_never_a_mere_notice():
    """When there is no way to pass to a person now, say so plainly and keep helping — but NEVER
    promise someone will do something (reach out, send, schedule, pass a message) without a tool on
    the turn that performs it. The old fallback promised the team «entra em contato por este mesmo
    canal» even when nothing could, which the judge rejected; that promise is gone. And the handoff
    puts the conversation in HUMAN mode — never used alone as a «notice»: only on the customer's
    yes."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "Se não houver como passar a conversa a uma pessoa agora" in system
    assert "Nunca prometa que alguém vai fazer algo" in system
    assert "se não houver no turno uma ferramenta que o faça" in system
    assert "põe a conversa no modo humano" in system
    # the old, unconditional promise is gone
    assert "entra em contato por este mesmo canal" not in system


def test_the_new_opportunity_offers_the_seller_and_does_no_sale_discovery():
    """An opportunity (the customer wants more) is the SELLER's, not the after-sales persona's: it
    must NOT ask what the customer wants to buy (sale discovery). WITH a way to pass the
    conversation on this turn it offers and only passes on yes; WITHOUT one it says plainly it
    cannot pass the conversation here, keeps helping — and NEVER asks whether to forward nor
    promises someone will reach out. No «registre» — nothing records."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "NÃO pergunte o que ele quer comprar" in system
    assert "isso é do vendedor" in system
    assert "OFEREÇA e só passe no sim" in system
    assert "por aqui você não consegue passar a conversa agora" in system
    assert "registre" not in (PROMPTS / "system.txt").read_text()


def test_the_handoff_is_never_offered_as_a_question_without_a_tool():
    """WITHOUT a tool that can pass the conversation on the turn, the persona says so plainly and
    keeps helping — it never asks «quer que eu encaminhe?» and never promises that someone will
    contact the customer. The rule is carried by BOTH the executor's system prompt and the
    voicer's prompt; the old «pergunte se quer que alguém fale com» wording is gone from both."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    voice = " ".join((PROMPTS / "voice.txt").read_text().split())
    assert "nunca pergunte se ele quer que você encaminhe" in system
    assert "nunca pergunte se ele quer que você encaminhe" in voice
    assert "pergunte se quer que alguém fale com" not in system
    assert "pergunte se quer que alguém fale com" not in voice
