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

Unset DSN is the normal case: the store tests skip on their own and nothing runs.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

# A database whose name says "test" is one someone is willing to lose. Anything else is
# assumed to be real until proven otherwise — a deployment is never worth a green test run.
_TEST_DB_MARKER = "test"


def names_a_test_database(dsn: str) -> bool:
    """Whether ``dsn`` targets a database safe to DROP TABLE in.

    Split out from the fixture so the predicate is unit-testable: the fixture's own body
    ends in ``pytest.exit``, which cannot be exercised from inside the same run.
    """
    return _TEST_DB_MARKER in urlsplit(dsn).path.lstrip("/").lower()


@pytest.fixture(autouse=True, scope="session")
def _refuse_non_test_database() -> None:
    """Abort the run when ``COGNO_TEST_PG_DSN`` does not name a test database."""
    dsn = os.environ.get("COGNO_TEST_PG_DSN", "").strip()
    if not dsn:
        return
    database = urlsplit(dsn).path.lstrip("/")
    if not names_a_test_database(dsn):
        pytest.exit(
            f"refusing to run: COGNO_TEST_PG_DSN points at database {database!r}, which is not "
            f"a test database (its name must contain {_TEST_DB_MARKER!r}). These tests DROP "
            f"TABLE — running them here would destroy real data. Create a throwaway database "
            f"(e.g. cogno_praxis_test) and point COGNO_TEST_PG_DSN at that instead.",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )
