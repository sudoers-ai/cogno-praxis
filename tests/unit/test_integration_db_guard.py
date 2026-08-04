"""The destructive-suite guard, exercised where CI actually runs it.

``tests/integration/conftest.py`` refuses to let the ``DROP TABLE`` suite run against a
database whose name does not say "test". The guard lives in the integration tree, which no
CI job executes — so its predicate is asserted here, in the unit tree, which every CI job does.

The case that motivated it: on 2026-08-04 the integration suite ran with
``COGNO_TEST_PG_DSN`` pointing at the live demo database ``.../cogno`` and dropped
``appointments`` and ``schedule_hosts``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_CONFTEST = Path(__file__).resolve().parents[1] / "integration" / "conftest.py"


def _guard():
    spec = importlib.util.spec_from_file_location("_praxis_integ_conftest", _CONFTEST)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.names_a_test_database


def test_refuses_the_live_database_name():
    # the exact DSN shape that did the damage — the demo box's live database
    assert not _guard()("postgresql://postgres:pw@localhost:55435/cogno")


def test_refuses_when_only_the_password_says_test():
    # the old module docstring suggested `postgresql://postgres:test@host:55432/cogno`:
    # "test" appears in the DSN, but the DATABASE is live. Matching the whole string would
    # have let exactly that through.
    assert not _guard()("postgresql://postgres:test@localhost:55432/cogno")


def test_accepts_a_throwaway_database():
    assert _guard()("postgresql://postgres:pw@localhost:55435/cogno_praxis_test")
    assert _guard()("postgresql://postgres:pw@localhost:5432/TEST_db")
