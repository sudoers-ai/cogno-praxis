"""Shared kit for the verticals' deterministic reply-grounding backstops.

Each vertical ships its anti-fabrication rules NEXT TO the tool-result strings they
grep (``cogno_praxis/<module>/grounding.py``) — single source of truth: rewording a
tool message and updating the rule that reads it happen in the same repo, ideally the
same PR (the behavioural marker tests pin them together).

The rules are HOST-agnostic: no anima/host import. The host adapts its
``PipelineContext`` onto :class:`ToolCall` rows and calls the vertical's
``ground_reply(reply, tools=…)``; the returned :class:`GroundingVerdict` says which
rule fired, the honest replacement message, and — when re-running the executor can
produce the REAL answer — a ``critique`` for the correction loop. The REWRITE decision
(and the repair/streak policy) stays at the host.

Locale note: reply-side patterns and replacement messages are pt-BR (this product's
voice language); a persona voicing another language silently bypasses the reply-side
rules (fail-open). A second locale means a second pattern/message set per vertical —
kept grouped for that day, not abstracted before it exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# A date token in the reply: dd/mm(/yyyy) or ISO. Times: "11:00", "11h", "às 14".
DATE_RE = re.compile(r"\b\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b")
# A money token: "R$ 500", "500,00", "1.234,56".
MONEY_RE = re.compile(r"R\$\s?\d|\b\d{1,3}(?:\.\d{3})*,\d{2}\b")
# A clause-level negation ("não", "nenhum", "nunca", "sem ").
NEG_RE = re.compile(r"\bn[ãa]o\b|\bnenhum\b|\bnunca\b|\bsem\s", re.IGNORECASE)

_CLAUSE_SPLIT_RE = re.compile(r"[.!?,;\n]+|\s[—–-]\s")


def clauses(text: str) -> Iterable[str]:
    """Split on clause boundaries (commas/semicolons/dashes too, not just sentences) so a
    stray negation elsewhere ("não se preocupe, sua consulta está agendada…") does not mask
    a real affirmation in the neighbouring clause."""
    return _CLAUSE_SPLIT_RE.split(text)


def affirmed(text: str, pattern: re.Pattern[str]) -> bool:
    """Some clause matches ``pattern`` and is not negated in that clause."""
    return any(pattern.search(c) and not NEG_RE.search(c) for c in clauses(text))


@dataclass(frozen=True)
class ToolCall:
    """One executed tool call from the turn's trace, in neutral (host-agnostic) shape.

    The host maps its executor trace rows onto these; ``result`` is the tool's output
    string on success (the markers the rules grep), ``ok`` the recoverable-success flag,
    ``side_effect`` whether the tool mutates (per the host's tool policy)."""

    tool: str
    ok: bool
    side_effect: bool = False
    result: str = ""
    error: str = ""


@dataclass(frozen=True)
class GroundingVerdict:
    """What a backstop found: which rule fired and what to do about it.

    ``message`` is the honest replacement reply (the safe fallback). ``repairable`` marks
    the rules where re-running the EXECUTOR with ``critique`` as the correction reason can
    produce the REAL answer — by construction those rules only fire when no relevant
    mutation happened this turn, so a repair re-step never doubles a side effect."""

    rule: str
    message: str
    repairable: bool = False
    critique: str = field(default="", compare=False)


def ok_results(tools: Sequence[ToolCall], tool: Optional[str] = None) -> list[str]:
    """Every successful (ok) result string in the trace — for one tool, or all of them."""
    return [t.result or "" for t in tools if t.ok and (tool is None or t.tool == tool)]
