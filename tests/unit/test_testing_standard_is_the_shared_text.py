"""``docs/TESTING.md`` is the owner's minimum testing standard, and it is SHARED.

The same text lives, byte for byte, in every repository an agent works in (the host, praxis and
the dashboard), so that any reader — a person, or an agent arriving with no context — finds the
rule inside the repository it is changing, and finds the SAME rule in each one. A copy edited in
one repository alone would be a second standard that nobody agreed to.

So the file's sha256 is pinned here. Changing the text forces this test to change too, and the
digest may only move together with the shared text, in every repository at once.

TWIN (run): without the file the test fails; with one character changed it fails.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTING = ROOT / "docs" / "TESTING.md"

# sha256 of the shared standard, 2026-11-01.
EXPECTED_SHA256 = "c3a8092d98220af45c0c7517b07bf59b9ae6bf62b8247de3af0956f8f3f29708"


def test_the_testing_standard_is_byte_identical_to_the_shared_text() -> None:
    assert TESTING.is_file(), "docs/TESTING.md is missing: it is the shared testing standard."
    got = hashlib.sha256(TESTING.read_bytes()).hexdigest()
    assert got == EXPECTED_SHA256, (
        "docs/TESTING.md changed: it must stay byte-identical to the shared standard; "
        "update this digest only together with the shared text."
    )
