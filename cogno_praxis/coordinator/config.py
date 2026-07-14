"""``CoordinatorConfig`` — a tenant's academic-schedule configuration.

The coordinator vertical is CONFIG-DRIVEN: which spreadsheets to read, which tab/range holds
the schedule, which header names map to the date/professor/subject roles, and which cell values
mean "free slot" or "skip" all come from the tenant's ``custom_rules`` text (the parent's
``tenant_personas.custom_rules``). This module parses that text into a structured, testable
config — the domain service never touches raw rules text.

Format (all sections optional; sensible defaults shown)::

    SPREADSHEETS:
    DSA_33=1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8
    DE_09=1U6Sve7H26NPp8DK-aj9pX_wUg7xIURBANx2vnjamLEc

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

import re


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
        # SPREADSHEETS: KEY=ID lines under the header (ID = 20–60 word chars). Falls back to
        # scanning the whole text for bare long IDs (parent parity for loosely-formatted rules).
        self.spreadsheets: dict[str, str] = {}
        section = re.search(r"(?is)SPREADSHEETS:\s*\n((?:\s*\S+\s*=\s*\S+\s*\n?)+)", rules)
        if section:
            for k, v in re.findall(r"(\S+)\s*=\s*([a-zA-Z0-9_-]{20,60})", section.group(1)):
                self.spreadsheets[k.strip()] = v.strip()
        elif re.search(r"[a-zA-Z0-9_-]{30,60}", rules):
            for i, sid in enumerate(re.findall(r"([a-zA-Z0-9_-]{30,60})", rules)):
                self.spreadsheets.setdefault(f"SHEET_{i+1}", sid)

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

    @property
    def configured(self) -> bool:
        """True iff at least one spreadsheet is declared (else the service short-circuits)."""
        return bool(self.spreadsheets)
