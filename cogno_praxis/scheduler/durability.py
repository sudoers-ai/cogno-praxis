"""Graph-durability veto for the SCHEDULER vertical.

The knowledge graph is relational SUPPORT (who-is-who), never live state. The Tier-2 LLM
consolidation happily emits scheduling-state edges (``HAS_APPOINTMENT``, ``BLOCKED_DATE``,
``IS_PENDING`` …); fed to the voicer as support, a stale one is a fresh fabrication source.

This module owns ONLY the scheduler's domain vocabulary — the perishable RELATION names a
scheduling conversation produces. The generic, cross-domain signals (a date/time endpoint, a
bare generic concept, universal status verbs) live in the host core; the host composes
``core ∪ active-verticals`` (mirrors the per-vertical grounding registry). Keeping the domain
lexicon next to the vertical means a new persona ships its own without touching the core.
"""

from __future__ import annotations

import re

# Scheduling-state relation stems (case-insensitive, matched anywhere in the relation name):
# appointment/booking/slot/block/availability/reschedule + the PT-BR forms a local model emits.
_PERISHABLE_REL = re.compile(
    r"APPOINTMENT|BOOK|SCHEDUL|SLOT|BLOCK|BUSY|OCCUP|AVAILABILIT|RESCHEDUL|RESERV|"
    r"AGENDAMENT|CONSULTA|HORARIO|MARCAD|REMARC|DESMARC|COMPROMISS", re.IGNORECASE)


def is_perishable_edge(source: str, target: str, relation: str) -> bool:
    """True iff this edge encodes volatile SCHEDULING state (belongs to a live tool read, not
    the durable graph). Only inspects the relation name — dates/generic nodes are host-core."""
    return bool(_PERISHABLE_REL.search(relation or ""))
