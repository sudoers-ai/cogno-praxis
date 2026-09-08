"""The professor-pay estimate — pure types, tenant-declared money, and the block that renders it.

**Nothing in this module invents a number.** Every figure it can state came from somewhere the
tenant declared: the hour total from a column the tenant NAMED, the hourly rate and the bonus
tiers from the tenant's own rules text. When a source is missing the estimate says so and stops
short of the total, because a made-up figure about a person's own pay is the one error they
cannot check and will act on.

The three shapes that follow from that, and each one exists because the alternative is a lie:

* a discipline whose hours the sheet does not carry is LISTED BY NAME and left out of the
  total (:attr:`PayEstimate.hours_missing`), never counted as zero — zero hours reads as
  "that class pays nothing", which is a different and false statement;
* an IBOPE result that was not found produces the declared HYPOTHESES, all of them, none
  chosen (:attr:`PayEstimate.hypotheses`) — the bonus tiers are a fact about the rules, the
  bonus itself is a fact about a survey nobody read;
* an undeclared rate or an undeclared hours column produces no estimate at all. That refusal
  lives in the service; what lives here is that neither has a default to fall back to.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

_log = logging.getLogger(__name__)

#: Every rendered block opens with a bold header in this shape. WhatsApp-style ``*bold*``,
#: because that is the channel these replies reach a professor through.
_H = "*{}*"


# ── money, as this tenant's people write it ──────────────────────────────────────────
def parse_money(raw: str) -> Optional[float]:
    """``"120,00"`` / ``"R$ 1.920,00"`` / ``"120.00"`` / ``"120"`` → a float; junk → ``None``.

    Both separators are accepted because both are written: a rules file typed by a Brazilian
    coordinator says ``120,00`` and a spreadsheet exported from a US locale says ``120.00``.
    What is NOT accepted is anything else at all — the return is ``None`` and the caller
    refuses. There is deliberately no "best effort" branch: a rate read wrong by a factor of a
    thousand is worse than no rate.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    text = re.sub(r"(?i)^r\$\s*", "", text).strip()
    # 1.234,56 (pt-BR) → 1234.56 ; 1,234.56 (en-US) → 1234.56 ; 120,00 → 120.00
    if "," in text and "." in text:
        text = (text.replace(".", "").replace(",", ".")
                if text.rfind(",") > text.rfind(".") else text.replace(",", ""))
    elif "," in text:
        text = text.replace(",", ".")
    if not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return None
    try:
        return float(text)
    except ValueError:                      # pragma: no cover — the regex already refused it
        return None


def fmt_money(value: float) -> str:
    """A float as ``R$ 1.920,00`` — pt-BR, because the professor reading it is Brazilian."""
    s = f"{value:,.2f}"                     # 1,920.00
    s = s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"R$ {s}"


def fmt_hours(value: float) -> str:
    """``16.0`` → ``"16 h"``; ``1.5`` → ``"1,5 h"`` — a whole number never grows a ``,0``."""
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))} h"
    return f"{value:.1f}".replace(".", ",") + " h"


# ── the bonus, as the tenant declares it ─────────────────────────────────────────────
@dataclass(frozen=True)
class BonusTier:
    """One declared IBOPE bonus band: ``low``–``high`` percent pays ``per_hour`` extra.

    ``high`` is ``None`` for an open-ended top band (``"90+ = 40"``). The band is carried as the
    tenant wrote it and is never interpolated between: a survey result of 89.5 falls in whatever
    band contains it or in none, and "none" is an answer.
    """
    low: float
    high: Optional[float]
    per_hour: float

    @property
    def label(self) -> str:
        return (f"IBOPE {self.low:g}–{self.high:g}%" if self.high is not None
                else f"IBOPE {self.low:g}%+")

    def contains(self, pct: float) -> bool:
        return pct >= self.low and (self.high is None or pct <= self.high)


#: One declared band. The amount runs to the end of its own chunk — it may contain a comma,
#: because in the locale that writes these rules the comma IS the decimal separator.
_TIER = re.compile(
    r"""^\s*(?P<low>\d+(?:[.,]\d+)?)\s*
        (?:(?:-|–|to|a)\s*(?P<high>\d+(?:[.,]\d+)?)|(?P<open>\+))?\s*%?\s*
        =\s*(?P<amount>[^;]+?)\s*$""",
    re.VERBOSE)

#: Bands are separated by SEMICOLONS and by nothing else. The comma was a separator here for
#: exactly one PR and it was a thousand-fold money bug: ``80-89 = 1.234,56`` split into
#: ``"80-89 = 1.234"`` and ``"56"``, the first parsed as a perfectly plausible **R$ 1,23** and
#: the second was discarded as unreadable. Nothing looked wrong; the band simply paid a
#: thousandth. A separator that can occur INSIDE the value it separates is not a separator.
_BAND_SEPARATOR = ";"


def parse_bonus_tiers(raw: str) -> "tuple[tuple[BonusTier, ...], tuple[str, ...]]":
    """``"80-89 = 30; 90+ = 40"`` → ``(bands sorted by low, entries this could not read)``.

    **The second half of that pair is the whole point.** An unreadable band used to be dropped
    with a log warning, and a value whose bands ALL failed came back as ``()`` — which the
    estimate then reported, truthfully and catastrophically, as "this tenant declares no bonus".
    A typo in the rules therefore paid a professor less and told nobody: the sentence the
    contact reads is identical to the sentence a tenant who really has no bonus scheme gets.

    So nothing is swallowed. The caller (:attr:`CoordinatorConfig.ibope_bonus_unreadable`) is
    handed every entry that failed and refuses the whole estimate, naming them. It is money;
    the only safe way to be wrong here is loudly.

    Refusing is deliberately NOT done by raising: this parser runs inside
    ``CoordinatorConfig.__init__``, which every tool of the vertical builds, so a raise would
    turn one typo in a bonus band into a professor who cannot read their own schedule. The
    blast radius belongs on the pay estimate alone.
    """
    if not raw or not raw.strip():
        return (), ()
    out: list[BonusTier] = []
    bad: list[str] = []
    for chunk in raw.split(_BAND_SEPARATOR):
        if not chunk.strip():
            continue
        m = _TIER.match(chunk)
        amount = parse_money(m.group("amount")) if m else None
        low = parse_money(m.group("low")) if m else None
        if m is None or amount is None or low is None:
            bad.append(chunk.strip())
            continue
        high = parse_money(m.group("high")) if m.group("high") else None
        out.append(BonusTier(low=low, high=high, per_hour=amount))
    return tuple(sorted(out, key=lambda t: t.low)), tuple(bad)


# ── the estimate ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PayLine:
    """One discipline inside one (turma, month) bucket.

    ``hours_each`` is ``None`` exactly when the tenant's hours column carried no row for this
    discipline. Then ``amount`` is ``None`` too and the line is excluded from every total — it
    is not zero. A professor told "Workshop de Abertura: R$ 0,00" reads that as a class that
    pays nothing; told "horas não declaradas" they read the truth, which is that this system
    does not know.
    """
    subject: str
    classes: int
    hours_each: Optional[float]

    @property
    def hours_total(self) -> Optional[float]:
        return None if self.hours_each is None else self.hours_each * self.classes

    def amount(self, rate: float) -> Optional[float]:
        h = self.hours_total
        return None if h is None else h * rate


@dataclass(frozen=True)
class PayGroup:
    """One (class group, month) bucket — the two axes the answer is grouped by."""
    turma: str
    month: str                              # "09/2026"
    lines: list[PayLine] = field(default_factory=list)

    @property
    def hours(self) -> float:
        return sum(ln.hours_total or 0.0 for ln in self.lines)


@dataclass(frozen=True)
class PayHypothesis:
    """One of the outcomes the declared rules ALLOW, offered because none could be verified."""
    label: str
    per_hour: float                         # 0.0 = the no-bonus baseline
    total: float


@dataclass(frozen=True)
class PayEstimate:
    """What a pay question can be answered with, and what it cannot.

    ``ibope_found`` is the bit the whole bonus half turns on. False means no IBOPE result was
    read — NOT that the result was bad — and the estimate then carries every declared
    hypothesis and picks none.
    """
    rate: float
    groups: list[PayGroup] = field(default_factory=list)
    hours_missing: tuple[str, ...] = ()     # disciplines the hours source does not name
    tiers: tuple[BonusTier, ...] = ()
    ibope_found: bool = False
    ibope_pct: Optional[float] = None
    ibope_tab: str = ""                     # the tab that WOULD carry it, when one is declared
    #: ``IBOPE_MIN_RESPONSE_PCT`` — the share of the class that must have ANSWERED the survey
    #: before any bonus is due. Declared by the tenant, and carried here so the block can state
    #: it as the CONDITION every figure below is subject to. This system has no reader for the
    #: response rate itself (no tenant declares one), so it is never silently treated as met.
    ibope_min_response_pct: Optional[float] = None
    period: str = ""                        # what the read filtered by, "" when it filtered none

    @property
    def hours(self) -> float:
        return sum(g.hours for g in self.groups)

    @property
    def base(self) -> float:
        return self.hours * self.rate

    @property
    def matched_tier(self) -> Optional[BonusTier]:
        """The band a FOUND result falls in — ``None`` when none was found or none contains it."""
        if not self.ibope_found or self.ibope_pct is None:
            return None
        return next((t for t in self.tiers if t.contains(self.ibope_pct)), None)

    @property
    def bonus_state(self) -> str:
        """Which of the four worlds this estimate's bonus is in — a closed vocabulary.

        ``applied``    a result was read and it falls inside a declared band.
        ``below``      a result was read and it is UNDER the lowest declared band. The bonus is
                       genuinely zero and the reply says so: the rules read "Ibope > 80% …
                       adicional", so under 80 there is no adicional, and that is a fact rather
                       than an absence of one.
        ``gap``        a result was read, it is not under the lowest band, and no band contains
                       it — 89,5 against bands of 80–89 and 90+. The bonus is UNDETERMINED, and
                       flatly it is not zero: paying zero there is a figure about somebody's
                       money that the tenant's own rules never authorised. The two worlds look
                       identical from inside ``matched_tier is None``, which is exactly why they
                       are told apart here and not by the renderer.
        ``not_found``  no result was read at all (see :attr:`ibope_found`).
        """
        if not self.tiers:
            return "not_found" if not self.ibope_found else "below"
        if not self.ibope_found or self.ibope_pct is None:
            return "not_found"
        if self.matched_tier is not None:
            return "applied"
        return "below" if self.ibope_pct < min(t.low for t in self.tiers) else "gap"

    @property
    def neighbouring_tiers(self) -> tuple[BonusTier, ...]:
        """For a ``gap``: the declared band just below the value and the one just above it.

        The two the reader has to arbitrate between, and no others — offering the whole ladder
        for a value that is demonstrably between two rungs is noise the reader has to filter
        before they can act."""
        if self.bonus_state != "gap" or self.ibope_pct is None:
            return ()
        below = [t for t in self.tiers if t.low <= self.ibope_pct]
        above = [t for t in self.tiers if t.low > self.ibope_pct]
        return tuple([below[-1]] if below else []) + tuple([above[0]] if above else [])

    @property
    def hypotheses(self) -> tuple[PayHypothesis, ...]:
        """The outcomes still open, the no-bonus baseline first — ``()`` when nothing is open.

        Two worlds produce hypotheses and they produce DIFFERENT ones. ``not_found`` knows
        nothing, so every declared band is still possible and all of them are listed. ``gap``
        knows the number and only cannot place it, so only the two bands around it are — with
        the baseline, because a value the bands do not cover may well earn nothing.
        """
        base = self.base
        state = self.bonus_state
        if state == "not_found" and self.tiers:
            return (PayHypothesis("Sem bônus", 0.0, base),
                    *(PayHypothesis(t.label, t.per_hour, base + self.hours * t.per_hour)
                      for t in self.tiers))
        if state == "gap":
            return (PayHypothesis("Sem bônus", 0.0, base),
                    *(PayHypothesis(t.label, t.per_hour, base + self.hours * t.per_hour)
                      for t in self.neighbouring_tiers))
        return ()


# ── the rendered block ───────────────────────────────────────────────────────────────
def render_pay_block(est: PayEstimate) -> str:
    """The estimate as the block a professor reads: bold headers, no repeated labels.

    **What this block may contain is a closed list, and that is a PII decision.** Every line is
    built from a class-group key, a month, a discipline name, a count, an hour total and a
    figure derived from those. It never copies a spreadsheet ROW, so no column the tenant
    happens to keep beside the schedule can ride out with it — and it never names a person, not
    even the reader, because the one identified human this block is about is the one holding
    the phone. The estimate is self-only by construction (see
    :meth:`CoordinatorService.estimate_professor_pay`), so there is no second person's figure
    for it to carry either.
    """
    period = f" — {est.period}" if est.period else ""
    out: list[str] = [_H.format(f"Remuneração estimada{period}"),
                      f"Valor/hora declarado nas regras: {fmt_money(est.rate)}", ""]
    for g in est.groups:
        out.append(_H.format(f"{g.turma} — {g.month}"))
        for ln in g.lines:
            aulas = f"{ln.classes} aula" + ("s" if ln.classes != 1 else "")
            if ln.hours_each is None:
                out.append(f"{ln.subject} · {aulas} · horas não declaradas · —")
            else:
                out.append(f"{ln.subject} · {aulas} · {fmt_hours(ln.hours_total or 0.0)} · "
                           f"{fmt_money(ln.amount(est.rate) or 0.0)}")
        out.append("")
    out.append(_H.format("Base"))
    out.append(f"{fmt_hours(est.hours)} · {fmt_money(est.base)}")
    if est.hours_missing:
        out.append(f"Fora desta soma, por não terem carga horária declarada na planilha: "
                   f"{', '.join(est.hours_missing)}.")
    out.append("")

    if not est.tiers:
        out.append(_H.format("Bônus IBOPE"))
        out.append("As regras deste tenant não declaram nenhuma faixa de bônus.")
        return "\n".join(out).strip()

    state = est.bonus_state
    tier = est.matched_tier
    if state == "applied" and tier is not None:
        bonus = est.hours * tier.per_hour
        out.append(_H.format(f"Bônus IBOPE — {est.ibope_pct:g}%"))
        out.append(f"{tier.label} · +{fmt_money(tier.per_hour)}/h · {fmt_money(bonus)}")
        out += _condition_lines(est)
        out.append(_H.format("Total"))
        out.append(fmt_money(est.base + bonus))
        return "\n".join(out).strip()

    if state == "below":
        lowest = min(t.low for t in est.tiers)
        out.append(_H.format(f"Bônus IBOPE — {est.ibope_pct:g}%"))
        out.append(f"Abaixo da faixa mais baixa declarada ({lowest:g}%), portanto sem adicional. "
                   f"Isto é um valor apurado, não uma falta de informação.")
        out += _condition_lines(est)
        out.append(_H.format("Total"))
        out.append(fmt_money(est.base))
        return "\n".join(out).strip()

    if state == "gap":
        out.append(_H.format(f"Bônus IBOPE — {est.ibope_pct:g}% — FAIXA NÃO DECLARADA"))
        out.append(f"O resultado foi encontrado, mas {est.ibope_pct:g}% não cai em nenhuma faixa "
                   f"declarada nas regras — fica entre duas. O adicional é INDETERMINADO, e não "
                   f"é zero: as faixas abaixo são as vizinhas, nenhuma foi escolhida.")
        for h in est.hypotheses:
            extra = "sem adicional" if h.per_hour == 0 else f"+{fmt_money(h.per_hour)}/h"
            out.append(f"{h.label} · {extra} · {fmt_money(h.total)}")
        out += _condition_lines(est)
        return "\n".join(out).strip()

    where = f" na aba «{est.ibope_tab}»" if est.ibope_tab else ""
    out.append(_H.format("Bônus IBOPE — RESULTADO NÃO ENCONTRADO"))
    out.append(f"O resultado do IBOPE não foi encontrado{where}, então o bônus não pode ser "
               f"calculado. Estas são as hipóteses previstas pelas regras — nenhuma delas foi "
               f"escolhida e nenhuma foi verificada:")
    for h in est.hypotheses:
        extra = "sem adicional" if h.per_hour == 0 else f"+{fmt_money(h.per_hour)}/h"
        out.append(f"{h.label} · {extra} · {fmt_money(h.total)}")
    out += _condition_lines(est)
    return "\n".join(out).strip()


def _condition_lines(est: PayEstimate) -> list[str]:
    """The response-rate condition, stated once, wherever a bonus figure was shown.

    The tenant declares a minimum share of the class that must have ANSWERED the survey before
    any bonus is due. Nothing here can read that share — no tenant declares a column for it — so
    it is never treated as met and never treated as failed. It is RENDERED, as the condition
    every figure above is subject to, because a bonus quoted without the condition it hangs on
    reads as a bonus that has been earned.
    """
    if est.ibope_min_response_pct is None:
        return []
    return ["", f"Condição das regras: o bônus só é devido se o IBOPE tiver sido respondido por "
                f"pelo menos {est.ibope_min_response_pct:g}% da turma. Este sistema não lê essa "
                f"taxa — confirme com a secretaria antes de contar com o adicional."]
