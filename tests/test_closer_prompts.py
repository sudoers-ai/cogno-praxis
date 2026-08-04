"""The CLOSER's prompt slots — the persona is prompts only, so the file layout IS the contract.

The host loads exactly `{system,scope,limits,voice}.txt` from the package's prompts dir and a
MISSING slot does not raise: it loads as an empty string and the persona quietly runs without
its judge criteria or its voice. So the presence and the shape are worth asserting."""

from __future__ import annotations

from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "closer" / "prompts"
SLOTS = ("system", "scope", "limits", "voice")


@pytest.mark.parametrize("slot", SLOTS)
def test_every_slot_the_host_loads_exists_and_is_not_empty(slot):
    f = PROMPTS / f"{slot}.txt"
    assert f.exists(), f"the host loads {slot}.txt and an absent one degrades silently"
    assert len(f.read_text().strip()) > 80


def test_the_arc_is_ordered_and_the_diagnosis_comes_before_the_pitch():
    system = (PROMPTS / "system.txt").read_text()
    for step in ("1. ABERTURA", "2. DIAGNÓSTICO", "3. DEVOLUTIVA", "4. ENCAIXE", "5. FECHAMENTO"):
        assert step in system
    # The rule the whole persona rests on — and the distinction that makes it survivable:
    # a live conversation died on it. The judge, reading "never talk product before act 3",
    # rejected every attempt to ANSWER a direct question about price, integration and how the
    # thing works, three times per turn, until the loop exhausted and the lead got
    # "sorry, I'll transfer you to an agent". Not offering ≠ not answering.
    assert "NUNCA **ofereça** produto antes do passo 3" in system
    assert "se ela PERGUNTAR" in system


def test_the_judge_rubric_ranks_truth_above_answering():
    """Both halves were learned from live conversations, in this order.

    First the judge rejected every attempt to ANSWER a direct question about price or
    integration ("never talk product before the recap"), three attempts per turn, until the
    loop exhausted and the lead got "I'll transfer you to an agent" — 4 of 11 turns.

    Then, told that answering was mandatory, it approved "Sim, o Cogno integra com o Bling" —
    an integration that appears nowhere. Answering had outranked being true. So the rubric is
    ORDERED now: truth first, then answering (with "I don't know" explicitly approvable), then
    rhythm."""
    limits = (PROMPTS / "limits.txt").read_text()
    flat = " ".join(limits.split())
    assert "## 1. VERDADE" in limits and "## 2. RESPONDER" in limits
    assert limits.index("## 1. VERDADE") < limits.index("## 2. RESPONDER")
    assert "não existe" in flat                       # an unlisted integration
    assert "Admitir limite É responder — APROVE." in flat
    assert "Não confunda **oferecer** com **responder**" in flat


def test_the_judge_classifies_the_contact_turn_before_judging_it():
    """Third live failure, and the one the two rules above could not fix.

    In a diagnosis MOST contact turns are answers, not requests. Handed "umas 30 por dia", the
    judge read it as a request, found the agent's next question did not "answer" it, and
    rejected — critique verbatim: "A resposta não atendeu ao pedido do usuário, que era sobre a
    quantidade de atendimentos". Three attempts, then the handoff text, on a turn where the
    agent had done exactly the right thing. So the rubric now classifies the contact's turn
    FIRST, and asking the next question is the approved outcome when they answered."""
    limits = (PROMPTS / "limits.txt").read_text()
    flat = " ".join(limits.split())
    assert "## 0." in limits
    # the classification has to come before every criterion it gates
    assert limits.index("## 0.") < limits.index("## 1. VERDADE")
    assert "A pessoa RESPONDEU" in flat and "A pessoa PERGUNTOU" in flat
    assert "não houve pedido" in flat
    # and the honest-limit answer needs an example, since the plain rule kept losing to the
    # judge's "give a direct answer" instinct
    assert "não está na lista de integrações" in flat


def test_an_explanation_is_not_rejected_for_being_long():
    """The "how does it work?" turn kept dying: explaining the pipeline does not fit the
    4-sentence budget a normal reply gets, and the judge rejected it three times per turn."""
    # normalize the file's own wrapping before matching a sentence that spans two lines
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    assert "pode usar até 8" in limits
    assert "não rejeite uma explicação boa por tamanho" in limits


def test_the_integration_trap_is_called_out_by_name():
    system = (PROMPTS / "system.txt").read_text().replace("\n", " ")
    assert "Integração é o caso mais perigoso" in system
    assert "NUNCA \"sim, integra\"" in system


def test_the_judge_can_approve_a_conversational_turn():
    """The default judge criterion is goal-vs-EXECUTION ("asked X, did X"). A consultative turn
    executes nothing, so without this escape hatch every good reply is rejected and the loop
    burns its retries — the same trap the BOOKKEEPER's limits.txt documents."""
    limits = (PROMPTS / "limits.txt").read_text()
    assert "NÃO exija que uma ação tenha sido realizada" in limits.replace("\n", " ")


def test_the_honesty_rules_are_present_because_they_are_what_make_it_credible():
    system = (PROMPTS / "system.txt").read_text()
    assert "NUNCA invente" in system
    assert "diga isso na cara e não force" in system      # walk away when it does not fit
    assert "responda a verdade" in system                 # "are you an AI?"


def test_the_voice_slot_carries_the_arc_because_short_answers_never_reach_the_executor():
    """Live finding: the contact answered "Claro" and the NER classified it SOCIAL, so the ID
    routed the turn to the SUPEREGO and the EXECUTOR never ran — meaning the five acts, which
    live in system.txt, were not consulted at all. The voicer alone wrote a generic line.

    A diagnosis is made of short answers ("claro", "uns 40", "só eu"), so this is the normal
    case, not an edge one. The landing chat solved the same problem by handing the executor's
    prompt to the voicer too; here the arc is restated in the voice slot."""
    voice = (PROMPTS / "voice.txt").read_text()
    assert "DIAGNÓSTICO" in voice
    for cue in ("canais de entrada", "volume", "quem responde", "fora do horário"):
        assert cue in voice.lower() or cue in voice
    # the specific turn that failed live
    assert "claro" in voice.lower()
    assert "nunca como pergunta nova" in voice


def test_the_voice_knows_how_to_open_a_conversation_it_started():
    """Live failure (2026-08-03): on a proactive opening the voicer saw "[ABERTURA]" in the
    user slot and no history, matched the arc's continuation rule — the only branch the voice
    slot had — and answered a contact who had said nothing: "Claro, Vinicius. Pode perguntar."
    The voice slot presumed the opening had already happened; on a turn the AGENT starts, it
    hasn't. So the opening is a branch of its own, and it comes FIRST."""
    voice = (PROMPTS / "voice.txt").read_text()
    flat = " ".join(voice.split())
    assert "[ABERTURA]" in voice
    assert "cumprimente pelo nome" in flat
    assert "peça licença para perguntar" in flat
    # the specific failure: opening with an answer to something nobody said
    assert 'NUNCA comece com "claro"' in flat
    # the opening branch must come before the continuation branch it was mistaken for
    assert flat.index("[ABERTURA]") < flat.index("acabou de pedir licença")


def test_the_persona_knows_where_its_product_facts_come_from():
    """The host injects a [PRODUTO] block (curated catalog + sales sheet). Without the prompt
    naming it, the model has a source it does not know it has — and the first live turn came
    out generic because it had nothing to say about the product."""
    system = (PROMPTS / "system.txt").read_text()
    voice = (PROMPTS / "voice.txt").read_text()
    for text in (system, voice):
        assert "[PRODUTO]" in text
        assert "única" in text.lower()          # it is the ONLY source
    # not knowing must produce "I don't know", never a plausible filler
    assert "Nunca preencha a lacuna" in system


def test_explaining_how_it_works_is_part_of_the_job():
    """A lead asks "how does this actually work?" — for a seller that is the work, not a
    digression. Every other persona stays product-blind (host-side flag)."""
    system = (PROMPTS / "system.txt").read_text()
    assert "como a solução funciona por dentro" in system
    assert "linguagem de negócio" in system


def test_the_close_does_not_promise_a_booking_it_cannot_make():
    """The persona is conversational: it has no scheduler. It used to borrow the tenant's
    MEDICAL agenda, where "let's talk 20 minutes" would book a consultation with an
    endocrinologist."""
    system = (PROMPTS / "system.txt").read_text()
    assert "NÃO tem agenda para marcar" in system
    # the close routes to a PERSON (see the handoff test below for when that is allowed)
    assert "Encaminhar para humano" in system


def test_handoff_is_the_close_not_an_escape_hatch():
    """`human_handoff` is a builtin in EVERY turn, and the arc's own "encaminhe para
    atendimento humano" line read as permission to use it whenever the model felt stuck. The
    production-faithful bench (escalation port wired) measured SEVEN escalations in one run —
    including on "isso é um robô?", which the persona must simply answer."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "Não é rota de fuga" in system
    assert "Encaminhar por não saber é pior que dizer" in system


def test_the_seller_sells_whoever_hired_it_not_only_cogno():
    """The persona was always tenant-agnostic in wording, but it declared the [PRODUTO] block
    the ONLY source — and that block is gated to the PLATFORM tenant, so any other tenant got
    a seller that had to answer "I don't know" about its own product. The tenant's own
    material arrives as `custom_rules` (rendered as "# Tenant-specific direction", and already
    handed to the judge as legitimate grounding), so it is a first-class source here."""
    system = " ".join((PROMPTS / "system.txt").read_text().split())
    assert "Tenant-specific direction" in system
    assert "produto de quem te contratou" in system
    # neither source present → still diagnoses, just does not pitch
    assert "Sem nenhuma das duas" in system
    assert "Diagnóstico não depende de catálogo" in system
