"""The SELLER's prompt slots — the persona is prompts only, so the file layout IS the contract.

The host loads exactly ``{system,scope,limits,voice}.txt`` from the package's prompts dir and a
MISSING slot does not raise: it loads as an empty string and the persona quietly runs without its
judge criteria or its voice. So the presence and the shape are worth asserting.

The SELLER (Vendedor) receives a contact who ALREADY wants to buy: it confirms the order, never
sums the TOTAL in its own head (the team confirms the final value with the payment), NEVER charges,
and hands the conversation to the human sales group through the human handoff. What it knows about
the product comes from the catalogue (``list_services``, when that tool is on the turn's table) and
from the DOCUMENTS the company published for it, read this turn with ``consult_documents`` — never a
fixed product block. The moment to read is when it confirms each item and its value.

Lives in ``tests/unit/`` because that is what CI RUNS: ``.github/workflows/ci.yml`` invokes
``pytest tests/unit`` and ``pytest tests/integration`` by name, never a bare ``pytest``."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "seller" / "prompts"
SLOTS = ("system", "scope", "limits", "voice")


@pytest.mark.parametrize("slot", SLOTS)
def test_every_slot_the_host_loads_exists_and_is_not_empty(slot):
    f = PROMPTS / f"{slot}.txt"
    assert f.exists(), f"the host loads {slot}.txt and an absent one degrades silently"
    assert len(f.read_text().strip()) > 80


def test_the_arc_is_ordered_welcome_confirm_total_handoff():
    system = (PROMPTS / "system.txt").read_text()
    for step in ("1. ACOLHIMENTO", "2. CONFIRMAÇÃO DO PEDIDO", "3. O TOTAL", "4. REGISTRO E PASSAGEM"):
        assert step in system


def test_the_seller_prompts_cite_the_documents_and_catalog_not_a_fixed_product_block():
    """The SELLER serves ANY company, so its prompts must not name a specific product. What it
    knows about the product comes from the catalogue and the company's DOCUMENTS, read this turn —
    not a fixed [PRODUTO] block, and not a product-specific build path."""
    system = (PROMPTS / "system.txt").read_text()
    limits = (PROMPTS / "limits.txt").read_text()
    for name, text in (("system.txt", system), ("limits.txt", limits)):
        assert not re.search(r"\bcogno\b", text, re.IGNORECASE), f"{name} names a specific product"
        assert not re.search(r"\bmcp\b", text, re.IGNORECASE), f"{name} names MCP, a product-specific path"
        assert "[PRODUTO]" not in text, f"{name} still points at the fixed product block"
        assert "documentos" in text.lower(), f"{name} must point the facts at the company's documents"
    assert "consult_documents" in system           # the tool that reads them this turn
    assert "list_services" in system                # the catalogue, when on the table
    voice = (PROMPTS / "voice.txt").read_text()
    assert "documentos da empresa" in voice and "[PRODUTO]" not in voice


def test_the_when_to_read_is_confirming_each_item_and_its_value():
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "O momento de consultar é a confirmação do pedido:" in system


def test_the_total_is_never_summed_in_the_sellers_head():
    """The total is what the team confirms, not arithmetic the seller invents — in the executor
    and in the judge alike."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    assert "NUNCA some o total de cabeça." in system
    assert "O TOTAL que o agente SOMOU de cabeça é um número inventado — REJEITE." in limits


def test_the_seller_never_charges_and_hands_the_order_to_the_human_team():
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    assert "NUNCA cobre" in system                  # never charges
    assert "nunca peça cartão nem Pix" in system
    assert "COBRANÇA — REJEITE SEMPRE." in limits    # the judge rejects a charge
    # the close is the handoff to the human sales group, not an escape hatch
    assert "passe a conversa ao grupo de vendas humano" in system
    assert "transferência para um atendente humano" in system


def test_the_judge_rubric_classifies_the_turn_then_ranks_truth_above_answering():
    limits = (PROMPTS / "limits.txt").read_text()
    flat = " ".join(limits.split())
    assert "## 0." in limits and "## 1. VERDADE" in limits and "## 2. RESPONDER" in limits
    assert limits.index("## 0.") < limits.index("## 1. VERDADE") < limits.index("## 2. RESPONDER")
    assert "A pessoa CONFIRMOU ou RESPONDEU" in flat and "A pessoa PERGUNTOU" in flat
    assert "catálogo nem nos documentos lidos neste turno" in flat
    assert "Forma NÃO é critério seu" in flat
