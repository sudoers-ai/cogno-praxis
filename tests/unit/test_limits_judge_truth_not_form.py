"""A persona's `limits.txt` reaches the JUDGE, and a judge judges TRUTH, ANSWER and LIMITS.

Owner's rule, 2026-09-06: *«todos os juízes de todas as personas só devem julgar verdade e
respostas»*. Three things, and nothing else:

1. **TRUTH** — nothing asserted without a source (a tool result, the context, what the contact
   said); preserved terms exact; a write announced is a write made.
2. **ANSWER** — the contact's question was answered or the limit admitted; an action request was
   executed or proposed (goal↔execution, constraints).
3. **BUSINESS LIMITS** — what the persona may NOT do (sell, advise clinically). This one STAYS,
   because it is truth about REACH, not style.

Everything that is FORM belongs to the VOICE: how many questions, how long, what tone, how warm,
and re-asking a question. The two slots reach DIFFERENT calls — `cogno_host/persona.py`'s
`SLOT_TO_LAYER` sends "limits" to the judge and "voice" to the voicer, and nothing merges them —
so a style rule written here is paid on every judge call, never reaches the writer, and buys the
rejection of a reply that is true and complete and that no retry can improve.

WHAT THIS TEST PROVES, AND WHAT IT DOES NOT
-------------------------------------------
This is a regex assertion over PROSE. The target here IS prose, so the instrument is legitimate.
It is bounded in two directions, and the next reader must not mistake a green for a certificate:

* **It does not prove the absence of FORM. It proves the absence of THESE TERMS.** Form written
  in words the lexicon does not carry passes clean. A measured example, not a hypothetical:
  `"Keep it short."` is missed, because the length rule below needs a message noun near the
  adjective and that sentence has none. `"seja mais simpático com quem reclama"` is caught only
  because `simpát` happens to be listed; `"não seja seco"` is not.
* The other direction is the false POSITIVE, and it is why the lexicon was built by ENUMERATING
  every occurrence of every candidate term over the whole corpus BEFORE the diff. A legitimate
  business limit that happens to use a lexicon word — *«não prometa prazos curtos»* is a LIMIT,
  not form — must not be caught. Four candidates were dropped and two refined for exactly that;
  each is named below with the line that killed it.

The census that built this (base `a3ad2db`, 5 files, 45 candidate terms, 18 hits):

    'pergunta'  11 hits, >=9 legitimate  -> DROPPED. The judge must CLASSIFY whether the contact
                                            asked, and must demand that a question be answered:
                                            "A pergunta dela manda: precisa ser respondida."
    'frase'      1 hit, closer:59        -> REFINED to a COUNT. The hit is the ANTI-form
                                            declaration ("quantas frases tem").
    'escrita'    1 hit, closer:60        -> DROPPED. "instrução de escrita e vive no prompt da
                                            voz" is the pointer TO the voice.
    'polite'     1 hit, coordinator:43   -> DROPPED. "is INCOMPLETE, however polite" tells the
                                            judge NOT to be swayed by courtesy.
    'brief'      1 hit, coordinator:6    -> KEPT as `\\bbrief\\b`: the hit is the tool name
                                            `get_weekly_briefing`, which has no word boundary.
    'curto/longo'  0 hits                -> REFINED to need a MESSAGE NOUN within 45 chars.
                                            Bare, they catch "prazos curtos" and "a longo
                                            prazo", which are business limits; and they catch
                                            an anti-form clause, measured on `cogno-anima`'s
                                            open `#150` whose `_READONLY_CRITERIA` says
                                            "whether it is long or short".
    'ritmo'      1 hit, interviewer:12   -> TRUE POSITIVE, removed by this PR.
    'empat'      1 hit, interviewer:5    -> TRUE POSITIVE, removed by this PR.
    'acolh'      1 hit, interviewer:5    -> TRUE POSITIVE, same line.

`objetivo` is deliberately absent although it reads as a style word ("objetivas"): it is also
the word for a GOAL, and goal↔execution is criterion #1 of every judge prompt in the house.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LIMITS = sorted(REPO.glob("cogno_praxis/*/prompts/limits.txt"))

# ── the lexicon ────────────────────────────────────────────────────────────────────────────
# label -> (pattern, why it is FORM and not a business limit)
SIMPLE: dict[str, tuple[str, str]] = {
    "tom": (r"\btom\b|\btons\b|\btone\b",
            "the register of a reply is the voice's, and the host already modulates it"),
    "emoji": (r"emoji", "a glyph budget is typography"),
    "empatia": (r"empat|acolh|\bwarm\b|\bfriendly\b|\bcordial\b|\bgentil\b|simpát|caloros",
                "how warmly it reads; the persona's declared traits carry this"),
    "ritmo": (r"\britmo\b|\brhythm\b|\bpac(?:e|ing)\b",
              "cadence across turns is not a fact about this reply's truth"),
    "estilo": (r"\bestilo\b|\bstyle\b|\bformata[çc]\w*|\bmarcador(?:es)?\b|\bbullet",
               "layout and wording"),
    "entusiasmo": (r"entusiasm\w*|\benthusias", "affect"),
    "frases-contadas": (r"(?:\d+|uma|duas|tr[êe]s|quatro|cinco|muitas|poucas)\s+frases?\b"
                        r"|(?:\d+|one|two|three|four|five)\s+sentences?\b",
                        "a sentence count is the clearest style rule there is"),
}

# Length needs the noun. `curto`/`longo`/`short`/`long` describe a DEADLINE as readily as a
# message, so they count as form only near a word for the message itself; the adjectives that
# can only ever mean a message stand alone.
_MSG_NOUN = (r"mensage\w+|respostas?|frases?|texto\w*|linhas?|repl(?:y|ies)|messages?"
             r"|turno|parágrafo\w*")
_LEN_AMBIGUOUS = r"curt[oa]s?|long[oa]s?|extens[oa]s?|\blong\b|\bshort\b"
_LEN_UNAMBIGUOUS = r"concis[oa]s?|concise|\bbrief\b|lengthy|verbose|prolix\w*"
_NOUN_WINDOW = 45


def _length_hits(text: str) -> list[tuple[int, str]]:
    """(offset, matched word) for every LENGTH instruction about the MESSAGE."""
    out = [(m.start(), m.group(0))
           for m in re.finditer(rf"\b(?:{_LEN_UNAMBIGUOUS})\b", text, re.IGNORECASE)]
    for m in re.finditer(rf"\b(?:{_LEN_AMBIGUOUS})\b", text, re.IGNORECASE):
        lo, hi = max(0, m.start() - _NOUN_WINDOW), m.end() + _NOUN_WINDOW
        if re.search(rf"\b(?:{_MSG_NOUN})\b", text[lo:hi], re.IGNORECASE):
            out.append((m.start(), m.group(0)))
    return out


def sweep(text: str) -> list[tuple[str, int, str]]:
    """(label, offset, matched text) for every form instruction the lexicon can see."""
    hits = [(label, m.start(), m.group(0))
            for label, (pattern, _) in SIMPLE.items()
            for m in re.finditer(pattern, text, re.IGNORECASE)]
    hits += [("tamanho", off, word) for off, word in _length_hits(text)]
    return sorted(hits, key=lambda h: h[1])


_WHY = {**{k: v[1] for k, v in SIMPLE.items()},
        "tamanho": "length; a true and complete answer cannot be made shorter by a retry"}

_HINT = (
    "Um juiz julga VERDADE, RESPOSTA e LIMITES DE NEGÓCIO — mais nada (ordem do dono, "
    "2026-09-06). Forma vive em `voice.txt`, o único slot que chega a quem ESCREVE "
    "(`cogno_host/persona.py: SLOT_TO_LAYER`). Uma regra de estilo escrita aqui é paga em "
    "cada chamada do juiz, nunca chega ao escritor, e compra a rejeição de uma resposta "
    "verdadeira e completa que nenhuma nova tentativa consegue melhorar."
)


def test_the_glob_actually_finds_the_limits() -> None:
    """A sweep over an empty file list is a sweep that passes forever.

    The control the rule below needs, and the DENOMINATOR the report quotes. Same shape as
    `test_the_glob_actually_finds_the_prompts` next door. The glob is over the REPO tree, so a
    persona whose prompts are on disk but not yet committed is swept too — deliberately: the
    guard should bite before the file lands, not after.
    """
    assert len(LIMITS) >= 5, f"o varrimento achou só {len(LIMITS)} limits.txt — o layout mudou?"
    names = {p.parent.parent.name for p in LIMITS}
    for persona in ("bookkeeper", "closer", "coordinator", "interviewer", "scheduler"):
        assert persona in names, persona


@pytest.mark.parametrize("limits", LIMITS, ids=lambda p: p.parent.parent.name)
def test_no_limits_prompt_asks_the_judge_to_grade_form(limits: Path) -> None:
    text = limits.read_text(encoding="utf-8")
    hits = [
        f"[{label}] linha {text.count(chr(10), 0, off) + 1}: "
        f"…{text[max(0, off - 60):off + len(word) + 60].replace(chr(10), ' ')}… — {_WHY[label]}"
        for label, off, word in sweep(text)
    ]
    assert not hits, (
        f"{limits.parent.parent.name}/limits.txt pede FORMA ao juiz:\n  "
        + "\n  ".join(hits) + "\n" + _HINT
    )


# ── the mutation and its twin, as tests ────────────────────────────────────────────────────

_FORM_SENTENCES = (
    "- Rejeite se a mensagem tiver mais de quatro frases.",
    "- Rejeite se a resposta for muito longa.",
    "- Rejeite se a mensagem não for curta.",
    "- Mensagens curtas e objetivas.",
    "- Seja conciso.",
    "- Reject a reply that is too long.",
    "- Rejeite se usar emoji.",
    "- Rejeite se o tom não for acolhedor.",
    "- Rejeite se não demonstrar empatia.",
    "- Rejeite se quebrar o ritmo da conversa.",
    "- Rejeite se responder com marcadores em vez de texto corrido.",
)

_BUSINESS_LIMITS = (
    "- Rejeite se prometer prazos curtos que a operação não cumpre.",
    "- Nunca ofereça um prazo curto sem confirmar com a equipe.",
    "- Rejeite se prometer retorno a longo prazo.",
    "- Rejeite se prometer um prazo longo demais para o cliente.",
    "- Do not promise a short lead time.",
    "- Rejeite se empurrar propostas comerciais ou tentar vender produtos.",
    "- Rejeite se der conselho médico, jurídico ou financeiro.",
    "- O objetivo do contato manda: precisa ser respondido.",
    "- Rejeite se expor a agenda de outro professor a um não-supervisor.",
)


@pytest.mark.parametrize("sentence", _FORM_SENTENCES)
def test_a_form_sentence_in_a_limits_prompt_is_caught(sentence: str) -> None:
    """THE mutation: put a form sentence in a `limits.txt` and the sweep must fail."""
    assert sweep(sentence), f"forma não apanhada: {sentence!r}"


@pytest.mark.parametrize("sentence", _BUSINESS_LIMITS)
def test_a_business_limit_that_uses_a_lexicon_word_is_NOT_caught(sentence: str) -> None:
    """The TWIN, and the reason the census came before the diff.

    *«não prometa prazos curtos»* is a LIMIT — it is about what the persona may promise, not
    about how the sentence reads — and it carries `curtos`, a candidate lexicon word. The
    length rule needs a MESSAGE NOUN within 45 characters precisely so this passes. If this
    goes red, the lexicon grew a term that punishes a legitimate limit, and the next author
    will delete a real rule to get CI green.
    """
    assert not sweep(sentence), f"falso positivo sobre um limite de negócio: {sentence!r}"


def test_the_anti_form_declaration_passes_clean() -> None:
    """The false positive the census actually found, pinned as a property.

    `closer/limits.txt` and (since this PR) `interviewer/limits.txt` end with a paragraph whose
    whole job is to say that form is NOT a criterion — and it necessarily NAMES form to do it.
    Bare `frases` and `escrita` were dropped or count-qualified for this sentence. The English
    twin comes from `cogno-anima`'s open `#150`, whose `_READONLY_CRITERIA` carries the same
    shape; it is quoted here because that is where the bare `long`/`short` pair was measured
    colliding, and it is why they need the noun.
    """
    pt = ("Forma NÃO é critério seu: quantas perguntas a mensagem faz, quantas frases tem, se "
          "repete uma pergunta já respondida. Isso é instrução de escrita e vive no prompt da "
          "voz. Nunca rejeite uma resposta verdadeira e completa pela forma.")
    en = ("A truthful reply built out of what the reads returned is a PASS, whether it is long "
          "or short.")
    assert sweep(pt) == [], sweep(pt)
    assert sweep(en) == [], sweep(en)
    closer = (REPO / "cogno_praxis/closer/prompts/limits.txt").read_text(encoding="utf-8")
    assert "Forma NÃO é critério seu" in closer     # the wording is not invented here


def test_the_lexicon_does_not_claim_to_prove_absence_of_form() -> None:
    """The docstring's honesty, made executable so it cannot rot into a false promise.

    `"Keep it short."` is FORM and the sweep misses it — there is no message noun for the
    length rule to find. This is the false-NEGATIVE half, and it is pinned so that a future
    reader who trusts a green here meets the counter-example in the same file. If someone
    widens the rule and this goes red, the docstring above is what needs updating, not this
    assertion — delete it then, deliberately.
    """
    assert sweep("Keep it short.") == []
    assert sweep("- Rejeite se não for seco o suficiente.") == []
