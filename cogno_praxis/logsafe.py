"""What an identifier looks like in a LOG LINE: a short digest, never the identifier.

A scheduler scope is a tenant's id and a contact's channel id; a spreadsheet's key is whatever
the tenant called it and its id opens the document. Interpolated into a log line, each of them
is kept for as long as the log stream is — the one store a deletion request does not reach.

:func:`id_sha` is the SAME function the reference host uses for the same purpose
(``cogno_host.scope.scope_sha``): the first 12 hex characters of the SHA-256 of the value. It
is deliberately not a second algorithm. This library depends on nothing of the host, so the
function is written here and a test pins it to that definition — an operator holding a scope
computes one digest and finds the lines of both.

**What it is not.** An id is low-entropy: someone who can enumerate the plausible values can
hash them all and invert this. It is de-identification of the log stream, not encryption, and
salting it would break the one property that makes it useful.
"""

from __future__ import annotations

import hashlib

__all__ = ["id_sha"]


def id_sha(value: object, *, length: int = 12) -> str:
    """A short, stable digest of an identifier — ``""`` for a blank or ``None`` value. Never
    raises: a log line must not be the reason a request dies."""
    if not value:
        return ""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:length]
