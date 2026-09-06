"""The CLOSER's prompt slots — the persona is prompts only, so the file layout IS the contract.

The host loads exactly `{system,scope,limits,voice}.txt` from the package's prompts dir and a
MISSING slot does not raise: it loads as an empty string and the persona quietly runs without
its judge criteria or its voice. So the presence and the shape are worth asserting.

Lives in `tests/unit/` because that is what CI RUNS: `.github/workflows/ci.yml` invokes
`pytest tests/unit` and `pytest tests/integration` by name, never a bare `pytest`. At the
`tests/` root this file was collected only by a local run — 18 tests about the persona's whole
contract, every one of them dark on every PR. A guard nobody runs is not a guard."""

from __future__ import annotations

import re
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
    ORDERED now: truth first, then answering (with "I don't know" explicitly approvable).
    Rhythm used to be criterion 3 here; it is the voice's business and moved to `voice.txt`."""
    limits = (PROMPTS / "limits.txt").read_text()
    flat = " ".join(limits.split())
    assert "## 1. VERDADE" in limits and "## 2. RESPONDER" in limits
    assert limits.index("## 1. VERDADE") < limits.index("## 2. RESPONDER")
    # Integração tem DUAS metades, e a regra mudou por decisão do dono do produto: o Cogno
    # conecta a qualquer sistema com API via MCP. O absoluto antigo ("não existe") tornava a
    # metade construível impronunciável e o juiz aprovava meia verdade — o que custava a venda.
    # O que NÃO pode afrouxar é a outra metade: afirmar que JÁ integra segue sendo o pior erro.
    assert "não está\n  PRONTA" in limits or "não está PRONTA" in flat
    assert "pior erro possível" in flat                # claiming a ready-made one still is
    assert "MCP" in limits, "the buildable half must be sayable"
    assert "prazo, preço ou esforço" in flat, "promising the build is still forbidden"
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


def test_length_is_the_writers_business_and_the_judge_has_no_criterion_for_it():
    """The "how does it work?" turn kept dying: explaining the pipeline does not fit the
    4-sentence budget a normal reply gets, and the judge rejected it three times per turn.
    The carve-out was written into the JUDGE's rubric, which is the wrong stage twice over.

    The two slots are DISJOINT — `limits.txt` renders into `limits_prompt` (the judge) and
    `voice.txt` into `voice_prompt` (the voicer); `cogno_host/persona.py: SLOT_TO_LAYER` maps
    "limits"→judge and "voice"→voice and nothing merges them. So the length budget was paid
    in input tokens on every judge call, and the model that actually decides how long a reply
    is never read it. Both halves of the budget now instruct the WRITER, and the judge is left
    with no length criterion to reject over — which is stronger than the carve-out was."""
    # normalize each file's own wrapping before matching a sentence that spans two lines
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    voice = " ".join((PROMPTS / "voice.txt").read_text().split())
    assert "até 4 frases" in voice
    assert "até 8 frases" in voice                       # the explanation carve-out
    assert "não se alongue sem motivo" in voice          # ...and its ceiling
    # nothing MEASURABLE about length left in the judge's rubric: the only surviving mention
    # of "frases" is the guard that tells it length is not its criterion (asserted below), so
    # the property is "no sentence BUDGET", not "the word never appears".
    assert not re.search(r"\d+\s+frases", limits)
    assert "Forma NÃO é critério seu" in limits


def test_the_rhythm_rules_instruct_the_voice_instead_of_gating_the_judge():
    """The other three §3 RITMO bullets, each in the slot that can act on it.

    One question per message, not re-asking what is already answered, and not pressing an
    invitation the contact declined are instructions about WRITING a message. A judge can only
    reject the finished reply — and the CLOSER is rejected ~1% of the time, so as a judge
    criterion these bought almost no corrections while costing their tokens on every call.

    The re-ask rule is the one with real machinery behind it, and it is the host's, not this
    file's: `cogno_host/arc.py` keeps per-session state of which diagnosis question was
    ANSWERED, `render_arc_stamp` emits it as "JÁ RESPONDIDO" lines plus the order "NÃO repita
    nenhuma pergunta marcada como JÁ RESPONDIDA", and `arc_voice_section` puts that block in
    the VOICE prompt — for the measured reason that the voicer is the stage that re-asks. So
    this bullet is not being demoted from a guarantee to a request: it is being written next
    to the state that answers it."""
    limits = " ".join((PROMPTS / "limits.txt").read_text().split())
    voice = " ".join((PROMPTS / "voice.txt").read_text().split())
    # one question, one subject
    assert "sobre UM assunto só" in voice
    assert "duas perguntas sobre assuntos diferentes" in voice
    assert "assuntos diferentes" not in limits
    # do not re-ask what the host's arc block marks answered
    assert "[ARCO]" in voice and "JÁ RESPONDIDO" in voice
    assert "[ARCO]" not in limits
    # no insisting, no scarcity, no pressure
    assert "escassez ou pressão" in voice
    assert "escassez" not in limits
    # and the section is gone as a section: the word "ritmo" survives nowhere in the rubric,
    # including the closing line that used to name it as a criterion.
    assert "ritmo" not in limits.lower()
    assert "honestidade e resposta, não execução" in limits


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


def test_the_voice_defers_to_the_configured_checklist_without_losing_its_questions():
    """The next diagnosis question has TWO sources now, and the order between them matters.

    The host injects the persona's configured intake list into the VOICE slot only — a block
    headed "Onboarding — ainda falta descobrir" with the items still pending
    (`cogno_host/persona.py`: the append is gated on `slot == "voice"`; the EGO system slot is
    deliberately denied it). So the voice slot must DEFER to that block when it arrives.

    But it does not arrive on every turn: it is skipped on a proactive opening and for
    SUPERVISOR/ADMIN roles, it stops after the intake ride budget, and a tenant whose persona
    row carries no items gets nothing — the turn path reads the DB row and never falls back to
    the spec default. On each of those turns the voice slot is the ONLY thing the voicer has,
    which is the same reason the arc lives here at all (see the test above). So the written
    chain STAYS, as the fallback, and both halves are asserted: a pointer with no fallback
    would be a prompt that names a mechanism the turn may not have.
    """
    voice = (PROMPTS / "voice.txt").read_text()
    flat = " ".join(voice.split())
    # the pointer, in the words the injected block itself uses
    assert "ainda falta descobrir" in flat
    assert "checklist de primeiro" in flat
    # ...and the precedence between the two sources, stated
    assert "manda mais que a ordem abaixo" in flat
    # ...and the fallback the test above pins, reachable WITHOUT the block
    assert "SEM esse bloco" in flat
    assert flat.index("SEM esse bloco") < flat.index("canais de entrada")


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


# ── the checklist block owns the opening (2026-09-05) ──────────────────────────────────
#
# The host renders the VOICE slot as this file with two placeholders filled
# (`cogno_host/persona.py: render_slot`) and, when the tenant declared a checklist, its own
# block appended at the tail (`_assemble`: voice ONLY — the executor never sees it). A
# prompts-only persona has no renderer, so these twins render the way the host does — once
# without the block, once with it — instead of reading the file as one string.
#
# The header is the HOST's (`cogno_host/intake.py: render_block`, pinned there by
# `test_intake.py`). It is quoted here because it is the one thing this persona knows about
# the block — the prompt points at it by its words, never at the list, which stays the host's:
# a source is one. If the host renames the header, the prompt's pointer dies silently and this
# constant is where the drift becomes visible.
_HOST_BLOCK_HEADER = "# Onboarding — ainda falta descobrir (REGRA DURA desta resposta)"


def _render_voice(block: str = "") -> str:
    text = ((PROMPTS / "voice.txt").read_text()
            .replace("{identity_label}", "Marina").replace("{tenant_name}", "Acme"))
    return f"{text}\n\n{block}" if block else text


def test_without_the_checklist_block_the_base_script_still_runs():
    """Gémeo 1: a persona with nothing declared renders NO block, and for it the written
    script must keep running — the opening asks permission, the chain is the next-question
    rule. Every sentence that suspends the script has to be CONDITIONED on the block: an
    unconditional suspension would silence a tenant that has no list.

    Mutation: drop "enquanto o bloco existir" from the suspension sentence and this dies."""
    rendered = _render_voice(block="")
    flat = " ".join(rendered.split())
    assert "ainda falta descobrir (REGRA DURA" not in rendered       # no block on this turn
    assert "peça licença para perguntar" in flat                      # the opening, as before
    assert "canais de entrada → volume por dia → quem responde" in flat
    for sentence in re.split(r"(?<=[.!?])\s+", flat):
        if "SUSPENSO" in sentence:
            assert "bloco" in sentence, f"unconditional suspension: {sentence!r}"
    # the fallback is stated as the no-block path and precedes the chain it introduces
    assert "SEM esse bloco" in flat
    assert flat.index("SEM esse bloco") < flat.index("canais de entrada")


def test_with_the_checklist_block_the_opening_asks_the_item_not_permission():
    """The owner's t86 (2026-09-04 ~03:35, CLOSER, EMPLOYEE): to "Oi" the reply welded the
    presentation, a promise of "três perguntas rápidas" and one checklist item; two turns later
    it asked the "volume diário", which is not on that tenant's list. Measured on the
    production group (n=4, control = this file on main): the EXECUTOR's draft carried the
    promise in 4/4 openings ("May I ask you three quick questions…") and a base-script
    question in 4/4 third turns, and the voice conveyed them — the executor never receives the
    block, so the voice is the only stage that can refuse them.

    And refusing them at the opening is enough: with this rule and `system.txt` untouched,
    the same executor's third-turn draft carried NO script question (0/4) — it followed the
    questionnaire the transcript now shows. An executor-side rule was measured (4/4 too) and
    added nothing, so nothing in `system.txt` changed. The script leak at t3 was downstream of
    the opening, not a second cause.

    So, with the block present: the opening asks the block's item directly (no permission for
    a battery, no announcement of one), a permission/script question in the draft is NOT
    conveyed, and the written script is suspended while the block exists. Gémeo 2: the
    opening stays THIS persona's — greet by name, say where you speak from."""
    rendered = _render_voice(block=_HOST_BLOCK_HEADER + "\n- (the tenant's item)")
    flat = " ".join(rendered.split())
    rule = flat[flat.index("Se o contexto trouxer um bloco de onboarding"):
                flat.index("SEM esse bloco")]
    assert "FAÇA a pergunta do bloco" in rule
    assert "sem pedir licença para perguntar" in rule
    assert "sem anunciar quantas perguntas" in rule
    assert "SUSPENSO" in rule and "enquanto o bloco existir" in rule
    assert "NÃO transmita" in rule and "pedido de licença" in rule       # the draft override
    assert "responder ao que a pessoa perguntou continua normal" in rule  # never gags a reply
    assert "cumprimente pelo nome" in rule and "de onde você fala" in rule  # gémeo 2
    # the pointer uses the host header's words, and the list itself never enters this file
    assert "ainda falta descobrir" in rule
    assert "mês e ano" not in (PROMPTS / "voice.txt").read_text()
    # the rule precedes the arc it overrides, and the opening bullet carries the exception at
    # the exact spot that instructs the habit
    assert flat.index("Se o contexto trouxer um bloco") < flat.index("[ABERTURA]")
    assert "a pergunta do bloco entra no lugar do pedido de licença" in flat

