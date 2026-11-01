"""The NEO scope lock: ``scripts/neo_scope_check.py`` and the workflow that runs it.

NEO's pull requests (head branch ``neo/<request_id>``) may change the verticals' skills under
``cogno_praxis/`` and nothing else: not the system, not NEO's own admin package. What is pinned:

* **The two allowed shapes pass**: a prompt edit and a service edit.
* **Every refused class is refused AND named** — the build configuration, the lock files, the
  workflows, the checker, the docs, the tests, the admin package (in any case), renames both
  ways, symlinks, executables, mode changes, traversal, dotfiles, file types.
* **The empty diff is refused** (a checker that read nothing must not pass it).
* **Real git, not only fake diffs**: a throwaway repository proves the checker reads the
  records git actually emits — and proves why it reads ``--raw``: ``--name-status`` prints a
  ``chmod +x`` as a plain ``M`` and a symlink as a plain ``A``.
* **The workflow**: the job's ``if:`` is exactly the ``neo/`` prefix, it runs on
  ``pull_request_target`` (so the BASE's workflow and checker judge the PR, never the PR's own
  edited copy), and no ``${{ }}`` reaches a ``run:`` block.

Pure: no network. The git tests run ``git`` in ``tmp_path`` with the user's config cut off.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "neo_scope_check.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "neo-scope.yml"

_spec = importlib.util.spec_from_file_location("neo_scope_check", SCRIPT)
assert _spec and _spec.loader
nsc = importlib.util.module_from_spec(_spec)
sys.modules["neo_scope_check"] = nsc
_spec.loader.exec_module(nsc)

Z = "0" * 7
SHA = "a" * 7


def rec(status: str, path: str, old: "str | None" = None, *, old_mode: str = "100644",
        new_mode: str = "100644") -> str:
    """One ``git diff --raw -z`` record."""
    if status == "A":
        old_mode = "000000"
    if status == "D":
        new_mode = "000000"
    head = f":{old_mode} {new_mode} {SHA if old_mode != '000000' else Z} {Z} {status}"
    paths = [old, path] if old is not None else [path]
    return "\0".join([head, *paths]) + "\0"


def verdict(*records: str, allow_tests: bool = False) -> "list[tuple[str, str]]":
    return [(r.path, r.rule) for r in
            nsc.check(nsc.parse_raw_z("".join(records)), allow_tests=allow_tests)]


# ── allowed ─────────────────────────────────────────────────────────────────────────────
def test_a_prompt_edit_is_in_scope():
    assert verdict(rec("M", "cogno_praxis/coordinator/prompts/system.txt")) == []


def test_a_service_edit_is_in_scope():
    assert verdict(rec("M", "cogno_praxis/bookkeeper/service.py")) == []


def test_adding_and_deleting_a_skill_file_is_in_scope():
    assert verdict(rec("A", "cogno_praxis/scheduler/prompts/new_rule.txt"),
                   rec("D", "cogno_praxis/scheduler/old_helper.py"),
                   rec("M", "cogno_praxis/py.typed")) == []


def test_a_rename_inside_the_scope_is_in_scope():
    assert verdict(rec("R100", "cogno_praxis/closer/b.py", "cogno_praxis/closer/a.py")) == []


def test_a_vertical_subdirectory_named_admin_is_not_the_admin_package():
    """Only the package's own ``admin`` (``cogno_praxis/admin``) is NEO's code."""
    assert verdict(rec("M", "cogno_praxis/scheduler/admin/rules.py")) == []


# ── refused, by class, each one named ──────────────────────────────────────────────────
@pytest.mark.parametrize("path", [
    "pyproject.toml", "uv.lock", "poetry.lock", "requirements.txt", "setup.py",
    ".github/workflows/ci.yml", ".github/workflows/neo-scope.yml", ".github/CODEOWNERS",
    "scripts/neo_scope_check.py", "scripts/other.py",
    "docs/NEO_SCOPE.md", "docs/HOST_INTEGRATION.md", "README.md", "CHANGELOG.md", "LICENSE",
    "tests/unit/test_coordinator_prompts.py", "tests/integration/conftest.py",
    "tests/unit/test_neo_scope_check.py", "examples/run.py",
    "cogno_praxis",                      # the root itself, as a file: not UNDER the directory
    "Cogno_Praxis/scheduler/service.py",  # case: not literally the package
])
@pytest.mark.parametrize("status", ["A", "M", "D"])
def test_everything_outside_the_package_is_refused(path, status):
    got = verdict(rec(status, path))
    rule = "hidden" if path.startswith(".") else "outside_scope"
    assert got == [(path, rule)], got


@pytest.mark.parametrize("path", [
    "cogno_praxis/admin/neo.py", "cogno_praxis/admin/prompts/system.txt",
    "cogno_praxis/Admin/neo.py", "cogno_praxis/ADMIN/neo.py", "cogno_praxis/aDmIn/x.txt",
    "cogno_praxis/admin.py",  # a module of the same name is the same import
])
def test_the_admin_package_is_refused_in_any_case(path):
    assert verdict(rec("M", path)) == [(path, "admin")]


def test_a_rename_from_the_scope_to_outside_is_refused_on_both_records():
    got = verdict(rec("R100", "tests/unit/test_x.py", "cogno_praxis/scheduler/x.py"))
    assert got == [("tests/unit/test_x.py", "outside_scope"),
                   ("cogno_praxis/scheduler/x.py -> tests/unit/test_x.py", "rename_across")]


def test_a_rename_from_outside_into_the_scope_is_refused():
    """The SOURCE is a deleted path too: checking only the destination would let a pull
    request move a test (or the checker) into the package and delete it from where it ran."""
    got = verdict(rec("R097", "cogno_praxis/scheduler/x.py", "scripts/neo_scope_check.py"))
    assert got == [("scripts/neo_scope_check.py", "outside_scope"),
                   ("scripts/neo_scope_check.py -> cogno_praxis/scheduler/x.py",
                    "rename_across")]


def test_a_rename_into_the_admin_package_is_refused():
    got = verdict(rec("R100", "cogno_praxis/admin/x.py", "cogno_praxis/scheduler/x.py"))
    assert ("cogno_praxis/admin/x.py", "admin") in got
    assert any(rule == "rename_across" for _, rule in got)


def test_a_copy_across_the_boundary_is_refused():
    got = verdict(rec("C100", "cogno_praxis/scheduler/x.py", "tests/unit/test_y.py"))
    assert ("tests/unit/test_y.py", "outside_scope") in got


@pytest.mark.parametrize("status,old_mode,new_mode,rule", [
    ("A", "000000", "120000", "mode"),         # a new symlink
    ("T", "100644", "120000", "mode"),         # a file turned into a symlink
    ("A", "000000", "100755", "mode"),         # a new executable
    ("M", "100644", "100755", "mode"),         # chmod +x
    ("A", "000000", "160000", "mode"),         # a submodule
    ("M", "100755", "100644", "mode_change"),  # chmod -x is still a mode change
    ("T", "120000", "100644", "mode_change"),  # a symlink turned into a file
])
def test_a_symlink_an_executable_or_a_mode_change_is_refused(status, old_mode, new_mode, rule):
    path = "cogno_praxis/scheduler/service.py"
    head = f":{old_mode} {new_mode} {SHA} {SHA} {status}\0{path}\0"
    assert verdict(head) == [(path, rule)]


def test_a_rename_that_changes_the_mode_is_refused():
    head = (":100644 100755 aaaaaaa aaaaaaa R100\0"
            "cogno_praxis/scheduler/a.py\0cogno_praxis/scheduler/b.py\0")
    assert verdict(head) == [("cogno_praxis/scheduler/b.py", "mode")]


def test_deleting_a_symlink_inside_the_scope_is_not_a_mode_offence():
    head = f":120000 000000 {SHA} {Z} D\0cogno_praxis/scheduler/link.txt\0"
    assert verdict(head) == []


@pytest.mark.parametrize("path,rule", [
    ("cogno_praxis/../pyproject.toml", "traversal"),
    ("cogno_praxis/scheduler/../../scripts/neo_scope_check.py", "traversal"),
    ("cogno_praxis/./scheduler/x.py", "traversal"),
    ("cogno_praxis//scheduler/x.py", "traversal"),
    ("cogno_praxis/scheduler/", "traversal"),
    ("/cogno_praxis/scheduler/x.py", "absolute"),
    ("cogno_praxis\\..\\pyproject.toml", "path_chars"),
    ("cogno_praxis/admın/x.py", "path_chars"),       # dotless i
    ("cogno_praxis/scheduler/x\ny.py", "path_chars"),
    ("cogno_praxis/scheduler/a b.py", "path_chars"),
    ("cogno_praxis/.gitattributes", "hidden"),
    ("cogno_praxis/scheduler/.hidden/x.py", "hidden"),
])
def test_a_path_that_could_pass_for_another_is_refused(path, rule):
    assert verdict(rec("M", path)) == [(path, rule)]


@pytest.mark.parametrize("path", [
    "cogno_praxis/scheduler/server.cpython-312-x86_64-linux-gnu.so",
    "cogno_praxis/scheduler/__pycache__/server.cpython-312.pyc",
    "cogno_praxis/scheduler/x.pth", "cogno_praxis/scheduler/run.sh",
    "cogno_praxis/scheduler/prompts/system.txt.bak", "cogno_praxis/scheduler/data.json",
])
def test_a_file_type_a_skill_is_not_made_of_is_refused(path):
    assert verdict(rec("A", path)) == [(path, "file_type")]


def test_the_allowed_types_are_exactly_what_the_package_holds():
    """``ALLOWED_SUFFIXES``/``ALLOWED_NAMES`` are a MEASUREMENT of the package; a new type in
    the package must be a decision written there, not a refusal NEO meets by surprise."""
    tracked = subprocess.run(["git", "ls-files", "cogno_praxis"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    assert tracked, "git ls-files read nothing — this guard would pass over an empty set"
    outside = [p for p in tracked if p.rsplit("/", 1)[-1] not in nsc.ALLOWED_NAMES
               and not p.endswith(tuple(nsc.ALLOWED_SUFFIXES))]
    assert outside == []
    names = {p.rsplit("/", 1)[-1] for p in tracked}
    suffixes = {Path(p).suffix for p in tracked if p.rsplit("/", 1)[-1] not in nsc.ALLOWED_NAMES}
    # Both directions: nothing allowed that the package does not use, so the allowance cannot
    # grow by a line nobody measured.
    assert suffixes == set(nsc.ALLOWED_SUFFIXES)
    assert set(nsc.ALLOWED_NAMES) <= names


def test_every_offending_path_is_named_not_only_the_first():
    got = verdict(rec("M", "cogno_praxis/coordinator/prompts/voice.txt"),
                  rec("M", "pyproject.toml"),
                  rec("M", "cogno_praxis/admin/neo.py"),
                  rec("D", "tests/unit/test_coordinator_prompts.py"))
    assert got == [("pyproject.toml", "outside_scope"), ("cogno_praxis/admin/neo.py", "admin"),
                   ("tests/unit/test_coordinator_prompts.py", "outside_scope")]


@pytest.mark.parametrize("status", ["U", "X", "B", "M100", "A1"])
def test_an_unknown_status_is_refused(status):
    assert verdict(f":100644 100644 {SHA} {SHA} {status}\0cogno_praxis/x.py\0") == \
        [("cogno_praxis/x.py", "status")]


# ── the empty diff ──────────────────────────────────────────────────────────────────────
def test_the_empty_diff_is_refused():
    """A NEO pull request that changes nothing has nothing to approve, and "no records" is
    also what a checker that read the wrong range (or nothing) sees. Fail closed."""
    assert verdict() == [("(no records)", "empty_diff")]
    assert nsc.main(["--stdin"], stdin="") == 1


# ── the test allowance (off by default) ─────────────────────────────────────────────────
def test_the_test_allowance_is_off_by_default():
    assert nsc.NEO_MAY_EDIT_TESTS is False
    assert verdict(rec("M", "tests/unit/test_coordinator_prompts.py")) == \
        [("tests/unit/test_coordinator_prompts.py", "outside_scope")]


def test_the_test_allowance_when_on_covers_only_adding_and_editing_unit_tests():
    on = {"allow_tests": True}
    assert verdict(rec("M", "tests/unit/test_coordinator_prompts.py"), **on) == []
    assert verdict(rec("A", "tests/unit/test_new_rule.py"), **on) == []
    refused = [
        rec("D", "tests/unit/test_coordinator_prompts.py"),
        rec("R100", "tests/unit/test_b.py", "tests/unit/test_a.py"),
        rec("M", "tests/unit/test_neo_scope_check.py"),
        rec("M", "tests/unit/test_ci_runs_every_test_file.py"),
        rec("M", "tests/unit/conftest.py"),
        rec("M", "tests/unit/_log_calls.py"),
        rec("M", "tests/unit/sub/test_x.py"),
        rec("M", "tests/integration/test_scheduler_via_mcp.py"),
        rec("M", "tests/conftest.py"),
    ]
    for r in refused:
        got = verdict(r, **on)
        assert got and all(rule in ("test_edit", "outside_scope", "rename_across")
                           for _, rule in got), (r, got)
    head = f":100644 100755 {SHA} {SHA} M\0tests/unit/test_x.py\0"
    assert ("tests/unit/test_x.py", "test_edit") in verdict(head, **on)


# ── the command line ────────────────────────────────────────────────────────────────────
def test_the_exit_codes_and_the_lines(capsys):
    assert nsc.main(["--stdin"], stdin=rec("M", "cogno_praxis/x.py")) == 0
    assert "NEO scope: ok — 1 record(s) read, 0 refusal(s)" in capsys.readouterr().out
    assert nsc.main(["--stdin"], stdin=rec("M", "pyproject.toml")) == 1
    out = capsys.readouterr().out
    assert "REFUSED pyproject.toml: outside_scope" in out
    assert nsc.main(["--stdin"], stdin="garbage") == 2
    assert nsc.main(["--stdin"], stdin=":100644 100644 a a M\0") == 2   # header, no path
    assert nsc.main([]) == 2
    assert nsc.main(["--allow-tests", "x"]) == 2   # there is no flag that opens the tests


# ── real git ────────────────────────────────────────────────────────────────────────────
def _git(cwd: Path, *args: str) -> str:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "Test", "GIT_COMMITTER_NAME":
           "Test", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_EMAIL":
           "t@example.invalid", "LC_ALL": "C"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    for p, text in {"cogno_praxis/scheduler/service.py": "x = 1\n",
                    "cogno_praxis/scheduler/prompts/system.txt": "Be kind.\n",
                    "tests/unit/test_a.py": "def test(): pass\n",
                    "pyproject.toml": "[project]\n"}.items():
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text(text)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "checkout", "-qb", "neo/r1")
    return tmp_path


def _run(repo: Path) -> "tuple[int, str]":
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(repo), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull}
    done = subprocess.run([sys.executable, str(SCRIPT), "main", "neo/r1"], cwd=repo, env=env,
                          capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def test_real_git_a_prompt_edit_passes(repo):
    (repo / "cogno_praxis/scheduler/prompts/system.txt").write_text("Be kind and brief.\n")
    rc, out = _run(repo)
    assert rc == 0, out
    assert "1 record(s) read" in out


def test_real_git_chmod_symlink_and_renames_are_refused(repo):
    (repo / "cogno_praxis/scheduler/service.py").chmod(0o755)
    os.symlink("../../pyproject.toml", repo / "cogno_praxis/scheduler/link.txt")
    _git(repo, "mv", "tests/unit/test_a.py", "cogno_praxis/scheduler/moved.py")
    rc, out = _run(repo)
    assert rc == 1, out
    assert "REFUSED cogno_praxis/scheduler/service.py: mode" in out
    assert "REFUSED cogno_praxis/scheduler/link.txt: mode" in out
    assert "REFUSED tests/unit/test_a.py: outside_scope" in out
    assert "rename_across" in out


def test_real_git_name_status_cannot_see_what_raw_sees(repo):
    """Why the checker reads ``--raw``: the same commit, in ``--name-status``, has no mode."""
    (repo / "cogno_praxis/scheduler/service.py").chmod(0o755)
    os.symlink("system.txt", repo / "cogno_praxis/scheduler/prompts/link.txt")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head")
    name_status = _git(repo, "diff", "--name-status", "main...neo/r1")
    assert name_status.split("\n")[:2] == ["A\tcogno_praxis/scheduler/prompts/link.txt",
                                           "M\tcogno_praxis/scheduler/service.py"]
    raw = _git(repo, "diff", "--raw", "main...neo/r1")
    assert " 120000 " in raw and " 100755 " in raw


def test_real_git_an_empty_range_is_refused(repo):
    rc, out = _run_empty(repo)
    assert rc == 1, out
    assert "empty_diff" in out


def _run_empty(repo: Path) -> "tuple[int, str]":
    done = subprocess.run([sys.executable, str(SCRIPT), "main", "neo/r1"], cwd=repo,
                          capture_output=True, text=True,
                          env={"PATH": os.environ.get("PATH", ""), "HOME": str(repo),
                               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return done.returncode, done.stdout + done.stderr


def test_real_git_an_unknown_ref_is_rc_2_not_ok(repo):
    done = subprocess.run([sys.executable, str(SCRIPT), "main", "neo/nope"], cwd=repo,
                          capture_output=True, text=True,
                          env={"PATH": os.environ.get("PATH", ""), "HOME": str(repo),
                               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    assert done.returncode == 2, done.stdout + done.stderr


# ── the workflow ────────────────────────────────────────────────────────────────────────
def _workflow() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 reads the bare key `on` as the boolean True.
    doc["on"] = doc.pop(True, doc.get("on"))
    return doc


def test_the_job_runs_only_for_the_neo_branch_prefix():
    jobs = _workflow()["jobs"]
    assert list(jobs) == ["scope"]
    assert jobs["scope"]["if"] == "startsWith(github.event.pull_request.head.ref, 'neo/')"


def test_the_workflow_judges_with_the_base_and_never_the_head():
    doc = _workflow()
    assert list(doc["on"]) == ["pull_request_target"], \
        "on `pull_request` the PR's own edited workflow and checker would judge it"
    assert doc["on"]["pull_request_target"]["branches"] == ["main"]
    assert doc["permissions"] == {"contents": "read"}
    assert "pull_request.number" in doc["concurrency"]["group"]
    steps = doc["jobs"]["scope"]["steps"]
    checkout = steps[0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    runs = [s["run"] for s in steps if "run" in s]
    assert runs[-1].strip() == 'python scripts/neo_scope_check.py "$BASE_SHA" "$HEAD_SHA"'
    for text in runs:
        assert "${{" not in text, "an expression interpolated into a run: block"
    # Nothing from the head is installed or executed: no pip, no checkout of the head.
    assert not any("pip" in t for t in runs)
    assert all(s.get("with", {}).get("ref", "").endswith("base.sha }}") for s in steps
               if str(s.get("uses", "")).startswith("actions/checkout@"))


def test_ci_lints_and_typechecks_the_checker():
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    runs = [s.get("run", "") for s in ci["jobs"]["test"]["steps"]]
    assert any(r.strip().startswith("ruff check") and "scripts" in r.split() for r in runs)
    assert any(r.strip().startswith("mypy") and "scripts" in r.split() for r in runs)
