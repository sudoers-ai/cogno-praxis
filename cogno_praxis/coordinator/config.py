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

    # The professor-pay estimate. NONE of these has a business default: every one of them
    # is a number or a column name only the tenant knows, and a default here would be this
    # library guessing at somebody's pay. Absent → the estimate refuses and names the key.
    COLUMN_HOURS: "Carga Horária"       # the per-discipline hour total, on TAB_HOURS
    TAB_HOURS: "Informações Adicionais" # optional — defaults to TAB_PROFESSORS
    RANGE_HOURS: "A1:E50"               # optional — defaults to RANGE_PROFESSORS
    PAY_RATE_PER_HOUR: 120,00           # the hourly rate
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
        # WHERE the hours live is two questions, and only the second one is required. The TAB
        # falls back to the professors tab because that tab is itself a tenant declaration —
        # falling back to another of the tenant's own answers is not a guess. The COLUMN has no
        # such fallback: it is the one name nothing else in this config can stand in for.
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
        """The pay keys this tenant has NOT declared — ``()`` when an estimate is possible.

        One place answers "may this be attempted at all", and it answers by NAMING what is
        missing rather than with a bare no: the refusal a professor reads has to tell whoever
        administers the tenant which line to add, or it is a dead end wearing a sentence.
        """
        missing: list[str] = []
        if self.pay_rate_per_hour is None:
            missing.append("PAY_RATE_PER_HOUR")
        if not self.column_hours.strip():
            missing.append("COLUMN_HOURS")
        return tuple(missing)
