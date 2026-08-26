"""No vertical prompt may teach the `<TOOL_CALL>` syntax — the CORE owns that.

The rule already existed, in a comment: `cogno_anima/stages/ego.py` says, beside the block it
renders, *"The persona prompt must NOT contain this; the core owns it and never edits the host's
text."* Nothing checked it, and it had been violated for an unknown length of time —
`scheduler/prompts/system.txt` taught the format AND gave two worked examples.

Why that matters beyond tidiness: the core appends the mechanics only when the turn actually has
a catalogue (cogno-anima#121). A prompt that teaches the tag by itself defeats that guard — a
persona with no tools still reads two examples of how to emit one, and a tag the model emits with
nothing to call is not a failed call, it is TEXT: it reaches the contact.

Same shape as `test_code_domains_match_prompt_domains_exactly` in cogno-anima — a contract split
between prose and code where only one side had a guard.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PROMPTS = sorted(Path(__file__).resolve().parents[2].glob("cogno_praxis/*/prompts/*.txt"))

# The tag itself, and the two spellings a well-meaning edit reaches for.
FORBIDDEN = ("<TOOL_CALL>", "</TOOL_CALL>", "TOOL_CALL")


def test_the_glob_actually_finds_the_prompts():
    """A guard over an empty file list is a guard that passes forever.

    This is the control the rule below needs: if the layout moves and the glob stops matching,
    the next test goes green over nothing and the rule quietly stops existing.
    """
    assert len(PROMPTS) >= 10, f"o varrimento achou só {len(PROMPTS)} prompts — o glob mudou?"
    assert any(p.name == "system.txt" for p in PROMPTS)


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_no_vertical_prompt_teaches_the_tool_call_syntax(prompt: Path):
    text = prompt.read_text(encoding="utf-8")
    hits = [tag for tag in FORBIDDEN if tag in text]
    assert not hits, (
        f"{prompt.relative_to(prompt.parents[3])} ensina {hits} — a mecânica de chamada é do "
        "CORE (`cogno_anima.stages.ego`), que a renderiza SÓ quando o turno tem catálogo. Um "
        "prompt que a ensina sozinho derrota essa guarda, e uma tag emitida sem ter o que "
        "chamar chega ao contato como texto. Diga a ORDEM das chamadas em prosa, se for isso "
        "que quer ensinar."
    )
