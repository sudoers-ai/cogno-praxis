"""``CoordinatorConfig`` — a tenant's academic-schedule configuration.

The coordinator vertical is CONFIG-DRIVEN: which spreadsheets to read, which tab/range holds
the schedule, which header names map to the date/professor/subject roles, and which cell values
mean "free slot" or "skip" all come from the tenant's ``custom_rules`` text (the parent's
``tenant_personas.custom_rules``). This module parses that text into a structured, testable
config — the domain service never touches raw rules text.

Format (all sections optional; sensible defaults shown)::

    SPREADSHEETS:
    DSA_33=1QwErTy-UiOpAsDfGhJkLzXcVbNm45678
    Turma DE_09 = 1PoIuYtReWqLkJhGfDsAmNbVcXz0123456789AbCdEfG

    TAB_SCHEDULE: "Secretaria"
    RANGE_SCHEDULE: "A4:E110"
    RANGE_METADATA: "A1:E3"
    TAB_PROFESSORS: "Informações Adicionais"
    RANGE_PROFESSORS: "A1:E50"

    COLUMN_DATE: "Data"
    COLUMN_PROFESSOR: "Professor"
    COLUMN_SUBJECT: "Disciplina"
    COLUMN_TIME: "Hora"                 # optional — absent → the calendar export is all-day
    CLASS_DURATION_MINUTES: 240         # only used when COLUMN_TIME resolves
    FIXED_COLUMNS: "Data, Dia"
    FREE_SLOT_LABELS: "Livre, Reposição"
    SKIP_LABELS: "Recesso, Feriado, Férias"

    # The STATUS column — the one a listing prints when it says something exceptional, and
    # the one a professor's answer to a class invitation is recorded in.
    COLUMN_STATUS: "Status"
    STATUS_DEFAULT_LABELS: "Confirmado, Confirmada"   # the ordinary state: printed by nobody
    STATUS_ACCEPTED_LABEL: "Aceita"     # what an accepted invitation writes into that cell
    STATUS_DECLINED_LABEL: "Recusada"   # and a declined one

    # The professor-pay estimate. NONE of these has a business default: every one of them
    # is a number or a column name only the tenant knows, and a default here would be this
    # library guessing at somebody's pay. Absent → the estimate refuses and names the key.
    #
    # The MONTH's pay is  classes in the month × HOURS_PER_CLASS × PAY_RATE_PER_HOUR  (plus
    # the IBOPE bonus per hour). HOURS_PER_CLASS is the hours ONE class (one row of the
    # schedule sheet) is worth — the tenant's own sentence: "cada linha na planilha equivale
    # a 4 horas". It is never inferred and never derived by dividing a workload by a count.
    HOURS_PER_CLASS: 4                  # hours per class (per schedule row) — REQUIRED
    PAY_RATE_PER_HOUR: 120,00           # the hourly rate — REQUIRED
    # COLUMN_HOURS is the discipline's TOTAL workload ("carga horária completa da
    # disciplina"), read off TAB_HOURS. OPTIONAL, and CONTEXT ONLY: it is shown beside the
    # estimate and prices "the whole discipline" (workload × rate); it is NEVER multiplied
    # by the number of classes. Until 2026-09-22 it was, and a 16 h discipline taught twice
    # in a month came out as 32 h — R$ 3.840,00 where the tenant's rule paid R$ 960,00.
    COLUMN_HOURS: "Carga Horária"       # optional — the discipline's total workload
    TAB_HOURS: "Informações Adicionais" # optional — defaults to TAB_PROFESSORS
    RANGE_HOURS: "A1:E50"               # optional — defaults to RANGE_PROFESSORS
    IBOPE_BONUS: 80-89=30; 90+=40       # optional bonus bands, R$/hour. SEMICOLONS separate
                                        # them — the comma is the decimal separator here.
    IBOPE_MIN_RESPONSE_PCT: 30          # optional: the share of the class that must have
                                        # ANSWERED before any bonus is due
    TAB_IBOPE: "IBOPE"                  # where a survey RESULT is recorded, if anywhere
    RANGE_IBOPE: "A1:Z200"              # optional — defaults to A1:Z200
    COLUMN_IBOPE: "Resultado"           # the percentage column on that tab
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from cogno_praxis.coordinator.pay import BonusTier, parse_bonus_tiers, parse_money

_log = logging.getLogger(__name__)

# A spreadsheet id as it appears on a ``KEY = VALUE`` line or in the header-less scan. The two
# paths share the token on purpose: whatever a tenant may DECLARE, the scan may also GUESS.
_ID_TOKEN = r"[a-zA-Z0-9_-]{20,60}"
# ``SPREADSHEETS:`` opening a section. Anchored at the start of a line; ``rest`` is whatever
# followed it on that same line (a tenant who wrote the first pair inline).
_SECTION_HEADER = re.compile(r"^[ \t]*SPREADSHEETS:(?P<rest>.*)$", re.IGNORECASE)
# One ``KEY = VALUE`` line INSIDE the section. The key may contain SPACES — the tenant writes
# "Turma DSA_33 = <id>", not "DSA_33=<id>" — which is what the old ``\S+\s*=`` regex could not
# match, and why the whole section went unrecognised (see ``CoordinatorConfig.__init__``).
_SECTION_PAIR = re.compile(r"^\s*(?P<key>[^=\n]+?)\s*=\s*(?P<value>\S+)\s*$")


def _find(rules: str, key: str, default: str) -> str:
    """First ``KEY: value`` line (case-insensitive), stripped of surrounding quotes/space."""
    m = re.search(rf"(?im)^\s*{key}:\s*(.+)$", rules)
    return m.group(1).strip().strip('"').strip("'") if m else default


def _find_int(rules: str, key: str, default: int) -> int:
    """A ``KEY: 240`` line as a positive int; anything else (absent, blank, "abc", 0, -5) →
    ``default``. A duration that is not a positive number is not a duration."""
    raw = _find(rules, key, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _find_positive(rules: str, key: str) -> Optional[float]:
    """A ``KEY: 4`` / ``KEY: 4,5`` line as a positive number; anything else is ``None``.

    ``None`` means UNDECLARED. A zero or a negative is treated the same way rather than kept:
    "a class is worth 0 hours" is not a declaration anyone made about pay, it is a typo, and the
    estimate refuses and names the key instead of paying nothing."""
    value = parse_money(_find(rules, key, ""))
    return value if value is not None and value > 0 else None


def _find_pct(raw: str) -> Optional[float]:
    """A percentage in ``0..100`` — anything else (absent, blank, "abc", 150, -1) is ``None``.

    ``None`` means the tenant declared no such threshold, and the estimate then states no
    condition. A value OUT of range is treated the same way rather than clamped: clamping 150
    to 100 would invent a rule the tenant did not write, about money."""
    value = parse_money(raw)
    return value if value is not None and 0.0 <= value <= 100.0 else None


def _find_list(rules: str, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """A comma-separated ``KEY: a, b, c`` line → a tuple of trimmed values."""
    raw = _find(rules, key, "")
    if not raw:
        return default
    return tuple(v.strip() for v in raw.split(",") if v.strip())


class CoordinatorConfig:
    """Parsed academic-schedule config for one tenant/persona (from ``custom_rules`` text).

    Empty rules → a config with no spreadsheets (the service returns "not configured" rather
    than crashing). Every field has a default so a partially-configured tenant still works.
    """

    def __init__(self, rules: str = "") -> None:
        rules = rules or ""
        # SPREADSHEETS: KEY = ID lines under the header; NO header → scan the text for bare ids.
        self.spreadsheets: dict[str, str] = self._parse_spreadsheets(rules)

        # Where the schedule + metadata + professor info live.
        self.tab_schedule: str = _find(rules, "TAB_SCHEDULE", "Secretaria")
        self.range_schedule: str = _find(rules, "RANGE_SCHEDULE", "A4:Z200")
        self.range_metadata: str = _find(rules, "RANGE_METADATA", "A1:Z3")
        self.tab_professors: str = _find(rules, "TAB_PROFESSORS?", "Informações Adicionais")
        self.range_professors: str = _find(rules, "RANGE_PROFESSORS?", "A1:Z50")

        # Header names that map to the three system roles (RBAC uses professor; free/skip use subject).
        self.column_date: str = _find(rules, "COLUMN_DATE", "Data")
        self.column_professor: str = _find(rules, "COLUMN_PROFESSOR", "Professor")
        self.column_subject: str = _find(rules, "COLUMN_SUBJECT", "Disciplina")
        # The HOUR, when the sheet has one. Optional by design and absent in most tenants: a
        # schedule spreadsheet records a DAY, and the calendar export renders an all-day event
        # when no hour column resolves. Never guessed from a header — only this name is looked
        # for, exactly like the three above.
        self.column_time: str = _find(rules, "COLUMN_TIME", "Hora")
        # How long a class lasts, for the calendar export's DTEND when an hour IS present.
        # Only reachable together with COLUMN_TIME; a non-numeric value falls back rather than
        # raising, because a typo in the rules must not take the vertical down.
        self.class_duration_minutes: int = _find_int(rules, "CLASS_DURATION_MINUTES", 60)

        # The STATUS column, and the values in it that say nothing a reader needs.
        #
        # A schedule sheet marks most rows with the ordinary, expected state ("Confirmado") and
        # a few with something a professor must ACT on. Printing the ordinary one on every line
        # spends a column of every row saying "normal", which is how the one row that says
        # something else stops standing out. So the listing prints a status only when it is NOT
        # one of these — the exception is the information, the rule is noise.
        #
        # DECLARED, not inferred: which words mean "nothing to see here" is the tenant's
        # vocabulary, and a system that guessed would eventually swallow a real warning because
        # it looked routine. A tenant whose sheet says "OK" adds it here; deleting a value from
        # this list makes that value print again, which is the safe direction to be wrong in.
        self.column_status: str = _find(rules, "COLUMN_STATUS", "Status")
        self.status_default_labels: tuple[str, ...] = _find_list(
            rules, "STATUS_DEFAULT_LABELS", ("Confirmado", "Confirmada"))
        # The two words an ANSWER to a class invitation writes into that same column. Declared
        # here for the same reason the labels above are: a professor reads this cell in their
        # own spreadsheet, so the word has to be the institution's, and a tenant whose sheet
        # already says "Aceito"/"Recusado" changes two lines instead of forking the vertical.
        #
        # They are deliberately NOT in `STATUS_DEFAULT_LABELS`: that list is what the listing
        # SWALLOWS as routine, and an answer is precisely the thing a coordinator has to see.
        # A tenant who puts one of these there is telling the listing to hide it, which is a
        # choice this config lets them make and does not make for them.
        self.status_accepted_label: str = _find(rules, "STATUS_ACCEPTED_LABEL", "Aceita")
        self.status_declined_label: str = _find(rules, "STATUS_DECLINED_LABEL", "Recusada")

        # Columns that DON'T move during a swap (dates stay put; content columns are exchanged).
        self.fixed_columns: tuple[str, ...] = _find_list(rules, "FIXED_COLUMNS", ("Data", "Dia"))

        # Subject-cell values that mean "an open slot" vs "not a real class, skip it".
        self.free_slot_labels: tuple[str, ...] = _find_list(
            rules, "FREE_SLOT_LABELS", ("Livre", "Reposição", "Reposicao"))
        self.skip_labels: tuple[str, ...] = _find_list(
            rules, "SKIP_LABELS",
            ("Recesso", "Feriado", "Emenda", "Férias", "Reservado",
             "Feriado Nacional", "Recesso Escolar"))

        # ── the professor-pay estimate ───────────────────────────────────────────────
        # Read here, and DELIBERATELY WITHOUT DEFAULTS, unlike every field above. The others
        # default because a wrong guess costs a mis-labelled column; these are a person's pay.
        # A missing key must reach the professor as "this institution has not declared it",
        # which is a true sentence they can act on, and never as a number this library chose.
        #
        # HOW MANY HOURS ONE CLASS IS WORTH. The month's pay is classes × this × the rate, and
        # this is the number that used to be read off the sheet's workload column and
        # multiplied by the class count — see ``column_hours`` below for what that cost.
        # REQUIRED, never inferred: "4" is the only value any tenant has ever meant, and a
        # library that assumed it would be right for every tenant until the one it is not.
        self.hours_per_class: Optional[float] = _find_positive(rules, "HOURS_PER_CLASS")
        # WHERE the discipline's TOTAL workload lives. The TAB falls back to the professors tab
        # because that tab is itself a tenant declaration — falling back to another of the
        # tenant's own answers is not a guess. The COLUMN has no fallback and is OPTIONAL:
        # the workload is CONTEXT ("carga total da disciplina: 16 h", and what the whole
        # discipline is worth), it is not a factor of the month's pay. It WAS one until
        # 2026-09-22 — ``PayLine.hours_total = hours_each × classes`` — and the docstring of
        # this very field already said "the per-discipline hour total": three declarations
        # of one key, in disagreement, and the one that decided a person's pay was the one
        # multiplying a discipline's whole workload by every class taught in the month.
        self.tab_hours: str = _find(rules, "TAB_HOURS", self.tab_professors)
        self.range_hours: str = _find(rules, "RANGE_HOURS", self.range_professors)
        self.column_hours: str = _find(rules, "COLUMN_HOURS", "")
        # The money. ``None``/``()`` mean UNDECLARED, and the two are not the same thing: no
        # rate means no estimate at all, while no tier means the rules declare no bonus — a
        # complete answer with nothing hypothetical in it.
        self.pay_rate_per_hour: Optional[float] = parse_money(_find(rules, "PAY_RATE_PER_HOUR", ""))
        # ONE name, no alias. ``PAY_BONUS_TIERS`` existed for exactly one unmerged PR and no
        # live tenant ever declared it — measured: every role block of the only configured
        # tenant reports both pay keys missing. There is therefore no compatibility to keep, and
        # two spellings of one key is a second door to one decision: the coordinator types what
        # the rules documentation names, and a key that never matches fails as "not configured"
        # with nothing on screen to say why.
        self.ibope_bonus: tuple[BonusTier, ...]
        self.ibope_bonus_unreadable: tuple[str, ...]
        self.ibope_bonus, self.ibope_bonus_unreadable = parse_bonus_tiers(
            _find(rules, "IBOPE_BONUS", ""))
        # The share of the class that must have ANSWERED. ``None`` = the tenant declared none.
        self.ibope_min_response_pct: Optional[float] = _find_pct(
            _find(rules, "IBOPE_MIN_RESPONSE_PCT", ""))
        # WHERE a survey RESULT would be, when the tenant records one anywhere. Absent is the
        # ordinary case and is not a defect: it produces the hypotheses, named as hypotheses.
        self.tab_ibope: str = _find(rules, "TAB_IBOPE", "")
        self.range_ibope: str = _find(rules, "RANGE_IBOPE", "A1:Z200")
        self.column_ibope: str = _find(rules, "COLUMN_IBOPE", "")

        # The same figures written in PROSE — "R$ 120,00 por hora", "4 horas por aula" — for a
        # key the tenant did NOT declare as a ``KEY: value`` line. Read last, because "declared"
        # is decided by the parsed fields above; see :func:`find_pay_in_prose`.
        self.pay_in_prose: tuple[ProseHint, ...] = find_pay_in_prose(rules, declared={
            "PAY_RATE_PER_HOUR": self.pay_rate_per_hour is not None,
            "HOURS_PER_CLASS": self.hours_per_class is not None,
            # a declared-but-unreadable band already refuses, louder, and names the entry
            "IBOPE_BONUS": bool(self.ibope_bonus) or bool(self.ibope_bonus_unreadable),
            "IBOPE_MIN_RESPONSE_PCT": self.ibope_min_response_pct is not None,
        })
        _warn_prose_once(self.pay_in_prose)

    # ── SPREADSHEETS parsing ─────────────────────────────────────────────────────────
    @staticmethod
    def _parse_spreadsheets(rules: str) -> dict[str, str]:
        r"""``{key: sheet_id}`` from the rules text — TWO paths, and the header decides which.

        **Declared** (a ``SPREADSHEETS:`` line exists): every following ``KEY = VALUE`` line is a
        spreadsheet, and the key MAY CONTAIN SPACES (a tenant writes ``Turma DSA_33 = <id>``).
        Blank and ``#`` comment lines are skipped; the first other line that is not a pair ends
        the section (in real rules that is the next ``KEY: "value"`` config line).

        **Guessed** (no header at all): scan the whole text for bare long id-looking tokens, the
        parent's tolerance for loosely-formatted rules.

        The two are EXCLUSIVE, and that is the fix. The old section regex required ``\S+\s*=``,
        so a key with a space did not match, the section went unrecognised, and the *guess* ran
        over the whole document instead — which swept up the 31-char slug of a course URL sitting
        in the middle of the rules ("…/mbas/<a 31-char course slug>/") as ``SHEET_1``.
        Iteration order then put that fake id FIRST, its Drive read 404'd, and the exception took
        the whole ``get_professor_schedule`` call with it: the professor was told the assistant
        could not access the schedule, on a tenant whose four real spreadsheets were fine.
        A declared header is an INTENTION; once it is there, guessing is never the answer — an
        empty result ("not configured") is a truthful answer and a wrong id is not.
        """
        lines = rules.splitlines()
        header, start = None, 0
        for start, line in enumerate(lines):
            header = _SECTION_HEADER.match(line)
            if header:
                break
        if header is None:
            # No header → the parent's whole-text guess, unchanged.
            return {f"SHEET_{i + 1}": sid
                    for i, sid in enumerate(re.findall(r"([a-zA-Z0-9_-]{30,60})", rules))}

        body = lines[start + 1:]
        inline = header.group("rest")                  # "SPREADSHEETS: KEY = <id>" on one line
        if _SECTION_PAIR.match(inline):
            body = [inline] + body
        out: dict[str, str] = {}
        for line in body:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            pair = _SECTION_PAIR.match(line)
            if pair is None:
                break                                  # the section ended (next config line)
            key = re.sub(r"\s+", " ", pair.group("key").strip())
            value = pair.group("value")
            if not re.fullmatch(_ID_TOKEN, value):
                _log.warning("coordinator: SPREADSHEETS entry %r does not look like a spreadsheet "
                             "id (%d chars) — skipped", key, len(value))
                continue
            out[key] = value
        if not out:
            _log.warning("coordinator: a SPREADSHEETS: header was declared but no usable "
                         "'KEY = ID' line followed it — no spreadsheet is configured")
        return out

    @property
    def configured(self) -> bool:
        """True iff at least one spreadsheet is declared (else the service short-circuits)."""
        return bool(self.spreadsheets)

    @property
    def pay_undeclared(self) -> tuple[str, ...]:
        """The REQUIRED pay keys this tenant has NOT declared — ``()`` when an estimate is possible.

        One place answers "may this be attempted at all", and it answers by NAMING what is
        missing rather than with a bare no: the refusal a professor reads has to tell whoever
        administers the tenant which line to add, or it is a dead end wearing a sentence.

        ``COLUMN_HOURS`` is not in it any more (2026-09-22): the workload column is context,
        and an estimate without it is a complete estimate with less context.
        """
        missing: list[str] = []
        if self.pay_rate_per_hour is None:
            missing.append("PAY_RATE_PER_HOUR")
        if self.hours_per_class is None:
            missing.append("HOURS_PER_CLASS")
        return tuple(missing)


# ── the same figures, written in PROSE ────────────────────────────────────────────────
#
# Measured 2026-09-22 on a live tenant: the persona rules carried "Aula - R$ 120,00 por hora,
# sendo o mínimo 4 horas por aula", "Ibope > 80% e <89%: Adicional de R$ 30,00 por hora" and
# "respondido por pelo menos 30% da turma" — every figure the estimate needs, in Portuguese
# prose — and ``estimate_professor_pay`` ran, ``ok=True``, and answered "NOT CONFIGURED:
# PAY_RATE_PER_HOUR, COLUMN_HOURS are missing from the persona rules". Both true. ``_find``
# reads ``KEY: value`` lines and nothing else, and it returns the default in SILENCE, so the
# same truth declared in two grammars counted in one and nothing told anybody. The model,
# meanwhile, SAW the R$ 120 in its prompt and was (rightly) forbidden to do the arithmetic.
#
# This does not read the prose as configuration — a rate read out of a sentence is a guess
# with a decimal point in it. It RECOGNISES the shapes, conservatively, and names each one
# beside the key it should have been, so the refusal says "found X in the rules, but KEY is not
# declared" instead of "KEY is missing" over rules that plainly contain it. Only the keys this
# config already reads (plus HOURS_PER_CLASS, which arrived with this) — no new key is invented
# here, and a sentence the table does not recognise is simply not mentioned.
@dataclass(frozen=True)
class ProseHint:
    """One pay key found in PROSE and not as a ``KEY: value`` line, with the sentences seen."""
    key: str
    excerpts: tuple[str, ...]

    def sentence(self) -> str:
        quoted = ", ".join(f'"{e}"' for e in self.excerpts)
        return f"found {quoted} in the rules, but {self.key} is not declared"


#: A money literal as these rules write it: ``R$ 120,00``, ``R$ 1.234,56``, ``R$120``.
_MONEY = r"R\$\s*\d[\d.]*(?:,\d{1,2})?"
#: "…per hour", in the ways a coordinator writes it: ``por hora``, ``a hora``, ``/h``, ``/hora``.
_PER_HOUR = r"(?:por|a|cada|/)\s*h(?:ora)?s?\b"
#: A line that is about the BONUS rather than the base rate. Decided per LINE, so the two
#: "Adicional de R$ 30,00 por hora" lines cannot be mistaken for two hourly rates.
_BONUS_WORDS = re.compile(r"(?i)\b(?:ibope|adicional|b[ôo]nus|extra|acr[ée]scimo)\b")
#: (key, pattern) — the recognised shapes, in the ORDER their sentences are listed. Each
#: pattern is anchored to a figure ("R$ …", "4 horas", "30%") so the excerpt it produces is a
#: figure with a few words around it and never a stretch of free text — which is also what makes
#: it safe to log: nothing here can capture a name.
_PROSE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PAY_RATE_PER_HOUR", re.compile(rf"(?i){_MONEY}\s*{_PER_HOUR}")),
    ("HOURS_PER_CLASS", re.compile(
        r"(?i)(?:\d+(?:[.,]\d+)?\s*h(?:oras?)?\s+(?:por|para|em|a)?\s*(?:cada\s+)?aula\b"
        r"|\baulas?\s+de\s+\d+(?:[.,]\d+)?\s*h(?:oras?)?\b)")),
    ("IBOPE_BONUS", re.compile(rf"(?i)(?:adicional\s+de\s+)?{_MONEY}\s*{_PER_HOUR}")),
    ("IBOPE_MIN_RESPONSE_PCT", re.compile(
        r"(?i)respondid[oa]\s+por\s+(?:pelo\s+menos|no\s+m[íi]nimo|ao\s+menos)?\s*"
        r"\d+(?:[.,]\d+)?\s*%")),
)
#: How much of a matched sentence travels into the message and the log. The patterns already
#: bound it; this is the belt to their braces.
_EXCERPT_MAX = 60


def find_pay_in_prose(rules: str, *, declared: dict[str, bool]) -> tuple[ProseHint, ...]:
    """The pay keys the rules describe in PROSE without declaring — ``()`` when none.

    ``declared`` says, per key, whether the parsed config already holds a value; a key that is
    declared is never reported, however many sentences also describe it (prose beside a declared
    key is documentation, and this is not a linter). A key that is NOT declared is reported with
    every distinct sentence that matched, in document order, so the message can quote what it
    saw. Line by line, because the rate/bonus distinction is a property of the LINE ("Ibope …
    Adicional de R$ 30,00 por hora" is a bonus, "Aula - R$ 120,00 por hora" is a rate).
    """
    found: dict[str, list[str]] = {}
    for raw in (rules or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        bonus_line = bool(_BONUS_WORDS.search(line))
        for key, pattern in _PROSE_PATTERNS:
            if declared.get(key, False):
                continue
            if key == "PAY_RATE_PER_HOUR" and bonus_line:
                continue
            if key == "IBOPE_BONUS" and not bonus_line:
                continue
            for m in pattern.finditer(line):
                excerpt = re.sub(r"\s+", " ", m.group(0)).strip()[:_EXCERPT_MAX]
                bucket = found.setdefault(key, [])
                if excerpt not in bucket:
                    bucket.append(excerpt)
    return tuple(ProseHint(key, tuple(excerpts))
                 for key, _p in _PROSE_PATTERNS if (excerpts := found.get(key)))


#: The configurations already warned about in this process — a config is rebuilt on every
#: tool call, and a warning per call is a warning nobody reads.
_PROSE_WARNED: set[tuple[ProseHint, ...]] = set()


def _warn_prose_once(hints: tuple[ProseHint, ...]) -> None:
    if not hints or hints in _PROSE_WARNED:
        return
    _PROSE_WARNED.add(hints)
    _log.warning("coordinator: the persona rules describe pay figures in PROSE that this config "
                 "does not read — %s. Only 'KEY: value' lines are read; the estimate refuses "
                 "and names these until they are declared that way.",
                 "; ".join(h.sentence() for h in hints))


def pay_refusal(missing: tuple[str, ...], prose: tuple[ProseHint, ...]) -> str:
    """The sentence the estimate refuses with — REQUIRED keys missing, prose found, or both.

    Three shapes, and the difference between the first two is the whole 2026-09-22 change:

    * keys missing, nothing in prose — the tenant never declared them; the sentence names them;
    * keys missing AND the figures are in prose — the tenant DID declare them, in a grammar this
      config does not read; the sentence names what it found and which key each should be, so
      whoever administers the persona knows it is one line per figure and not a decision;
    * nothing missing but a figure in prose for an OPTIONAL key (the bonus, the response-rate
      condition) — refused too, for the reason an unreadable band is: an estimate that says
      "this tenant declares no bonus" over rules that describe one pays less with the very
      sentence a tenant with no bonus scheme legitimately gets.
    """
    assert missing or prose
    parts: list[str] = []
    if missing:
        parts.append(
            f"This institution has not configured the pay figures: {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} missing from the persona rules. "
            f"Nothing can be estimated without {'it' if len(missing) == 1 else 'them'}, "
            f"and nothing here will be assumed.")
    if prose:
        seen = "; ".join(h.sentence() for h in prose)
        parts.append(
            f"The rules DO describe {'them' if missing else 'pay figures'} in prose, which this "
            f"system does not read as configuration: {seen}. Each has to be written as its own "
            f"KEY: value line (for example PAY_RATE_PER_HOUR: 120,00 or HOURS_PER_CLASS: 4) by "
            f"whoever administers this persona; until then nothing is estimated, because a "
            f"figure the rules describe and the estimate silently omits is a wrong number about "
            f"a person's pay.")
    return " ".join(parts)
