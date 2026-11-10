"""«Não há X» — the ``NO SUCH DISCIPLINE`` line OPENS the listing, as the answer, never under it.

The shape of a real read, with invented names: a professor asks for his classes of a discipline
the schedule does not hold. The tool drops the filter and SAYS so (M6-c), and the host's
«você quis dizer» reads the list of disciplines back (VQD-2(a)). But the line sat at the END, a
footer under the whole listing, worded as a note to the executor ("so the list above is…"). The
reply was written from the top: measured on that read, it listed the classes and left the
negative out 3 times in 5, so the contact never learned that the name matched nothing.

Now the line is the first paragraph of the tool's text, it says the miss as a sentence of its
own, and it asks for it as the reply's first sentence (:data:`SAY_THE_MISS_FIRST`). Every other
read renders byte for byte as before (the digests below were taken on praxis main ``6d46f598``).
"""

from __future__ import annotations

import asyncio
import hashlib

import pytest

from cogno_praxis.coordinator import parse_unmatched_discipline
from cogno_praxis.coordinator.footers import NO_SUCH_DISCIPLINE, SAY_THE_MISS_FIRST
from tests.unit.test_coordinator_unmatched_discipline import PROGRAMA, _tool

#: A discipline name nobody's schedule holds — the 2450 shape (not the 2056 programme shape).
ASKED = "Ciência de Dados"


def _first_class(out: str) -> int:
    at = out.find("\n- ")
    assert at >= 0, out
    return at


# ── the presence: the negative is the first thing the read says ──────────────────────────

@pytest.mark.parametrize("asked", [ASKED, PROGRAMA])
def test_a_negativa_abre_a_listagem_antes_de_qualquer_aula(asked):
    out = _tool(discipline=asked)
    head = out.split("\n\n", 1)[0]
    assert head.startswith(f'{NO_SUCH_DISCIPLINE}: "{asked}" does not match any discipline '
                           f"in this schedule. ")
    assert SAY_THE_MISS_FIRST in head
    assert out.index(NO_SUCH_DISCIPLINE) < out.index("*Setembro de 2026*") < _first_class(out)
    assert out.count(NO_SUCH_DISCIPLINE) == 1, "the line is said ONCE, at the head"


def test_os_outros_rodapes_continuam_debaixo_da_lista():
    """Only the miss moved. The window notes are notes ABOUT the list and stay under it."""
    out = _tool(discipline=ASKED)
    last_class = out.rindex("\n- ")
    assert out.index("(This list covers today onward") > last_class
    assert out.index("(This list covers the next 30 days") > last_class


def test_o_leitor_do_host_le_a_linha_na_cabeca():
    """The host's VQD-2(a) reads the line wherever it sits — one reader, position-free."""
    assert parse_unmatched_discipline(_tool(discipline=ASKED)) == (
        ASKED, ("Bancos NoSQL", "Spark Distribuído"))


def test_a_linha_nao_aponta_para_cima_nem_para_baixo():
    """Worded to stay true wherever a caller puts it (`_fmt_report` still carries it for a
    caller that writes no head)."""
    line = next(ln for ln in _tool(discipline=ASKED).splitlines()
                if ln.startswith(NO_SUCH_DISCIPLINE))
    assert "above" not in line and "below" not in line


# ── the voice reads it first, through the REAL voice prompt ──────────────────────────────

def _voice_prompt(tool_output: str) -> str:
    from cogno_anima.stages.superego import SuperegoStage
    from cogno_anima.types import (EgoResult, EgoStep, IntentResult, NoumenoResult,
                                   PipelineContext, StageMetrics, ToolExecution)

    def m(stage: str) -> StageMetrics:
        return StageMetrics(stage=stage, model="stub", elapsed_ms=0.0, tokens_in=0, tokens_out=0)

    user = f"quais são as minhas aulas de {ASKED}?"
    ctx = PipelineContext(
        user_input=user,
        noumeno=NoumenoResult(original=user, rewritten=f"what are my {ASKED} classes?",
                              context_turn="", language="pt", canonical_language="en",
                              drift_score=0.0, drift_tag="PASS_THROUGH", changed=False,
                              confidence=1.0, change_subject=False, subject_similarity=1.0,
                              context_used=False, preserved_terms=[], rewrite_warnings=[],
                              metrics=m("noumeno")),
        intent=IntentResult(intent_class="INFORMATION_REQUEST", sentiment="NEUTRAL",
                            confidence=1.0, temporal_class="FUTURE", triad_signal="EGO",
                            goal="see my classes", domains=["EDUCATION"], pii_risk="NONE",
                            metrics=m("ner")),
    )
    ctx.ego_result = EgoResult(steps=[EgoStep(
        index=0, path="native", assistant_text="",
        tool_calls=[ToolExecution(tool="get_professor_schedule",
                                  arguments={"discipline": ASKED}, result=tool_output,
                                  ok=True, side_effect=False)])], metrics=m("ego"))

    class Stub:
        model = "stub"

        async def generate(self, system, prompt):
            return "ok", 1, 1

    res = asyncio.run(SuperegoStage().voice(ctx, Stub(), voice_prompt="Persona."))
    return res.prompt_text or ""


def test_no_prompt_da_voz_a_negativa_vem_antes_das_aulas():
    out = _tool(discipline=ASKED)
    prompt = _voice_prompt(out)
    assert SAY_THE_MISS_FIRST in prompt
    data = prompt.index(NO_SUCH_DISCIPLINE)
    assert data < prompt.index("- 10/09") and data < prompt.index("- 17/09")


# ── the controls: a read WITH its data renders byte for byte as on praxis main ───────────

#: sha256 of the tool's text per read (the miss is the one that moves). Re-taken when the listing
#: gained the discipline's last-class mark: only the reads that actually CONTAIN a last class moved
#: (``other_month`` and ``turma_miss`` list nothing, so their digest is byte for byte main's — the
#: proof the mark is surgical, not a blanket reformat).
_MAIN = {
    "no_discipline": ({}, "73854fd934acddf6bacc90efcd5e561240e3b391610eb3d6545effd52c6ca786"),
    "matching_discipline": ({"discipline": "Bancos NoSQL"},
                            "bf5941652d437364120c4df8b0b5763b37be61076340301d80c8cafa37444790"),
    "matching_fuzzy": ({"discipline": "spark distribuido"},
                       "7204da8352bd576fbe88b92ad1942ec58f1f6891724b5882e113c167ef6d1be0"),
    "other_month": ({"discipline": "Spark", "month": "2026-10"},
                    "a26f297bf70db95de30b967ad080a073ed883aaf8df651b6d44cbb3a80096ddc"),
    "include_past": ({"include_past": True},
                     "139ad68d3e88c3c427efb48acc96f59b5c60d58729fb440f3d1db541c2f28f26"),
    "turma_miss": ({"turma": "ZZ_99"},
                   "f914e6f16ac290e4442c526ee0277b13985a8ec964e29eb3ad1e7f16e9bd97c3"),
    "month": ({"month": "2026-11"},
              "a1e07b3b72a0e35f45b5465786367792a2cf20a69b459989f828cc722f5aa5a4"),
}

#: The miss on praxis main — the broken world, so the control below is shown to discriminate.
_MAIN_MISS = "1a4e3a77868b971571cbd9355efc1916249212fe6d6fd2af948ea9cda6eec1d9"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize("name", sorted(_MAIN))
def test_controlo_uma_leitura_com_dados_fica_byte_a_byte(name):
    kwargs, digest = _MAIN[name]
    assert _sha(_tool(**kwargs)) == digest


def test_controlo_o_digest_ve_a_mudanca_na_leitura_que_falha():
    """The same digest, over the one read that DID change, must differ — else the controls
    above would pass over any change at all."""
    assert _sha(_tool(discipline=PROGRAMA)) != _MAIN_MISS
