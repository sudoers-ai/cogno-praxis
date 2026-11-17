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


def test_satisfaction_is_measured_in_text_with_no_poll_tool():
    """Satisfaction is a plain question in the reply — a word or a 0–10 read — and the persona has
    no poll tool, in the executor and in the judge alike."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    assert "Você NÃO tem ferramenta de enquete" in system
    assert "meça **em texto**" in system
    assert "não a confunda com uma ferramenta de enquete, que esta persona não tem" in limits


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
