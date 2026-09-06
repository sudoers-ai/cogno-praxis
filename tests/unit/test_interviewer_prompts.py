"""The INTERVIEWER's prompt slots — prompt-only persona contract tests.

The host loads `{system,scope,limits,voice}.txt` from the package's prompts dir. The first
three tests are the ones the persona arrived with (2026-09-04, uncommitted in the served
checkout); the twins below them are what made it committable — each names the defect it
pins, and each was measured or grepped before being written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "interviewer" / "prompts"
SLOTS = ("system", "scope", "limits", "voice")


@pytest.mark.parametrize("slot", SLOTS)
def test_every_slot_the_host_loads_exists_and_is_not_empty(slot: str) -> None:
    f = PROMPTS / f"{slot}.txt"
    assert f.exists(), f"the host loads {slot}.txt and an absent one degrades silently"
    assert len(f.read_text().strip()) > 50


def test_interviewer_voice_rules() -> None:
    voice = (PROMPTS / "voice.txt").read_text()
    assert "uma pergunta por mensagem" in voice.lower()
    assert "resumo consolidado" in voice.lower() or "resumo" in voice.lower()


def test_interviewer_limits_rules() -> None:
    limits = (PROMPTS / "limits.txt").read_text()
    assert "VERDADE" in limits
    assert "RITMO E FOCO" in limits


# ── twins (2026-09-05) ──────────────────────────────────────────────────────────────────
#
# The host renders the VOICE slot with two placeholders filled and, when the tenant declared a
# checklist, its own block appended at the tail (`cogno_host/persona.py: _assemble`, voice
# ONLY). The header is the host's (`intake.render_block`); the prompt points at it by its
# words, never at the list — the same contract the CLOSER's twins pin.
_HOST_BLOCK_HEADER = "# Onboarding — ainda falta descobrir (REGRA DURA desta resposta)"


def _render_voice(block: str = "") -> str:
    text = ((PROMPTS / "voice.txt").read_text()
            .replace("{identity_label}", "Marina").replace("{tenant_name}", "Acme"))
    return f"{text}\n\n{block}" if block else text


def test_the_persona_does_not_name_itself() -> None:
    """The served draft opened with "Seu nome padrão de atendimento é Carol". No other persona
    in this package names itself (grep over every prompts dir: empty) — the name is the
    tenant's (`tenant_personas.display_name`, rendered by the host's identity block into the
    voice and limits slots), and a name baked into the base prompt would fight the one the
    tenant configured on every turn."""
    for slot in SLOTS:
        text = (PROMPTS / f"{slot}.txt").read_text()
        assert "Carol" not in text and "nome padrão" not in text, slot
    system = (PROMPTS / "system.txt").read_text()
    assert "{tenant_name}" in system and "{identity_label}" in system


def test_the_base_prompt_carries_no_domain_script() -> None:
    """The served draft shipped a canonical campaign table (Tema/Objetivo/Formato·CTA,
    Carrossel, Reel) and a "datas comemorativas" section in the BASE voice — the same shape as
    the CLOSER's measured defect: a script in the base prompt plus the same script in the
    tenant's `custom_rules` ("Planejamento de Campanhas Mensais") is two sources for one
    instruction. A generic interviewer has no domain of its own; the deliverable's format is
    the tenant's to declare, and the base says so."""
    for slot in SLOTS:
        low = (PROMPTS / f"{slot}.txt").read_text().lower()
        for word in ("campanha", "carrossel", "reel", "comemorativ", "tema sugerido", "| semana"):
            assert word not in low, (slot, word)
    voice = " ".join((PROMPTS / "voice.txt").read_text().split())
    assert "é o que as regras de quem te contratou pedirem" in voice
    assert "não traz um roteiro próprio" in voice


def test_with_the_checklist_block_the_opening_asks_the_first_item_not_permission() -> None:
    """The owner's t86 corpus, which today talks to THIS persona: to "Oi", the reply must ask
    the block's first item — no permission for a battery, no announcement of one — and drop a
    draft that carries either. Same rule, same words, as the CLOSER's (measured there 0/4 →
    4/4 on the production group); the A/B on this persona is in the host PR."""
    flat = " ".join(_render_voice(_HOST_BLOCK_HEADER + "\n- (the tenant's item)").split())
    rule = flat[flat.index("Se o contexto trouxer um bloco de onboarding"):flat.index("SEM esse bloco")]
    assert "FAÇA a primeira pergunta do bloco" in rule
    assert "sem pedir licença para perguntar" in rule
    assert "sem anunciar quantas perguntas virão" in rule
    assert "NÃO transmita" in rule                                   # the executor's draft
    assert "cumprimente pelo nome" in rule and "de onde você fala" in rule
    assert "ainda falta descobrir" in rule                           # the host header's words


def test_without_a_checklist_the_interviewer_conducts_whatever_the_tenant_declared() -> None:
    """Gémeo: no block → the questions come from the tenant's direction, and with neither the
    persona asks what the person wants to record. It never falls back to a campaign script,
    because it has none (the test above). The block is absent on a proactive opening, for
    SUPERVISOR/ADMIN, after the intake budget, and for a tenant row with no items."""
    flat = " ".join(_render_voice(block="").split())
    assert "ainda falta descobrir (REGRA DURA" not in flat
    tail = flat[flat.index("SEM esse bloco"):]
    assert "Tenant-specific direction" in tail
    assert "pergunte o que a pessoa quer registrar" in tail
    # the conduction survives without a list: one question, progress, correction, summary
    for cue in ("Uma pergunta por vez", "Indicador de progresso", "Flexibilidade e correção",
                "Fechamento e validação consolidada"):
        assert cue in flat, cue


def test_the_executor_knows_the_list_lives_in_the_voice_slot() -> None:
    """The executor never receives the checklist block (host: voice-only). The served draft's
    system slot said nothing about where questions come from; this one says it has no script
    of its own and that the list reaches the voice stage, not the executor — so its draft
    records the answer instead of inventing the next question."""
    flat = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "Você não traz um roteiro próprio" in flat
    assert "a etapa de voz recebe a lista do que ainda falta descobrir; você não" in flat
    assert "Tenant-specific direction" in flat
    assert "NUNCA invente um dado" in flat


def test_the_judge_has_no_calendar() -> None:
    """The served limits said "Rejeite se apresentar datas com dias da semana incorretos". The
    judge is an LLM without a calendar: it would reject correct replies (the class measured
    this week — the judge rejecting honesty three times per turn). Calendar is judged only
    against a verifiable datum in the context (the `[HOJE]` anchor / `resolve_date`), and a
    weekday computed in the judge's head is named as something it must NOT reject on."""
    limits = (PROMPTS / "limits.txt").read_text()
    flat = " ".join(limits.split())
    assert "dias da semana incorretos" not in flat
    assert "[HOJE]" in flat and "resolve_date" in flat
    assert "Sem âncora no contexto, não julgue calendário" in flat
    assert "nunca rejeite por um dia da semana que você calculou de cabeça" in flat
    assert limits.index("## 0.") < limits.index("## 1. VERDADE") < limits.index("## 2. RITMO")


def test_one_question_per_message_is_the_voices_rule_and_the_judge_no_longer_repeats_it() -> None:
    """`limits.txt` and `voice.txt` reach DIFFERENT calls — `cogno_host/persona.py`'s
    SLOT_TO_LAYER sends "limits" to the judge and "voice" to the voicer, and nothing merges
    them. "Two questions in one turn" is an instruction about writing a message, and the voice
    slot already carried it twice (the conduction rule and the # Forma line), so as a judge
    criterion it bought a rejection of a reply nobody could rewrite into fewer questions
    without re-running the turn — while costing its tokens on every judge call.

    What STAYS is deliberately not symmetric with the CLOSER's move. Pushing a sale is SCOPE.
    And "ignorou a resposta e refez a mesma pergunta" stays because the machinery that backs
    the CLOSER's version does not exist here: `cogno_host/arc.py`'s `_ARCS` registry holds
    only "closer", so this persona gets no `[ARCO]` state marking a question answered. The
    host's checklist block covers the declared-list path (it renders PENDING items only, so an
    answered one never reappears) and the anti-repeat guard covers a near-duplicate reply, but
    neither reaches a re-asked question that is worded fresh outside a checklist. Moving this
    one would trade a criterion for nothing."""
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    voice = " ".join((PROMPTS / "voice.txt").read_text().split())
    assert "apenas uma pergunta por mensagem" in voice
    assert "uma interrogação por mensagem" in voice
    assert "duas perguntas no mesmo turno" not in limits
    assert "empurrar propostas comerciais" in limits          # scope stays
    assert "refazer a mesma pergunta" in limits               # unbacked here — stays


def test_the_scope_guard_is_told_that_bare_answers_are_the_normal_message() -> None:
    """The INTERVIEWER is not `conversational` (that host flag would also drop the notify /
    profile / remind families the owner wants her to have), so the scope guard runs on every
    turn — and an interview is made of bare answers. Measured on the guard alone
    (gpt-4o-mini, no NER bypass, N=6 per input): the served scope.txt blocked "umas 3 por
    semana" 4/6 and "umas 3" 3/6 with "Desculpe, mas não posso ajudar…"; this text, 0/6 on
    all four inputs ("umas 3 por semana", "Outubro de 2026", "umas 3", "sim"). It also showed
    once in the bench A/B (1/4 third turns refused). The guard still blocks abuse."""
    scope = " ".join((PROMPTS / "scope.txt").read_text().split())
    assert "RESPOSTA curta" in scope
    assert "TODA resposta curta está DENTRO do escopo" in scope
    for example in ('"umas 3"', '"Outubro de 2026"', '"sim"/"não"'):
        assert example in scope, example
    assert "BLOQUEIE apenas mensagens abusivas" in scope
    assert "Em dúvida, PERMITA" in scope
