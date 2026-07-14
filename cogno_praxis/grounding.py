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

Locale note: the reply-side rules run against the VOICER's reply, which is in the
tenant's configured voice language (``tenant.settings["language"]`` → resolved
``noumeno.language``). The language-specific lexicon (negation / date / money tokens)
lives in :class:`Locale`; each vertical pairs one with its own reply patterns +
rewrite messages per locale (``_BUNDLES``). The host derives the 2-letter family from
the turn's language and passes ``locale=`` down. An UNSUPPORTED language fails open (no
rules → no rewrite): a backstop never rewrites a reply in a language it can't read.
Supported today: pt, en, es. Everything else here (clause splitting, the neutral types,
trace helpers) is language-agnostic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# The numeric date anchor is language-agnostic: dd/mm(/yyyy) or ISO. (Standalone clock
# times are deliberately NOT matched — the pre-locale behaviour — so this stays shared.)
_DATE_CORE = r"\b\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b"

_CLAUSE_SPLIT_RE = re.compile(r"[.!?,;\n]+|\s[—–-]\s")


@dataclass(frozen=True)
class Locale:
    """The language-specific lexical anchors a grounding backstop needs: a clause-level
    negation, a date anchor, and a money anchor. Verticals pair one of these with their
    own reply patterns + rewrite messages, one bundle per locale."""

    lang: str
    neg: re.Pattern[str]
    date: re.Pattern[str]
    money: re.Pattern[str]


_PT = Locale(
    lang="pt",
    # "não", "nenhum", "nunca", "sem "
    neg=re.compile(r"\bn[ãa]o\b|\bnenhum\b|\bnunca\b|\bsem\s", re.IGNORECASE),
    date=re.compile(_DATE_CORE),
    # "R$ 500", "500,00", "1.234,56"
    money=re.compile(r"R\$\s?\d|\b\d{1,3}(?:\.\d{3})*,\d{2}\b"),
)
_EN = Locale(
    lang="en",
    # "not", "no", "never", "without", "n't", "none", "nothing"
    neg=re.compile(r"\bnot\b|\bno\b|\bnever\b|\bwithout\b|n't\b|\bnone\b|\bnothing\b",
                   re.IGNORECASE),
    date=re.compile(_DATE_CORE),
    # "$500", "500.00", "1,234.56"
    money=re.compile(r"\$\s?\d|\b\d{1,3}(?:,\d{3})*\.\d{2}\b"),
)
_ES = Locale(
    lang="es",
    # "no", "nunca", "ningún/ninguna", "sin ", "nada"
    neg=re.compile(r"\bno\b|\bnunca\b|\bning[úu]n[ao]?\b|\bsin\s|\bnada\b", re.IGNORECASE),
    date=re.compile(_DATE_CORE),
    # "€500", "$500", "500,00" (es-ES uses the comma decimal like pt)
    money=re.compile(r"[€$]\s?\d|\b\d{1,3}(?:\.\d{3})*,\d{2}\b"),
)

#: Supported grounding locales, keyed by 2-letter family.
LOCALES: dict[str, Locale] = {"pt": _PT, "en": _EN, "es": _ES}

# Back-compat module-level pt regexes (host + pre-locale callers import these directly).
NEG_RE = _PT.neg
DATE_RE = _PT.date
MONEY_RE = _PT.money


def normalize_lang(lang: Optional[str]) -> str:
    """A language tag/code onto its 2-letter family key ('pt-BR'→'pt', 'en_US'→'en')."""
    return (lang or "").strip().lower().replace("_", "-").split("-")[0]


def resolve_locale(lang: Optional[str]) -> Optional[Locale]:
    """The :class:`Locale` for a tenant language, or ``None`` when unsupported — the
    caller then fails open (a backstop never rewrites a reply it has no rules for)."""
    return LOCALES.get(normalize_lang(lang))


def clauses(text: str) -> Iterable[str]:
    """Split on clause boundaries (commas/semicolons/dashes too, not just sentences) so a
    stray negation elsewhere ("não se preocupe, sua consulta está agendada…") does not mask
    a real affirmation in the neighbouring clause."""
    return _CLAUSE_SPLIT_RE.split(text)


def affirmed(text: str, pattern: re.Pattern[str], *, neg: re.Pattern[str] = NEG_RE) -> bool:
    """Some clause matches ``pattern`` and is not negated in that clause. ``neg`` is the
    active locale's negation (defaults to pt for pre-locale callers)."""
    return any(pattern.search(c) and not neg.search(c) for c in clauses(text))


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
