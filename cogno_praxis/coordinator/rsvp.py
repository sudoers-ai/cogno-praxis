"""The answer to a class invitation — its three states, and the pure rules that read them.

The invitation half already exists: the calendar export mails a professor their classes with
``RSVP=TRUE``, so the client offers accept and decline (``coordinator/ics.py``). This module is
the RETURN leg for the CHAT channel: the professor writes back, and what they said is recorded
against the class they named.

**The three states, and why one of them is never written.** ``PENDING`` is the ABSENCE of an
answer, not a value somebody stores: a class nobody has answered about is pending, and so is a
class whose answer this system refused to guess at. Only ``ACCEPTED`` and ``DECLINED`` are ever
written down, which is what makes "pending" impossible to fabricate — there is no code path that
can produce it except *nothing was recorded*, which is the truth it is supposed to mean.

**Where the state lives is the tenant's own STATUS column** (``COLUMN_STATUS``), the one
``server._entry_status`` already reads onto every listing line. That choice is what keeps this
from being a second copy of a fact: an answer recorded here shows up in the weekly briefing, the
daily check and the schedule listing with no reader written for it, and the secretary sees it in
the spreadsheet they already keep. It also survives the process — the vertical is spawned once
per turn, so anything held in memory is gone before the next message arrives.

**The labels are the tenant's words, the states are ours.** The cell holds Portuguese a human
reads ("Aceita"); the code compares closed English constants. The two are joined here, in one
table, so no caller has to know both.
"""

from __future__ import annotations

import unicodedata
from typing import Optional

#: An invitation nobody has answered — or one this system refused to link to an answer. Never
#: written to a cell: it IS the empty cell (or the tenant's own ordinary status).
RSVP_PENDING = "PENDING"
RSVP_ACCEPTED = "ACCEPTED"
RSVP_DECLINED = "DECLINED"

#: The closed vocabulary, in the order a reader meets them.
VALID_RSVP: tuple[str, ...] = (RSVP_PENDING, RSVP_ACCEPTED, RSVP_DECLINED)

#: What a caller may ASK to record — the two answers, and deliberately not the third. A tool
#: argument is a closed field, not a sentence: the contact's "sim" is turned into one of these
#: by the model that read it, and anything else is refused by name rather than interpreted.
RECORDABLE: tuple[str, ...] = (RSVP_ACCEPTED, RSVP_DECLINED)


def _norm(s: str) -> str:
    """Accent- and case-folded, for comparing a human's spelling of a label with the tenant's.

    The same folding the rest of the vertical uses (``service._norm``, ``server._norm``); it is
    re-stated rather than imported because this module is pure and imports nothing from either.
    """
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").strip().lower())
                   if not unicodedata.combining(c))


def parse_answer(raw: str) -> str:
    """A caller's ``answer`` argument → ``RSVP_ACCEPTED``/``RSVP_DECLINED``, or ``""``.

    ``""`` means *not one of the two*, and the caller must refuse rather than pick one. There is
    no third reading and no fuzzy match on purpose: this is the field where an ambiguous answer
    would become a commitment, and the only safe way to be unsure here is to say so."""
    n = _norm(raw)
    for state in RECORDABLE:
        if n == state.lower():
            return state
    return ""


def state_of(cell: str, *, accepted: str, declined: str,
             ordinary: "tuple[str, ...]" = ()) -> Optional[str]:
    """What one status cell says, in this module's vocabulary — or ``None`` for *not ours*.

    Four readings, and the fourth is the one that matters:

    * empty, or one of the tenant's ``ordinary`` labels ("Confirmado") → ``RSVP_PENDING``. The
      routine state of a scheduled class is not an answer, and treating it as one would report
      every class in the sheet as accepted.
    * the tenant's accepted/declined label → that state.
    * **anything else → ``None``.** A cell holding a word this system did not write is a note a
      human left in the tenant's own spreadsheet, and it is not this feature's to overwrite —
      ``None`` is what a caller reads to stop and say what is there instead. The ``Optional``
      says "unreadable", never "nothing"; collapsing it into ``PENDING`` would silently hand a
      secretary's note to the next answer that comes in.
    """
    val = (cell or "").strip()
    if not val or any(_norm(val) == _norm(o) for o in ordinary):
        return RSVP_PENDING
    if _norm(val) == _norm(accepted):
        return RSVP_ACCEPTED
    if _norm(val) == _norm(declined):
        return RSVP_DECLINED
    return None


def label_for(state: str, *, accepted: str, declined: str) -> str:
    """The tenant's own word for a state — ``""`` for ``PENDING``, which is written as an empty
    cell because that is exactly what it means: no answer on file."""
    if state == RSVP_ACCEPTED:
        return accepted
    if state == RSVP_DECLINED:
        return declined
    return ""
