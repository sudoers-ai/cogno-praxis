"""The size of a proposed change: every CLOSED rule has a twin (LARGE) and a control (SMALL).

Each control is the twin with exactly the one fact the rule reads taken away, so a rule that fired
on something else would fail its control, and a rule switched off would fail its twin. The
boundary of the diff rule is pinned at both sides (200 small, 201 large), doubt is LARGE, and
``escalate`` can never lower.
"""

from __future__ import annotations

import inspect

import pytest

from cogno_praxis.admin.impact import (
    MAX_SMALL_DIFF_LINES,
    RULES,
    Change,
    Classification,
    PathChange,
    classify,
    escalate,
)

#: A path every rule leaves SMALL: a vertical's service code, a few lines.
_SMALL = PathChange("cogno_praxis/scheduler/service.py", 3, 1)


def _one(path: str, added: "int | None" = 3, removed: "int | None" = 1, created: bool = False,
         kind: "str | None" = "correction", **flags) -> Classification:
    """One path, declared a CORRECTION unless told otherwise — so every path rule below is
    measured on the one kind that can be small, and the kind never explains a LARGE by itself."""
    return classify(Change((PathChange(path, added, removed, created),), kind=kind, **flags))


def _rules(c: Classification) -> "set[str]":
    return {r.split(":", 1)[0] for r in c.reasons}


def test_the_baseline_is_small_with_no_reasons():
    c = classify(Change((_SMALL,), kind="correction"))
    assert c == Classification("small", ())


# ── question 0: does it CORRECT or ADD? ──────────────────────────────────────────────────────
def test_a_small_correction_is_small():
    assert _one("cogno_praxis/scheduler/prompts/voice.txt", 1, 1).size == "small"


@pytest.mark.parametrize("kind", ["improvement", "evolution"])
def test_a_small_diff_that_adds_is_large(kind):
    """The twin: the same one-line diff as the correction above, declared as an addition."""
    c = _one("cogno_praxis/scheduler/prompts/voice.txt", 1, 1, kind=kind)
    assert c.size == "large" and _rules(c) == {"not_a_correction"}
    assert kind in c.reasons[0]


@pytest.mark.parametrize("kind", [None, "", "   ", "Correction", " correction", "fix", "bugfix",
                                  "small", 1, True])
def test_a_kind_missing_blank_or_unknown_is_large(kind):
    c = _one("cogno_praxis/scheduler/prompts/voice.txt", 1, 1, kind=kind)
    assert c.size == "large" and _rules(c) == {"kind_not_declared"}
    assert c.reasons[0].startswith("kind_not_declared: kind not declared")


def test_the_kind_defaults_to_not_declared():
    c = classify(Change((_SMALL,)))
    assert c.size == "large" and _rules(c) == {"kind_not_declared"}


def test_a_new_tool_is_large_even_as_a_correction():
    c = _one("cogno_praxis/scheduler/server.py", 10, 0, new_tool=True)
    assert c.size == "large" and _rules(c) == {"new_capability"}


@pytest.mark.parametrize("path,rule", [
    ("cogno_praxis/scheduler/prompts/scope.txt", "scope_or_limits"),
    ("cogno_praxis/scheduler/store.py", "store_or_schema"),
    ("pyproject.toml", "dependency"),
    ("cogno_praxis/admin/service.py", "admin_code")])
def test_a_correction_that_touches_a_closed_path_is_still_large(path, rule):
    assert _rules(_one(path, 1, 1)) == {rule}


def test_a_large_correction_by_size_is_still_large():
    assert _rules(_one(_SMALL.path, 201, 0)) == {"diff_size"}


@pytest.mark.parametrize("path", [
    "cogno_praxis/scheduler/service.py", "cogno_praxis/scheduler/prompts/system.txt",
    "cogno_praxis/bookkeeper/prompts/voice.txt", "cogno_praxis/render.py",
    "tests/unit/test_scheduler_service.py", "docs/BOOKKEEPER.md", "README.md", "CHANGELOG.md",
    "examples/host_min.py", "cogno_praxis/coordinator/server.py"])
def test_the_known_small_kinds_stay_small(path):
    assert _one(path).size == "small", path


# ── rule 1: a new vertical, persona or tool ──────────────────────────────────────────────────
@pytest.mark.parametrize("flag", ["new_vertical", "new_persona", "new_tool"])
def test_new_capability_declared_twin_and_control(flag):
    assert "new_capability" in _rules(_one(_SMALL.path, **{flag: True}))
    assert _one(_SMALL.path, **{flag: False}).size == "small"


@pytest.mark.parametrize("path", ["cogno_praxis/florist/__init__.py",
                                  "cogno_praxis/florist/server.py",
                                  "cogno_praxis/scheduler/prompts/greeting.txt"])
def test_new_capability_derived_from_a_created_path_twin_and_control(path):
    twin = _one(path, created=True)
    assert twin.size == "large" and "new_capability" in _rules(twin)
    control = _one(path, created=False)      # the same path, edited — not created
    assert "new_capability" not in _rules(control)


# ── rule 2: scope.txt / limits.txt ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("slot", ["scope", "limits"])
def test_scope_or_limits_twin_and_control(slot):
    twin = _one(f"cogno_praxis/scheduler/prompts/{slot}.txt", 1, 0)
    assert twin.size == "large" and _rules(twin) == {"scope_or_limits"}
    for other in ("system", "voice"):
        assert _one(f"cogno_praxis/scheduler/prompts/{other}.txt", 1, 0).size == "small"


# ── rule 3: store or schema ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", ["cogno_praxis/scheduler/store.py",
                                  "cogno_praxis/bookkeeper/stores/postgres.py",
                                  "cogno_praxis/scheduler/stores/__init__.py",
                                  "cogno_praxis/companies/migrations/0002.py",
                                  "cogno_praxis/bookkeeper/migration_v2.py"])
def test_store_or_schema_twin(path):
    twin = _one(path)
    assert twin.size == "large" and "store_or_schema" in _rules(twin)


def test_store_or_schema_control_and_declared_flag():
    assert _one("cogno_praxis/scheduler/service.py").size == "small"
    assert _one("cogno_praxis/scheduler/storefront.py").size == "small"   # not store.py
    flagged = _one("cogno_praxis/scheduler/service.py", schema_change=True)
    assert _rules(flagged) == {"store_or_schema"}


# ── rule 4: dependencies ─────────────────────────────────────────────────────────────────────
def test_dependency_twin_and_control():
    assert _rules(_one("pyproject.toml", 1, 1)) == {"dependency"}
    assert _one("README.md", 1, 1).size == "small"


# ── rule 5: diff size, and its boundary ──────────────────────────────────────────────────────
def test_the_boundary_is_200_small_201_large():
    assert MAX_SMALL_DIFF_LINES == 200
    assert _one(_SMALL.path, 150, 50).size == "small"
    big = _one(_SMALL.path, 150, 51)
    assert big.size == "large" and _rules(big) == {"diff_size"}
    assert "201 lines" in big.reasons[0]


def test_the_diff_is_counted_over_all_paths_added_plus_removed():
    two = Change((PathChange("cogno_praxis/a.py", 100, 0), PathChange("docs/A.md", 0, 101)),
                 kind="correction")
    assert _rules(classify(two)) == {"diff_size"}
    two_small = Change((PathChange("cogno_praxis/a.py", 100, 0), PathChange("docs/A.md", 0, 100)),
                       kind="correction")
    assert classify(two_small).size == "small"


# ── rule 6: NEO's own code ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", ["cogno_praxis/admin/impact.py",
                                  "cogno_praxis/admin/prompts/voice.txt",
                                  "cogno_praxis/admin/__init__.py"])
def test_admin_code_twin(path):
    twin = _one(path, 1, 0)
    assert twin.size == "large" and "admin_code" in _rules(twin)


@pytest.mark.parametrize("path", ["cogno_praxis/Admin/service.py", "cogno_praxis/ADMIN/server.py",
                                  "cogno_praxis/admin.py", "cogno_praxis/Admin.py",
                                  "Cogno_Praxis/admin/impact.py", "cogno_praxis/admin.md"])
def test_admin_code_is_case_insensitive_twin(path):
    """A capital letter or a module beside the package is still NEO's own code: the rule only
    raises, so it reads the name the way a case-insensitive filesystem would."""
    assert "admin_code" in _rules(_one(path, 1, 0)), path


@pytest.mark.parametrize("path", ["cogno_praxis/admin_x.py", "cogno_praxis/admin_tools.py",
                                  "cogno_praxis/Admin_Tools.py", "cogno_praxis/ADMIN_X.PY",
                                  "cogno_praxis/admin_tools/service.py", "cogno_praxis/admin.pyi"])
def test_admin_code_covers_the_module_form_twin(path):
    """``cogno_praxis/admin.*`` and ``admin_*`` beside the package are NEO's code too (the same
    rule as the host's lock), in any case."""
    assert "admin_code" in _rules(_one(path, 1, 0)), path


@pytest.mark.parametrize("path", ["cogno_praxis/administrative.py", "cogno_praxis/adminx.py",
                                  "cogno_praxis/scheduler/admin_x.py", "cogno_praxis/sysadmin.py"])
def test_admin_code_module_form_control(path):
    """No separator after ``admin``, or not at the package root: not NEO's code."""
    assert "admin_code" not in _rules(_one(path, 1, 0)), path


@pytest.mark.parametrize("path,rule", [
    ("cogno_praxis/scheduler/prompts/Scope.txt", "scope_or_limits"),
    ("cogno_praxis/scheduler/prompts/LIMITS.txt", "scope_or_limits"),
    ("cogno_praxis/scheduler/Store.py", "store_or_schema"),
    ("cogno_praxis/bookkeeper/Stores/postgres.py", "store_or_schema"),
    ("PyProject.toml", "dependency")])
def test_every_path_rule_is_case_insensitive_twin(path, rule):
    assert rule in _rules(_one(path, 1, 0)), path


def test_a_created_vertical_is_seen_in_any_case():
    assert "new_capability" in _rules(_one("cogno_praxis/Florist/Server.py", created=True))


def test_admin_code_control():
    assert _one("cogno_praxis/administrative/service.py", 1, 0).size == "small"
    assert _one("cogno_praxis/Administrative/service.py", 1, 0).size == "small"
    assert _one("cogno_praxis/scheduler/admin.py", 1, 0).size == "small"   # not the package
    assert _one("docs/ADMIN.md", 1, 0).size == "small"


# ── doubt → large ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", [".github/workflows/ci.yml", "requirements.txt", "setup.cfg",
                                  "cogno_praxis/scheduler/data.json", "Makefile",
                                  "cogno_praxis/scheduler/prompts/system.md"])
def test_an_unknown_path_type_is_large(path):
    c = _one(path)
    assert c.size == "large" and "doubt" in _rules(c), path


@pytest.mark.parametrize("added,removed", [(None, 1), (1, None), (None, None), (-1, 0),
                                           (True, 0), (1.5, 0)])
def test_a_missing_or_unreadable_count_is_large(added, removed):
    c = _one(_SMALL.path, added, removed)
    assert c.size == "large" and _rules(c) == {"doubt"}


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.py", "cogno_praxis/../x.py",
                                  "cogno_praxis\\x.py", "", " README.md", "cogno_praxis//x.py",
                                  "./README.md"])
def test_a_path_that_does_not_read_is_large(path):
    c = _one(path)
    assert c.size == "large" and "doubt" in _rules(c), path


def test_a_change_with_no_path_is_large():
    c = classify(Change((), kind="correction"))
    assert c.size == "large" and _rules(c) == {"doubt"}


def test_every_reason_carries_a_closed_rule_code():
    c = classify(Change((PathChange("cogno_praxis/admin/store.py", 300, 0, True),
                         PathChange("pyproject.toml", None, 0)), kind="evolution", new_tool=True))
    assert _rules(c) <= set(RULES)
    assert _rules(c) == {"not_a_correction", "new_capability", "store_or_schema", "admin_code", "diff_size",
                         "dependency", "doubt"}


# ── escalate never lowers ────────────────────────────────────────────────────────────────────
def test_escalate_raises_small_to_large():
    small = classify(Change((_SMALL,), kind="correction"))
    assert small.size == "small"
    up = escalate(small, reason="touches a contract the host reads back")
    assert up.size == "large"
    assert up.reasons == ("escalated: by reviewer: touches a contract the host reads back",)


def test_escalate_keeps_large_large_and_its_reasons():
    large = _one("pyproject.toml")
    up = escalate(large, by="owner", reason="second look")
    assert up.size == "large"
    assert up.reasons[:-1] == large.reasons and up.reasons[-1].startswith("escalated: by owner")


@pytest.mark.parametrize("start", ["small", "large"])
def test_escalate_never_answers_small(start):
    for reason in ("x", "lower it please", "small"):
        assert escalate(Classification(start, ()), reason=reason).size == "large"


def test_escalate_takes_no_size():
    """The guarantee is STRUCTURAL: there is no parameter through which a size could be asked."""
    params = inspect.signature(escalate).parameters
    assert list(params) == ["classification", "by", "reason"]
    with pytest.raises(TypeError):
        escalate(Classification("large", ()), reason="x", size="small")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        escalate(Classification("large", ()), reason="x", to="small")  # type: ignore[call-arg]


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_escalate_refuses_a_blank_reason(reason):
    with pytest.raises(ValueError):
        escalate(Classification("small", ()), reason=reason)  # type: ignore[arg-type]


def test_a_classification_cannot_be_lowered_in_place():
    c = Classification("large", ("doubt: x",))
    with pytest.raises(Exception):
        c.size = "small"  # type: ignore[misc]
