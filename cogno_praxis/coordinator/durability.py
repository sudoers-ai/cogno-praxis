"""Graph-durability veto for the COORDINATOR vertical.

Mirrors scheduler/bookkeeper: the perishable RELATION names an academic-schedule conversation
produces — a class on a date, a swap, a slot, a deadline/IBOPE state. Those are live schedule
facts a tool read owns, not durable graph knowledge. Durable relations (a professor TEACHES a
discipline, a discipline BELONGS_TO a course) pass untouched. Generic signals (dates, generic
concepts) are the host core's job.
"""

from __future__ import annotations

import re

# Academic-schedule volatile-state relation stems + PT-BR forms.
_PERISHABLE_REL = re.compile(
    r"SCHEDUL|CLASS_ON|SWAP|SLOT|DEADLINE|IBOPE|SURVEY|ATTEND|GRADE|REPLACEMENT|"
    r"FREE_SLOT|LAST_CLASS|SUBMIT|"
    r"AULA_EM|TROCA|REPOSIC|VAGA|PRAZO|PRESENCA|NOTA|FALTA|REMARC", re.IGNORECASE)


def is_perishable_edge(source: str, target: str, relation: str) -> bool:
    """True iff this edge encodes volatile SCHEDULE state (belongs to a live tool read, not the
    durable graph). Only inspects the relation name — dates are host-core."""
    return bool(_PERISHABLE_REL.search(relation or ""))
