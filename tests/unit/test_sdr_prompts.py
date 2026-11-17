"""The SDR's prompt slots — the persona is prompts only, so the file layout IS the contract.

The host loads exactly ``{system,scope,limits,voice}.txt`` from the package's prompts dir and a
MISSING slot does not raise: it loads as an empty string and the persona quietly runs without its
judge criteria or its voice. So the presence and the shape are worth asserting.

The SDR is the first-contact TRIAGE persona, built on the CLOSER mould: it qualifies whoever
arrives and either sets up a short conversation with the human team or says plainly it is not a
fit. It presents no proposal, quotes no closed price and never charges. What it knows about the
product comes from the DOCUMENTS the company published for it, read this turn with
``consult_documents`` — never a fixed product block, and NEVER during the triage: only when the
person asks about price or a feature.

Lives in ``tests/unit/`` because that is what CI RUNS: ``.github/workflows/ci.yml`` invokes
``pytest tests/unit`` and ``pytest tests/integration`` by name, never a bare ``pytest``."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "sdr" / "prompts"
SLOTS = ("system", "scope", "limits", "voice")


@pytest.mark.parametrize("slot", SLOTS)
def test_every_slot_the_host_loads_exists_and_is_not_empty(slot):
    f = PROMPTS / f"{slot}.txt"
    assert f.exists(), f"the host loads {slot}.txt and an absent one degrades silently"
    assert len(f.read_text().strip()) > 80


def test_the_arc_is_ordered_triage_then_fit_then_next_step():
    system = (PROMPTS / "system.txt").read_text()
    for step in ("1. ABERTURA", "2. TRIAGEM", "3. ENCAIXE", "4. PRÓXIMO PASSO"):
        assert step in system


def test_the_sdr_prompts_cite_the_documents_not_a_fixed_product_block():
    """The SDR serves ANY company, so its prompts must not name a specific product. What it knows
    about the product comes from the DOCUMENTS the company published, read this turn with
    ``consult_documents`` — not a fixed [PRODUTO] block, and not a product-specific build path."""
    system = (PROMPTS / "system.txt").read_text()
    limits = (PROMPTS / "limits.txt").read_text()
    for name, text in (("system.txt", system), ("limits.txt", limits)):
        assert not re.search(r"\bcogno\b", text, re.IGNORECASE), f"{name} names a specific product"
        assert not re.search(r"\bmcp\b", text, re.IGNORECASE), f"{name} names MCP, a product-specific path"
        assert "[PRODUTO]" not in text, f"{name} still points at the fixed product block"
        assert "documentos" in text.lower(), f"{name} must point the facts at the company's documents"
    assert "consult_documents" in system           # the tool that reads them this turn
    # the voice points at the same source, not the old fixed block
    voice = (PROMPTS / "voice.txt").read_text()
    assert "documentos da empresa" in voice and "[PRODUTO]" not in voice


def test_the_when_to_read_is_the_role_s_moment_never_the_triage():
    """The SDR reads the documents at ONE moment, and it is not the triage: only when the person
    asks about price or a feature. The diagnosis/triage questions live in the prompt, not the
    documents, so during the triage it reads nothing."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "Durante a triagem você não consulta documentos." in system
    assert "Só quando a pessoa perguntar preço ou funcionalidade" in system


def test_the_triage_presents_no_proposal_and_never_charges():
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "não apresenta proposta" in system
    assert "não cobra" in system


def test_the_judge_rubric_classifies_the_turn_then_ranks_truth_above_answering():
    limits = (PROMPTS / "limits.txt").read_text()
    flat = " ".join(limits.split())
    assert "## 0." in limits and "## 1. VERDADE" in limits and "## 2. RESPONDER" in limits
    assert limits.index("## 0.") < limits.index("## 1. VERDADE") < limits.index("## 2. RESPONDER")
    assert "A pessoa RESPONDEU" in flat and "A pessoa PERGUNTOU" in flat
    assert "documentos lidos neste turno" in flat, "the judge grounds truth in this turn's documents"
    assert "Admitir limite É responder — APROVE." in flat
    # form is the writer's business, not the judge's
    assert "Forma NÃO é critério seu" in flat


def test_the_honesty_rules_and_the_handoff_is_not_an_escape_hatch():
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "NUNCA invente" in system
    assert "diga isso na cara e não force" in system     # walk away when it does not fit
    assert "responda a verdade" in system                # "are you an AI?"
    assert "Não é rota de fuga" in system                # the handoff is not an escape hatch
