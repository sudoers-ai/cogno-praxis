"""A safety gate on the database the destructive integration tests target.

The Postgres store tests here are destructive by design — ``_drop_and_store`` opens with
``DROP TABLE appointments CASCADE`` so each test starts from a known schema. That is fine
against a disposable database and catastrophic against a live one.

It is easy to point them at a live one: a dev shell usually already has ``COGNO_PG_DSN``
exported, and copying it into ``COGNO_TEST_PG_DSN`` is a single keystroke away. The
module docstring of ``test_postgres_store.py`` even used to *suggest* a DSN ending in
``/cogno`` — the demo box's live database name.

That is not hypothetical. On 2026-08-04 this suite ran against the live demo database and
dropped ``appointments`` and ``schedule_hosts``; ``cogno-engram``'s equivalent suite, run in
the same batch, dropped ``memories``/``knowledge_nodes``/``knowledge_edges`` and recreated
them with an 8-dimension embedding column against a 768-dimension embedder — an outage of the
memory layer, not just data loss. ``cogno-host`` already had this exact guard and was the only
repo of the three that refused. This is that guard, ported.

Since 2026-08-26 the disposable database is also the DEFAULT destination: with
``COGNO_TEST_PG_DSN`` unset, ``resolve_test_dsn`` aims at ``cogno_praxis_test`` on the local
server the shell already points at, and returns ``""`` (→ the old skip) when nothing is
listening there. Nobody types a database name, so nobody can type the wrong one.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Mapping
from functools import lru_cache
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import pytest

# A database whose name says "test" is one someone is willing to lose. Anything else is
# assumed to be real until proven otherwise — a deployment is never worth a green test run.
_TEST_DB_MARKER = "test"
_DSN_ENV = "COGNO_TEST_PG_DSN"


def names_a_test_database(dsn: str) -> bool:
    """Whether ``dsn`` targets a database safe to DROP TABLE in.

    Split out from the fixture so the predicate is unit-testable: the fixture's own body
    ends in ``pytest.exit``, which cannot be exercised from inside the same run.
    """
    return _TEST_DB_MARKER in urlsplit(dsn).path.lstrip("/").lower()


# ── the disposable database is the DEFAULT, not something you have to remember ───────────
#
# The guard above turns the 2026-08-04 mistake into a refusal, but it still leaves the
# person to TYPE a DSN — and the shape that did the damage is the one a dev shell hands
# you. So stop asking. With COGNO_TEST_PG_DSN unset the suite now aims at
# `cogno_praxis_test` on whatever LOCAL server the shell already points at.
#
# The database name is the part that is never carried across: `_for_test_database`
# OVERWRITES it. Handing this function the exact DSN that caused the outage returns the
# disposable one — which is what `tests/unit/test_integration_db_guard.py` pins, in both
# directions.
_TEST_DATABASE = "cogno_praxis_test"

# Only a LOCAL server is adopted implicitly. A `COGNO_PG_DSN` pointing at a managed cloud
# instance is somebody's production server, and `cogno_praxis_test` is not ours to create
# there.
_LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "0.0.0.0"})

_PROBE_TIMEOUT_S = 0.5


def _for_test_database(dsn: str) -> str:
    """``dsn`` with its database name REPLACED by this repo's disposable one."""
    return urlunsplit(urlsplit(dsn)._replace(path=f"/{_TEST_DATABASE}"))


def default_test_dsn(env: Mapping[str, str] | None = None) -> str:
    """Where the DSN-using tests go when nobody names a database.

    Server and credentials come from the ambient `COGNO_PG_DSN` when it is local, else from
    libpq's own `PG*` variables (whose defaults are what CI's postgres service container
    serves). The database is always `_TEST_DATABASE` — there is no input that changes it.
    """
    env = os.environ if env is None else env
    ambient = (env.get("COGNO_PG_DSN") or "").strip()
    if ambient and (urlsplit(ambient).hostname or "") in _LOCAL_HOSTS:
        return _for_test_database(ambient)
    host = env.get("PGHOST") or "localhost"
    return (f"postgresql://{env.get('PGUSER') or 'postgres'}:"
            f"{env.get('PGPASSWORD') or 'postgres'}@"
            f"{quote(host, safe='') if host.startswith('/') else host}:"
            f"{env.get('PGPORT') or '5432'}/{_TEST_DATABASE}")


@lru_cache(maxsize=None)
def _server_is_listening(dsn: str) -> bool:
    """Whether something answers at ``dsn``'s address — a TCP probe, no query, no auth.

    Keeps the old ergonomics: with no server around, the modules skip exactly as they did
    when the variable was simply unset. A box with no Postgres must not go red.
    """
    parts = urlsplit(dsn)
    host = unquote(parts.hostname or "localhost")
    if host.startswith("/"):
        return os.path.exists(host)
    try:
        with socket.create_connection((host, parts.port or 5432), _PROBE_TIMEOUT_S):
            return True
    except OSError:
        return False


def resolve_test_dsn(env: Mapping[str, str] | None = None) -> str:
    """The DSN the DSN-using tests run against; ``""`` means skip.

    An explicit COGNO_TEST_PG_DSN wins — including a dangerous one, which is the whole
    point: it must reach the collection guard by name rather than be silently corrected.
    """
    env = os.environ if env is None else env
    explicit = (env.get(_DSN_ENV) or "").strip()
    if explicit:
        return explicit
    fallback = default_test_dsn(env)
    return fallback if _server_is_listening(fallback) else ""


def pytest_collection_modifyitems(items) -> None:
    """Abort when a DSN-using test is about to run against a non-test database.

    Checks the RESOLVED DSN, not the raw variable: the guard has to inspect the same string
    the fixtures will open, or the two can drift apart and only one of them is checked.

    Fires on COLLECTION, not on every session in this directory. Four of the six modules
    here (the MCP-over-stdio ones) never open a Postgres connection, and a stale
    ``COGNO_TEST_PG_DSN`` in someone's shell must not stop them: a guard annoying enough to
    be worked around is a guard that stops guarding. The trigger is a collected test whose
    module reads the DSN — those are the ones that ``DROP TABLE``.

    An unreachable server resolves to ``""``: those modules skip on their own, as before.
    """
    dsn = resolve_test_dsn()
    if not dsn or names_a_test_database(dsn):
        return
    if not any(getattr(getattr(i, "module", None), "DSN", None) for i in items):
        return                                   # nothing collected would touch that database
    database = urlsplit(dsn).path.lstrip("/")
    pytest.exit(
        f"refusing to run: {_DSN_ENV} points at database {database!r}, which is not "
        f"a test database (its name must contain {_TEST_DB_MARKER!r}). These tests DROP "
        f"TABLE — running them here would destroy real data. Unset {_DSN_ENV} and the suite "
        f"aims at {_TEST_DATABASE!r} on the same server by itself.",
        returncode=pytest.ExitCode.USAGE_ERROR,
    )
