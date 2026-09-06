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
    FIXED_COLUMNS: "Data, Dia"
    FREE_SLOT_LABELS: "Livre, Reposição"
    SKIP_LABELS: "Recesso, Feriado, Férias"
"""

from __future__ import annotations

import logging
import re

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

        # Columns that DON'T move during a swap (dates stay put; content columns are exchanged).
        self.fixed_columns: tuple[str, ...] = _find_list(rules, "FIXED_COLUMNS", ("Data", "Dia"))

        # Subject-cell values that mean "an open slot" vs "not a real class, skip it".
        self.free_slot_labels: tuple[str, ...] = _find_list(
            rules, "FREE_SLOT_LABELS", ("Livre", "Reposição", "Reposicao"))
        self.skip_labels: tuple[str, ...] = _find_list(
            rules, "SKIP_LABELS",
            ("Recesso", "Feriado", "Emenda", "Férias", "Reservado",
             "Feriado Nacional", "Recesso Escolar"))

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
