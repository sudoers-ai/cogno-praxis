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


def _conftest():
    spec = importlib.util.spec_from_file_location("_praxis_integ_conftest", _CONFTEST)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _guard():
    return _conftest().names_a_test_database


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


# ── blast radius: it aborts the dangerous run, not every run ─────────────────────────────
#
# Four of the six integration modules (the MCP-over-stdio ones) never open a Postgres
# connection. A stale COGNO_TEST_PG_DSN must not stop those: a guard annoying enough to be
# worked around is a guard that stops guarding. Subprocesses, because the abort ends the
# session it fires in.

_LIVE_DSN = "postgresql://x:y@localhost:5432/cogno"


def _run(target: str):
    import os
    import subprocess
    import sys
    return subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider",
         "--co", "-q"],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
        env={**os.environ, "COGNO_TEST_PG_DSN": _LIVE_DSN},
    )


def test_a_live_dsn_does_not_block_the_mcp_tests():
    r = _run("tests/integration/test_scheduler_via_mcp.py")
    assert "refusing to run" not in r.stdout, r.stdout[-1500:]
    assert r.returncode == 0, r.stdout[-1500:]


def test_a_live_dsn_does_block_the_destructive_module():
    """``--co`` opens no connection — so if the abort still fires, it fired FIRST.

    That distinction is the whole guard: a check that runs inside a fixture has already let
    ``pytest`` reach the point where the next statement is ``DROP TABLE``. ``cogno-host``
    carried exactly that shape (a session-scoped autouse fixture) until 2026-08-26.
    """
    r = _run("tests/integration/test_postgres_store.py")
    assert "refusing to run" in r.stdout, r.stdout[-1500:]
    assert "cogno" in r.stdout, "the abort must NAME the database it refused"
    assert r.returncode != 0


# ── the convention the guard rests on ────────────────────────────────────────────────────
#
# The trigger is a collected test whose module exposes a module-level ``DSN``. That makes the
# guard fail OPEN for a future module that reads COGNO_TEST_PG_DSN some other way — it would
# connect, DROP, and never trip the abort. Assert the convention instead of trusting it.

def test_every_module_reading_the_dsn_exposes_it_as_a_module_attribute():
    import re

    integ = Path(__file__).resolve().parents[1] / "integration"
    scanned = [f for f in sorted(integ.glob("test_*.py"))
               if "COGNO_TEST_PG_DSN" in f.read_text() or "resolve_test_dsn" in f.read_text()]
    offenders = [f.name for f in scanned if not re.search(r"^DSN\s*=", f.read_text(), re.M)]
    # A scan that matches nothing passes for free. Since the modules stopped reading the
    # variable directly (they call `resolve_test_dsn` now), the match term is the thing that
    # can silently go stale — so assert it still finds them.
    assert len(scanned) >= 2, f"the scan matched only {[f.name for f in scanned]}"
    assert not offenders, (
        f"{offenders} read COGNO_TEST_PG_DSN but expose no module-level `DSN`, so "
        f"pytest_collection_modifyitems in tests/integration/conftest.py cannot see them "
        f"and would let a DROP TABLE run against a live database."
    )


# ── the disposable database is the DEFAULT ───────────────────────────────────────────────
#
# Owner, 2026-08-26: "Já temos um test só para os testes de integração, isso deveria ser
# padrão." The guard turned the 2026-08-04 mistake into a refusal; this turns it into
# something nobody has to remember. What makes it safe is not a check but a construction:
# the database name is never carried in from anywhere, it is written.

def test_the_default_is_always_the_disposable_database():
    m = _conftest()
    # the very DSN that caused the outage, handed in as the ambient one
    got = m.default_test_dsn({"COGNO_PG_DSN": "postgresql://postgres:pw@localhost:55435/cogno"})
    assert got == "postgresql://postgres:pw@localhost:55435/cogno_praxis_test"
    assert m.names_a_test_database(got)


def test_the_default_keeps_the_server_and_credentials_it_was_given():
    # host, port, user and password ride across — only the database is replaced. Otherwise
    # "the default" would mean "a server nobody is running", i.e. a permanent skip.
    got = _conftest().default_test_dsn({"COGNO_PG_DSN": "postgresql://u:p@localhost:6000/cogno"})
    assert got == "postgresql://u:p@localhost:6000/cogno_praxis_test"


def test_no_ambient_dsn_falls_back_to_libpq_defaults_which_is_what_ci_serves():
    m = _conftest()
    assert m.default_test_dsn({}) == "postgresql://postgres:postgres@localhost:5432/cogno_praxis_test"
    assert m.default_test_dsn({"PGHOST": "db", "PGPORT": "6543", "PGUSER": "u", "PGPASSWORD": "s"}) \
        == "postgresql://u:s@db:6543/cogno_praxis_test"


def test_a_REMOTE_ambient_dsn_is_not_adopted():
    """`cogno_praxis_test` on someone's managed instance is not ours to create, let alone DROP."""
    got = _conftest().default_test_dsn({"COGNO_PG_DSN": "postgresql://u:p@db.prod.example.com:5432/cogno"})
    assert "prod.example.com" not in got
    assert got == "postgresql://postgres:postgres@localhost:5432/cogno_praxis_test"


def test_every_default_names_a_test_database_whatever_the_environment_says():
    m = _conftest()
    for env in ({}, {"COGNO_PG_DSN": _LIVE_DSN}, {"COGNO_PG_DSN": "postgresql:///cogno"},
                {"PGHOST": "h", "COGNO_PG_DSN": "postgresql://a:b@127.0.0.1/postgres"}):
        assert m.names_a_test_database(m.default_test_dsn(env)), env


def test_the_marker_lives_in_the_name_the_default_uses():
    # `_TEST_DATABASE` and `names_a_test_database` are two halves of one rule; if the
    # constant were ever renamed to something without "test", the default would build a
    # DSN its own guard refuses.
    m = _conftest()
    assert m.names_a_test_database(f"postgresql://h/{m._TEST_DATABASE}")


def test_an_explicit_dsn_still_wins_including_a_dangerous_one():
    # It must NOT be quietly corrected: the collection guard has to see it and say the name
    # out loud, or the person keeps a live DSN in their shell and never learns.
    assert _conftest().resolve_test_dsn({"COGNO_TEST_PG_DSN": _LIVE_DSN}) == _LIVE_DSN


def test_nothing_listening_means_skip_exactly_as_before():
    # port 1 answers nowhere; the modules' own `skipif(not DSN)` then does what it always did
    assert _conftest().resolve_test_dsn({"COGNO_PG_DSN": "postgresql://u:p@127.0.0.1:1/cogno"}) == ""
