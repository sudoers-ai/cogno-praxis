"""ONE e-mail address, or not — the question a recipient is asked before anything is mailed to it.

The rule is the host's (``cogno_host.onboarding.is_email``, cogno-host #1242): a local part of
word characters, ``.``, ``+`` and ``-``; one ``@``; a domain label; a dot; the rest of the domain.
``fullmatch``, so NOTHING may follow or precede the address — not a second ``@``, not a blank
inside it or at either end, not a line break, not a second address after a ``;``. It is written
here again rather than imported because praxis does not import the host; a host test pins that
the two accept the same values.

Asked of the value AS WRITTEN. A blank at an end is NOT trimmed before the question: trimming would
be a silent repair of what the tenant typed, and a value nobody fixed is a value nobody checked.
Deliberately permissive otherwise (no length rules, no TLD list): refusing a real address is worse
than sending to an odd one, and the mail server still has the last word.
"""

from __future__ import annotations

import re

_ONE_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+\.[\w][\w.-]*")

#: The closed reason a refused recipient carries — the host's spelling (``outbound_mail``).
INVALID_RECIPIENT = "invalid_recipient"


def is_one_address(value: object) -> bool:
    """Is ``value``, as written, exactly ONE e-mail address? ``False`` for anything that is not
    text. Never raises."""
    return isinstance(value, str) and _ONE_ADDRESS.fullmatch(value) is not None
