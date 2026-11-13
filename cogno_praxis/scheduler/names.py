"""The ONE name checker for the agenda — folding, normalisation, host matching, labelling.

Extracted here so there is a single definition of *does this free string name this
professional?*, shared by two callers that must never disagree:

* :class:`cogno_praxis.scheduler.service.SchedulerService` — resolving the professional a
  booking acts on (``_host_candidates`` delegates here); and
* :mod:`cogno_praxis.scheduler.catalog` — matching the professionals a service line names
  against the schedulable catalogue, so a name that resolves to nobody (or to two people)
  invalidates the line instead of inventing a professional or picking the first of two.

A second copy of this matcher would let the SECRETARY offer a service by a name the booking
path then fails to resolve, or the reverse. Pure, no I/O.
"""

from __future__ import annotations

import re
import unicodedata

from cogno_praxis.honorifics import is_host_name_title
from cogno_praxis.scheduler.store import Host


def _fold(s: str) -> str:
    """The ecosystem's ONE fold — a REPLICA of ``cogno_host.textfold.fold`` (its base, no flags).

    NFKD → combining marks removed → ``casefold()``: the host's operations in the host's order
    (NFKD FIRST, which is what makes the fold idempotent — ``lower`` first left the characters
    whose compatibility decomposition is upper-case, the mathematical "fancy" letters of many
    WhatsApp display names among them, upper-case after folding). The contract is SYNC WITH THE
    HOST: ``cogno-host`` pins this function against its own over 100 000 strings, because a copy
    that answered differently would find a professional here that the host could not, or the
    reverse.
    """
    folded = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in folded if not unicodedata.combining(ch)).casefold()


def _norm_host(s: str) -> str:
    """Fold to a comparable key for fuzzy host matching: accent-free, no honorific, alnum only —
    so 'dr_otavio_renan_bertholdi', 'Dr. Otávio Renan Bertholdi' and 'otaviorenanbertholdi'
    all collapse equal."""
    folded = _fold(s)
    for hon in ("dra", "dr", "sr", "sra"):
        folded = folded.replace(hon, "")
    return "".join(ch for ch in folded if ch.isalnum())


# Honorifics as WHOLE tokens (the one list, :mod:`cogno_praxis.honorifics`). ``_norm_host`` strips
# them as substrings anywhere in the string, which is fine for collapsing one name to one key and
# wrong for splitting a name into words ("Pedro" would lose its "dr"). The two normalisers
# therefore stay separate.


def _host_tokens(s: str) -> "frozenset[str]":
    """The folded word tokens of a person's name, honorifics dropped, 1-char words dropped.

    Token-wise, unlike :func:`_norm_host`, which collapses the whole string to a single key.
    A contact says "a Dra. Marina" and the catalogue holds "Dra. Marina Aloe": only a token
    comparison can tell *every word they said is in this name* from *no match at all*, and
    that difference is what separates "book it" from "ask which one".

    One-character tokens are dropped from the QUERY side on purpose — a bare initial matches
    almost anything, and a match that loose is exactly what must not resolve to one agenda.
    """
    return frozenset(t for t in re.split(r"[\W_]+", _fold(s)) if len(t) > 1
                     and not is_host_name_title(t))


def host_label(h: Host) -> str:
    """How ``list_schedulable_hosts`` names a professional: the name, then the role in brackets.

    The ONE spelling of that line. The resolver accepts it back as that professional: a model
    copies the line it was shown into ``host_name``, and a door that refused its own list's label
    turned a «sim» into "nobody bookable here goes by that" for the very person just listed. The
    catalogue import door reuses it so two namesakes are told apart by the SAME label the list
    prints.
    """
    return h.name + (f" ({h.role})" if h.role else "")


def host_candidates(text: str, hosts: "list[Host]", *, by_role: bool = True) -> "list[Host]":
    """Every catalogue host a free string could mean — 0, 1 or many. Never picks.

    Three tiers, first non-empty wins, each STRICTER than the phrase it answers:
    the catalogue key itself (id, full name, or the line ``list_schedulable_hosts`` printed —
    :func:`host_label` — accent/honorific/separator-insensitive), then *every word the caller
    said is a word of this name* ("Marina" → "Dra. Marina Aloe"), then a specialty
    ("o cardiologista"). A tier that matches two hosts returns both, so the caller asks instead
    of guessing — the old resolver collapsed that case into "unknown host", which reads as
    *nobody* when the truth is *which of these two*.

    ``by_role=False`` drops the third tier. The catalog's «who performs it» cell names PEOPLE: a
    specialty that happened to match the only professional who has it would link the service to
    them, and move it silently to a different person the day a second one with that specialty
    joins. The booking resolver keeps the tier («quero marcar com o cardiologista»).
    """
    key = _norm_host(text)
    if key:
        exact = [h for h in hosts
                 if key in (_norm_host(h.host_id), _norm_host(h.name), _norm_host(host_label(h)))]
        if exact:
            return exact
    want = _host_tokens(text)
    if want:
        partial = [h for h in hosts
                   if want <= (_host_tokens(h.name) | _host_tokens(h.host_id))]
        if partial:
            return partial
    if key and by_role:
        return [h for h in hosts if h.role and _norm_host(h.role) == key]
    return []
