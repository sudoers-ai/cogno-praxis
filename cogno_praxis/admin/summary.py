"""The three layers a proposed change is reported in — pure, deterministic, no model call.

Rendered from a typed :class:`ChangeReport`:

* **Diretor** — 2 to 3 lines: what changes, its size, and whether it waits for a decision;
* **Gerencial** — impact, risk, the reviewer's opinion, how to revert;
* **Técnico** — the files, a diff summary, the tests, the PR.

The labels a reader sees are pt-BR, like every other text this package writes for a person (the
listings, the e-mails). The limits are ENFORCED here, not asked of a writer: each layer has a
maximum number of lines (:data:`MAX_LINES`), every line is one line (whitespace collapsed) of at
most :data:`MAX_LINE_CHARS` characters, cut with «…», and a file list longer than
:data:`MAX_FILES_LISTED` ends with how many were left out. A field nobody filled says
:data:`NOT_GIVEN` — never an invented value, never a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cogno_praxis.admin.impact import Classification, PathChange

#: Lines per layer: (minimum, maximum).
MAX_LINES = {"diretor": (2, 3), "gerencial": (4, 6), "tecnico": (4, 12)}
MAX_LINE_CHARS = 160
MAX_FILES_LISTED = 6

LAYER_TITLES = {"diretor": "Diretor", "gerencial": "Gerencial", "tecnico": "Técnico"}
NOT_GIVEN = "não informado"

_SIZE_WORD = {"small": "pequena", "large": "grande"}
#: The impact rules, in the reader's words. Keyed by the closed codes of ``impact.RULES``.
RULE_WORDS = {
    "kind_not_declared": "tipo de mudança não declarado",
    "not_a_correction": "não é correção: é melhoria ou evolução",
    "new_capability": "vertical, persona ou ferramenta nova",
    "scope_or_limits": "muda o escopo ou os limites",
    "store_or_schema": "muda armazenamento ou esquema",
    "dependency": "muda dependências",
    "diff_size": "diff acima de 200 linhas",
    "admin_code": "toca o código do próprio NEO",
    "doubt": "na dúvida, grande",
    "escalated": "escalada pelo revisor",
}


@dataclass(frozen=True)
class ChangeReport:
    """What a proposed change is, in the fields the three layers read."""

    title: str
    vertical: str
    classification: Classification
    benefit: Optional[str] = None
    impact: Optional[str] = None
    risk: Optional[str] = None
    reviewer_opinion: Optional[str] = None
    revert: Optional[str] = None
    files: "tuple[PathChange, ...]" = ()
    diff_summary: Optional[str] = None
    tests: Optional[str] = None
    pr: Optional[str] = None


@dataclass(frozen=True)
class Summary:
    diretor: "tuple[str, ...]"
    gerencial: "tuple[str, ...]"
    tecnico: "tuple[str, ...]"

    def text(self) -> str:
        blocks = []
        for key in ("diretor", "gerencial", "tecnico"):
            lines = getattr(self, key)
            blocks.append("\n".join([f"{LAYER_TITLES[key]}:"] + [f"- {line}" for line in lines]))
        return "\n\n".join(blocks)


def _line(text: Optional[str]) -> str:
    """One line, whitespace collapsed, at most :data:`MAX_LINE_CHARS`; empty → :data:`NOT_GIVEN`."""
    flat = " ".join(str(text).split()) if text is not None else ""
    if not flat:
        flat = NOT_GIVEN
    if len(flat) > MAX_LINE_CHARS:
        flat = flat[: MAX_LINE_CHARS - 1].rstrip() + "…"
    return flat


def _count(value: Optional[int]) -> str:
    return str(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else "?"


def _rule_words(reasons: "tuple[str, ...]") -> str:
    seen: "list[str]" = []
    for reason in reasons:
        code = reason.split(":", 1)[0]
        words = RULE_WORDS.get(code, code)
        if words not in seen:
            seen.append(words)
    return "; ".join(seen)


def _fit(lines: "list[str]", layer: str) -> "tuple[str, ...]":
    low, high = MAX_LINES[layer]
    out = [_line(line) for line in lines][:high]
    if len(out) < low:  # pragma: no cover - every layer below renders at least its minimum
        raise AssertionError(f"{layer} rendered {len(out)} lines, under its minimum {low}")
    return tuple(out)


def _diretor(report: ChangeReport) -> "list[str]":
    size = report.classification.size
    lines = [f"{_line(report.title)} — mudança {_SIZE_WORD.get(size, 'grande')} em "
             f"{_line(report.vertical)}."]
    lines.append(f"Ganho: {_line(report.benefit)}")
    if size != "small":
        lines.append("Precisa da sua decisão antes de seguir.")
    return lines


def _gerencial(report: ChangeReport) -> "list[str]":
    size = report.classification.size
    why = _rule_words(report.classification.reasons)
    sized = f"Tamanho: {_SIZE_WORD.get(size, 'grande')}" + (f" ({why})" if why else "")
    return [
        sized,
        f"Impacto: {_line(report.impact)}",
        f"Risco: {_line(report.risk)}",
        f"Parecer do revisor: {_line(report.reviewer_opinion)}",
        f"Como reverter: {_line(report.revert)}",
    ]


def _tecnico(report: ChangeReport) -> "list[str]":
    files = tuple(report.files)
    added = [f.added for f in files]
    removed = [f.removed for f in files]
    known = all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in added + removed)
    totals = (f"+{sum(n for n in added if n)} -{sum(n for n in removed if n)}" if known and files
              else "linhas: ?" if files else "")
    lines = [f"Arquivos: {len(files)}" + (f" ({totals})" if totals else "")]
    budget = MAX_LINES["tecnico"][1] - 4   # the four fixed lines below + the header above
    shown = files[: min(MAX_FILES_LISTED, budget)]
    for f in shown:
        lines.append(f"{f.path} (+{_count(f.added)} -{_count(f.removed)})")
    if len(files) > len(shown):
        lines.append(f"… e mais {len(files) - len(shown)} arquivo(s)")
    lines.append(f"Resumo do diff: {_line(report.diff_summary)}")
    lines.append(f"Testes: {_line(report.tests)}")
    lines.append(f"PR: {_line(report.pr)}")
    return lines


def render(report: ChangeReport) -> Summary:
    """The three layers of ``report``. Same report, same bytes."""
    return Summary(diretor=_fit(_diretor(report), "diretor"),
                   gerencial=_fit(_gerencial(report), "gerencial"),
                   tecnico=_fit(_tecnico(report), "tecnico"))


__all__ = [
    "LAYER_TITLES",
    "MAX_FILES_LISTED",
    "MAX_LINES",
    "MAX_LINE_CHARS",
    "NOT_GIVEN",
    "RULE_WORDS",
    "ChangeReport",
    "Summary",
    "render",
]
