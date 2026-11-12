"""The ONE list of honorifics: words that address a person and are no part of the name.

Three readers of a person's name used to keep a list each, and the lists drifted: the
coordinator's schedule query dropped «professor» and «doutora» but not «senhor», the
scheduler's host matcher dropped «dr» and «sra» but not «professor» or «doutor», and the host
kept two more. One title therefore resolved a person in one place and missed them in the next.
Every reader now takes the list from here; the host imports :data:`HONORIFICS` and
:func:`is_honorific` from this module instead of copying them.

Tokens are compared FOLDED (lower case, no accents) with a trailing dot removed, so «Prof.»,
«prof» and «PROF» are one word. A word that is a title only is the caller's business: this
module answers whether ONE token is a title, never what is left of a name.
"""

from __future__ import annotations

#: Folded forms of titles and forms of address, Portuguese, Spanish and English.
HONORIFICS: frozenset[str] = frozenset({
    "dr", "dra", "doutor", "doutora",
    "prof", "profa", "professor", "professora",
    "mestre",
    "sr", "sra", "srta", "senhor", "senhora", "dona", "seu",
    "senor", "senora",
    "mr", "mrs", "ms", "miss", "sir", "don",
})


def is_honorific(token: str) -> bool:
    """Is ``token`` (already folded) a title — «dra», «prof.», «senhor»?"""
    return str(token or "").strip().strip(".") in HONORIFICS
