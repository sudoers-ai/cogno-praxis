"""How a company is NAMED and IDENTIFIED — the two rules the row's key and its CNPJ obey.

Both were host code until this vertical existed, and both had to be re-expressed here rather
than imported, for the reason the ``bookkeeper`` server states about its ``_meta`` keys: a
vertical that could only do its job by importing the host would have the dependency arrow
backwards. ``cogno-praxis`` depends on ``mcp`` and nothing else.

A re-expressed rule is a DUPLICATED CONTRACT, and this project has watched those rot. The pin
therefore lives where BOTH copies are importable — the host, which has ``cogno_anima`` and this
package at once (``tests/unit/test_company_rules_match_the_core.py``). Here the copies are kept
byte-comparable on purpose: :func:`cnpj_valid` is the same weights and the same two check
digits as ``cogno_anima.security.detector.cnpj_valid``, and :func:`fold` is the base fold of
``cogno_host.textfold.fold`` with its ``punctuation=True`` step, which is the only combination
``company_id_for`` ever asked for.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# The punctuation a CNPJ is WRITTEN with, and nothing else. Removing it is normalisation;
# removing anything more would be guessing.
_CNPJ_PUNCTUATION = re.compile(r"[.\-/\s]")
# Fourteen ASCII digits. `str.isdigit()` is not this test — it is True for "²" and for
# Arabic-Indic digits, neither of which is a CNPJ, and `\d` under `re` matches them too.
_CNPJ_DIGITS = re.compile(r"\A[0-9]{14}\Z")


def fold(text: "str | None", *, punctuation: bool = False) -> str:
    """Lower-case and strip accents, so ``nao`` and ``não`` compare equal.

    ``punctuation`` turns every character that is neither alphanumeric nor whitespace into a
    space; runs are NOT collapsed (the caller splits). ``None`` folds to ``""``. ``ß`` stays
    ``ß`` — NFKD does not decompose it and ``lower()`` does not expand it.
    """
    folded = unicodedata.normalize("NFKD", (text or "").lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    if punctuation:
        folded = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in folded)
    return folded


def company_id_for(name: str) -> str:
    """The row's second key half, derived from the NAME — deterministic, so a re-registration
    UPDATES instead of piling up a row per turn.

    Folded through :func:`fold` rather than a private lower/strip, so "Padaria São João" and
    "padaria sao joao" are the same company. A name that folds to nothing (emoji, punctuation
    only) still needs a key, so it falls back to a digest of the raw name: also deterministic,
    so the upsert keeps its meaning for that name too.
    """
    slug = "-".join(fold(name, punctuation=True).split())[:120]
    if slug:
        return slug
    return "c-" + hashlib.sha256((name or "").encode("utf-8")).hexdigest()[:16]


def cnpj_valid(text: str) -> bool:
    """Brazilian CNPJ check-digit validation."""
    d = "".join(ch for ch in (text or "") if ch.isdigit() and ch.isascii())
    if len(d) != 14 or d == d[0] * 14:
        return False
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6] + w1
    for weights, pos in ((w1, 12), (w2, 13)):
        s = sum(int(d[i]) * weights[i] for i in range(pos))
        r = s % 11
        dv = 0 if r < 2 else 11 - r
        if dv != int(d[pos]):
            return False
    return True


def normalize_cnpj(raw: "str | None") -> str:
    """``raw`` with a CNPJ's own punctuation removed; ``""`` when nothing was supplied.

    ``"11.222.333/0001-81"`` and ``"11222333000181"`` are the same number and are stored the
    same way — digits only, so a read-back, a comparison and a later export cannot disagree
    about formatting.

    Everything that is NOT that punctuation is KEPT, and that is the load-bearing half. A
    normaliser that deleted letters would turn ``"não sei"`` into ``""`` — and ``""`` means
    *not supplied*, so a contact who said they did not know would be recorded as a company with
    no CNPJ and told the registration succeeded. Leaving the junk in makes :func:`cnpj_valid`
    refuse it, which is the honest answer.
    """
    return _CNPJ_PUNCTUATION.sub("", (raw or "").strip())


def cnpj_is_acceptable(normalized: str) -> bool:
    """May this NORMALISED value be stored? ``""`` (not supplied) yes; anything else must check.

    Written as *shape then checksum*: :func:`cnpj_valid` strips every non-digit before it
    counts, so it answers ``True`` for ``"11222333000181 e mais alguma coisa"``. The shape test
    is what stops a valid number with junk stapled to it from being stored as if it were clean.
    """
    if not normalized:
        return True
    return bool(_CNPJ_DIGITS.match(normalized)) and cnpj_valid(normalized)
