"""The ONE table of honorifics: words that address a person and are no part of the name.

Three readers of a person's name kept a list each, and the copies drifted apart. They now read
this table — but each reader strips EXACTLY the subset it stripped before (12/11): consolidating
is not widening. A word joins a reader's subset only in a change of its own, with the real form
that asks for it and a collision twin in Portuguese («seu» is also the possessive). The host
imports these instead of keeping copies.

Tokens are compared FOLDED (lower case, no accents) with a trailing dot removed, so «Prof.»,
«prof» and «PROF» are one word. This module answers whether ONE token is a title for a given
reader, never what is left of a name.
"""

from __future__ import annotations

#: Titles of a NAME in a schedule QUERY, dropped from its front (the coordinator's
#: ``_drop_leading_title``; the host's ``google_workspace`` name words mirror it).
QUERY_NAME_TITLES: frozenset[str] = frozenset({
    "prof", "profa", "professor", "professora", "dr", "dra", "doutor", "doutora", "mestre",
    "sr", "sra",
})

#: Titles dropped from BOTH sides of the agenda host match (the scheduler's ``_host_tokens``).
HOST_NAME_TITLES: frozenset[str] = frozenset({"dr", "dra", "sr", "sra", "prof", "profa"})

#: Forms of address the host's persona ROUTING skips (``cogno_host.assembler``). No praxis reader
#: strips these from a name.
ROUTING_ADDRESS: frozenset[str] = frozenset({
    "senhor", "senhora", "sr", "sra", "srta", "dona", "seu", "dr", "dra", "doutor", "doutora",
    "prof", "professor", "professora", "mr", "mrs", "ms", "miss", "sir", "don", "senor", "senora",
})

#: Every word some reader treats as a title — the whole table, for documentation and drift tests.
HONORIFICS: frozenset[str] = QUERY_NAME_TITLES | HOST_NAME_TITLES | ROUTING_ADDRESS


def _bare(token: str) -> str:
    return str(token or "").strip().strip(".")


def is_query_name_title(token: str) -> bool:
    """Is ``token`` (already folded) a title the schedule QUERY drops from a name's front?"""
    return _bare(token) in QUERY_NAME_TITLES


def is_host_name_title(token: str) -> bool:
    """Is ``token`` (already folded) a title the agenda HOST match drops from both sides?"""
    return _bare(token) in HOST_NAME_TITLES
