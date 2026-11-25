"""``BEYOND_HORIZON_NOTE`` names the 30-day window footer ONCE, with the SAME bytes.

The 30-day default window holds later classes back and ``_fmt_report`` says so with a fixed
note. A second reader — the host — appends its own "covers the next 30 days" line to any reply
or held delivery built from such a read, and it recognises the footer by importing this constant
rather than by copying the literal. So the literal became a module constant.

This is a pure extraction: the note is given a name, not a new wording. The gémeo pins both
halves of that claim — the footer IS the constant, and the constant is byte-for-byte what the
inline literal said before — so a future edit to the text cannot drift the two readers apart or
quietly move the output.
"""

from __future__ import annotations

from cogno_praxis.coordinator.server import BEYOND_HORIZON_NOTE, _fmt_report
from cogno_praxis.coordinator.types import ReadReport

#: The exact bytes the inline literal produced before the extraction (praxis main ``0a2d91a``).
#: Hard-coded on purpose: it is the independent witness that naming the note changed no output.
_FROZEN_LITERAL = (
    "(This list covers the next 30 days — this tool's default window when no period was "
    "asked for. Later classes are one argument away: call again with `month` set to the "
    "month the user names. Offer to look further ahead; do not say how many are out "
    "there.)"
)


def test_the_constant_is_byte_for_byte_the_old_literal():
    assert BEYOND_HORIZON_NOTE == _FROZEN_LITERAL


def test_fmt_report_renders_the_constant_and_nothing_else_changed():
    out = _fmt_report(ReadReport(errors=(), beyond_horizon=True))
    assert BEYOND_HORIZON_NOTE in out
    # The windowed read with no other flag renders exactly the note — byte-equal to before.
    assert out == _FROZEN_LITERAL


def test_no_beyond_horizon_no_note():
    out = _fmt_report(ReadReport(errors=(), beyond_horizon=False))
    assert BEYOND_HORIZON_NOTE not in out
