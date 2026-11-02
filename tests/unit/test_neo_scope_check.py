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
* **Who the lock applies to**: the bridge's author (``scripts/neo_bridge_logins``), a ``neo/``
  branch, or a branch imitating it; ``branch_name`` and ``branch_lookalike``; and the control, a
  person's ordinary pull request, which RUNS and exits 0 with "not a NEO pull request".
* **The workflow**: no ``if:`` on the job or on any step (a skipped job reads green to a required
  check), it runs on ``pull_request_target`` (so the BASE's workflow and checker judge the PR,
  never the PR's own edited copy), and no ``${{ }}`` reaches a ``run:`` block. And the workflow
  is SIMULATED: its own ``run:`` blocks, executed over a throwaway origin with a
  ``refs/pull/<n>/head``, for the bridge's and a person's pull requests.

Pure: no network. The git tests run ``git`` in ``tmp_path`` with the user's config cut off.
"""

from __future__ import annotations

import importlib.util
import os
import re
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
    "scripts/neo_scope_check.py", "scripts/neo_bridge_logins", "scripts/other.py",
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


# ── tests: NEO may never edit one, and may create new ones only behind the switch ─────
_TEST_PATHS = [
    rec("A", "tests/unit/test_new_rule.py"),
    rec("M", "tests/unit/test_coordinator_prompts.py"),
    rec("D", "tests/unit/test_coordinator_prompts.py"),
    rec("R100", "tests/unit/test_b.py", "tests/unit/test_a.py"),
    rec("A", "tests/unit/conftest.py"),
    rec("A", "tests/integration/test_new.py"),
]


def test_the_switch_is_named_for_adding_and_is_off_by_default():
    assert nsc.NEO_MAY_ADD_TESTS is False
    assert not hasattr(nsc, "NEO_MAY_EDIT_TESTS")


@pytest.mark.parametrize("record", _TEST_PATHS)
def test_with_the_switch_off_every_test_path_is_refused(record):
    """Through the DEFAULT, not an explicit False: `check()` with no keyword and `main()`, so a
    default flipped to True is seen here and not only by the constant's own assertion."""
    records = nsc.parse_raw_z(record)
    got = nsc.check(records)
    assert got and all(r.rule in ("outside_scope", "rename_across") for r in got), got
    assert nsc.main(["--stdin"], stdin=record) == 1


def test_with_the_switch_on_a_new_unit_test_file_is_allowed():
    assert verdict(rec("A", "tests/unit/test_new_rule.py"), allow_tests=True) == []
    assert verdict(rec("A", "tests/unit/test_x.py"),
                   rec("M", "cogno_praxis/scheduler/prompts/system.txt"), allow_tests=True) == []


@pytest.mark.parametrize("record,path", [
    (rec("M", "tests/unit/test_coordinator_prompts.py"), "tests/unit/test_coordinator_prompts.py"),
    (rec("D", "tests/unit/test_coordinator_prompts.py"), "tests/unit/test_coordinator_prompts.py"),
    (rec("R100", "tests/unit/test_b.py", "tests/unit/test_a.py"), "tests/unit/test_a.py"),
    (rec("R100", "tests/unit/test_b.py", "tests/unit/test_a.py"), "tests/unit/test_b.py"),
    (rec("C100", "tests/unit/test_b.py", "tests/unit/test_a.py"), "tests/unit/test_b.py"),
    (rec("R100", "tests/unit/test_moved.py", "cogno_praxis/scheduler/x.py"),
     "tests/unit/test_moved.py"),
    (rec("A", "tests/unit/conftest.py"), "tests/unit/conftest.py"),
    (rec("A", "tests/unit/_helpers.py"), "tests/unit/_helpers.py"),
    (rec("A", "tests/unit/sub/test_x.py"), "tests/unit/sub/test_x.py"),
    (rec("A", "tests/unit/test_Neo_Scope_Check.py"), "tests/unit/test_Neo_Scope_Check.py"),
    (rec("A", "tests/unit/test_neo_scope_check.py"), "tests/unit/test_neo_scope_check.py"),
    (rec("A", "tests/unit/test_ci_runs_every_test_file.py"),
     "tests/unit/test_ci_runs_every_test_file.py"),
    (rec("A", "tests/unit/test_x.txt"), "tests/unit/test_x.txt"),
    (rec("A", "tests/integration/test_new.py"), "tests/integration/test_new.py"),
    (rec("A", "tests/conftest.py"), "tests/conftest.py"),
    (rec("A", "tests/unit/test_x.py", new_mode="100755"), "tests/unit/test_x.py"),
    (rec("A", "tests/unit/test_x.py", new_mode="120000"), "tests/unit/test_x.py"),
    (f":100644 100755 {SHA} {SHA} M\0tests/unit/test_x.py\0", "tests/unit/test_x.py"),
    (f":100644 120000 {SHA} {SHA} T\0tests/unit/test_x.py\0", "tests/unit/test_x.py"),
])
def test_with_the_switch_on_anything_but_a_new_file_is_refused(record, path):
    got = verdict(record, allow_tests=True)
    assert got, "refused nothing"
    assert any(p == path and rule in ("test_add", "outside_scope", "mode") for p, rule in got), got


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
def _git(cwd: Path, *args: str, date: "str | None" = None) -> str:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "Test", "GIT_COMMITTER_NAME":
           "Test", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_EMAIL":
           "t@example.invalid", "LC_ALL": "C"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
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


# ── history: a NEO head is linear on one merge base ─────────────────────────────────────
def _check(repo: Path) -> "tuple[int, str]":
    return _run_empty(repo)


def _commit(repo: Path, msg: str, date: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg, date=date)


def test_real_git_a_criss_cross_head_is_refused_though_its_diff_looks_in_scope(repo):
    """The measured bypass. Main merged A (a hardening of pyproject.toml) and B (an unrelated
    in-scope file). The head is ``B + merge -s ours A + a prompt edit``: it has TWO merge bases
    with main, the three-dot diff is taken from B and shows the prompt edit only, and landing it
    (git's merge over a virtual base, as GitHub's) puts the OLD pyproject.toml back."""
    _git(repo, "branch", "A")
    _git(repo, "branch", "B")
    _git(repo, "checkout", "-q", "A")
    (repo / "pyproject.toml").write_text("[project]\nhardened = true\n")
    _commit(repo, "A", "2026-01-01T00:00:01")
    _git(repo, "checkout", "-q", "B")
    (repo / "cogno_praxis/scheduler/extra.txt").write_text("b\n")
    _commit(repo, "B", "2026-01-01T00:00:02")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-edit", "A", date="2026-01-01T00:00:03")
    _git(repo, "merge", "-q", "--no-edit", "B", date="2026-01-01T00:00:04")
    _git(repo, "checkout", "-q", "-B", "neo/r1", "B")
    _git(repo, "merge", "-q", "-s", "ours", "--no-edit", "A", date="2026-01-01T00:00:05")
    (repo / "cogno_praxis/scheduler/prompts/system.txt").write_text("Be kind and brief.\n")
    _commit(repo, "prompt", "2026-01-01T00:00:06")
    # The broken world, proved before the verdict is read: the diff the paths are judged on
    # holds only the in-scope prompt edit, and a real merge reverts the hardening.
    assert len(_git(repo, "merge-base", "--all", "main", "neo/r1").split()) == 2
    seen = nsc.check(nsc.parse_raw_z(_git(repo, "diff", "--raw", "-z", "-M", "main...neo/r1")))
    assert seen == [], "precondition: the three-dot diff must look in scope"
    _git(repo, "checkout", "-q", "-b", "landed", "main")
    _git(repo, "merge", "-q", "--no-edit", "neo/r1", date="2026-01-01T00:00:07")
    assert "hardened" not in (repo / "pyproject.toml").read_text(), "precondition: landing reverts"
    _git(repo, "checkout", "-q", "neo/r1")
    rc, out = _check(repo)
    assert rc == 1, out
    assert "REFUSED (merge bases: 2): merge_bases" in out


def test_real_git_a_merge_commit_on_one_base_is_refused(repo):
    """One merge base, every path in scope, and a merge commit in the head: refused on the
    merge alone. A NEO head is linear."""
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "cogno_praxis/scheduler/prompts/system.txt").write_text("Be kind and brief.\n")
    _commit(repo, "side", "2026-01-01T00:00:01")
    _git(repo, "checkout", "-q", "neo/r1")
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", "side", date="2026-01-01T00:00:02")
    assert len(_git(repo, "merge-base", "--all", "main", "neo/r1").split()) == 1
    assert nsc.check(nsc.parse_raw_z(_git(repo, "diff", "--raw", "-z", "-M",
                                           "main...neo/r1"))) == []
    rc, out = _check(repo)
    assert rc == 1, out
    assert out.count(": merge_commit") == 1
    assert "1 record(s) read" in out


def test_real_git_an_unrelated_history_is_refused_with_its_rule_not_a_git_error(repo):
    _git(repo, "checkout", "-q", "--orphan", "neo/r2")
    (repo / "cogno_praxis/scheduler/prompts/system.txt").write_text("Be kind and brief.\n")
    _commit(repo, "orphan", "2026-01-01T00:00:01")
    done = subprocess.run([sys.executable, str(SCRIPT), "main", "neo/r2"], cwd=repo,
                          capture_output=True, text=True,
                          env={"PATH": os.environ.get("PATH", ""), "HOME": str(repo),
                               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    assert done.returncode == 1, done.stdout + done.stderr
    assert "REFUSED (merge bases: 0): merge_bases" in done.stdout


def test_real_git_a_linear_head_has_no_history_refusal(repo):
    """The control: two plain commits on one base are judged on their paths alone."""
    (repo / "cogno_praxis/scheduler/prompts/system.txt").write_text("Be kind and brief.\n")
    _commit(repo, "one", "2026-01-01T00:00:01")
    (repo / "cogno_praxis/scheduler/service.py").write_text("x = 2\n")
    _commit(repo, "two", "2026-01-01T00:00:02")
    rc, out = _check(repo)
    assert rc == 0, out
    assert "merge_" not in out and "2 record(s) read" in out


# ── who the lock applies to: the author, the branch, the lookalike ─────────────────────
# Invented accounts. The bridge's is listed in a fixture file, never in the real one.
BRIDGE = "bridge-bot-example"
HUMAN = "octo-human-example"


@pytest.fixture
def logins(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("logins") / "neo_bridge_logins"
    path.write_text(f"# the bridge\n\n  {BRIDGE.upper()}  \n")
    return path


@pytest.mark.parametrize("author,branch,why", [
    (BRIDGE, "neo/abc", "author"),
    (BRIDGE, "feature-x", "author"),           # the author is asked first, whatever the branch
    (BRIDGE.upper(), "feature-x", "author"),   # a login is case-insensitive
    (HUMAN, "neo/abc", "branch"),
    (HUMAN, "NEO/abc", "branch"),              # GitHub's startsWith ignored case; so does this
    (HUMAN, "neo-abc", "lookalike"),
    (HUMAN, "NEO_abc", "lookalike"),
    (HUMAN, "neo.abc", "lookalike"),
    (HUMAN, "neo", "lookalike"),
    (HUMAN, "fix-y", None),
])
def test_who_the_lock_applies_to(logins, author, branch, why):
    assert nsc.applies(author, branch, nsc.read_logins(logins)) == why


@pytest.mark.parametrize("branch", [
    "neon-lights", "neo2", "neo4j-upgrade", "neophyte", "fix/neo-x", "feature-neo", "geo-x",
    "r-neo-x", "main",
])
def test_adverse_branches_that_merely_contain_neo_are_not_lookalikes(logins, branch):
    """The negative probe: the lookalike rule must not catch a person's branch that only has
    ``neo`` somewhere in it."""
    assert not nsc.is_lookalike(branch)
    assert nsc.applies(HUMAN, branch, nsc.read_logins(logins)) is None


# Each form that escaped a lookalike check written on the literal prefix, one twin per form.
# The ids are plain ASCII names: the branch itself may not be.
_EVASIONS = [
    ("refs/heads/neo/x", "ref-prefix-full"),
    ("heads/neo/x", "ref-prefix-short"),
    ("refs/heads/neo-x", "ref-prefix-dash"),
    ("Refs/Heads/neo/x", "ref-prefix-case"),
    ("refs/heads/heads/neo/x", "ref-prefix-twice"),
    ("ne0/x", "zero-for-o-slash"),
    ("ne0-x", "zero-for-o-dash"),
    ("NE0/x", "zero-for-o-upper"),
    ("ne0", "zero-for-o-bare"),
    ("n\u0435o/x", "cyrillic-ie"),
    ("\uff4e\uff45\uff4f/x", "fullwidth"),
    ("\u039deo/x", "greek-capital-nu"),
    ("ne\u200do/x", "zero-width-joiner"),
    ("neo\u200d/x", "zwj-before-slash"),
    ("fix-\u00e9", "any-non-ascii"),
]


@pytest.mark.parametrize("branch", [b for b, _ in _EVASIONS], ids=[i for _, i in _EVASIONS])
def test_every_evasive_spelling_of_the_prefix_applies_and_is_refused(logins, branch):
    """A person's branch spelled to look like NEO's, or to slip past a literal prefix: the lock
    applies (fails CLOSED), and the branch is refused as a lookalike and not the bridge's."""
    assert nsc.is_lookalike(branch)
    assert nsc.applies(HUMAN, branch, nsc.read_logins(logins)) == "lookalike"
    assert [r.rule for r in nsc.branch_refusals(branch)] == ["branch_name", "branch_lookalike"]


# A REMOTE prefix in front of neo/: a component that is not the last, read with 0 as o, is
# exactly "neo". One twin per form.
_REMOTE_FORMS = [
    ("origin/neo/x", "origin"),
    ("remotes/origin/neo/x", "remotes-origin"),
    ("refs/remotes/origin/neo/x", "refs-remotes-origin"),
    ("upstream/neo/x", "upstream"),
    ("origin/ne0/x", "origin-zero-for-o"),
]


@pytest.mark.parametrize("branch", [b for b, _ in _REMOTE_FORMS], ids=[i for _, i in _REMOTE_FORMS])
def test_a_remote_prefix_in_front_of_the_prefix_applies_and_is_refused(logins, branch):
    assert nsc.is_lookalike(branch)
    assert nsc.applies(HUMAN, branch, nsc.read_logins(logins)) == "lookalike"
    assert [r.rule for r in nsc.branch_refusals(branch)] == ["branch_name", "branch_lookalike"]


@pytest.mark.parametrize("branch,lookalike", [
    ("fix/neo-x", False),            # "neo-x" is the LAST component, and not exactly "neo"
    ("feature/neo-thing/z", False),  # a middle component that only starts with "neo"
    ("fix/neon/x", False),
    ("origin/fix-y", False),         # a remote prefix in front of an ordinary name
    ("neo-n1-admin-x", True),        # a person's neo-… branch: a lookalike by the dash, as before
    ("neo/x", False),                # the plain prefix stays branch_name's, not a lookalike
])
def test_control_the_component_rule_reads_only_a_middle_component_that_is_neo(branch, lookalike):
    assert nsc.is_lookalike(branch) is lookalike


def test_the_component_rule_has_no_hit_on_real_shapes():
    """The shapes of the last 130 branch names of this repository (2026-11-02), invented: a
    prefix, slashes, and two people's neo-… branches. Only the neo-… ones are lookalikes."""
    shapes = ["fix/calendar-recipient-one-address", "docs-testing-standard", "fix-negation-x",
              "neo-n4a-x", "neo-n1-x", "review/contrast-x", "pf56-p5-x", "feat/restart-x"]
    assert [b for b in shapes if nsc.is_lookalike(b)] == ["neo-n4a-x", "neo-n1-x"]


@pytest.mark.parametrize("branch", ["refs/heads/fix-y", "heads/fix-y", "ne0n-lights",
                                    "fix/ne0-x", "heads-up", "headsup/neo-x", "refsheads/neo"])
def test_adverse_the_evasion_folds_do_not_catch_ordinary_branches(logins, branch):
    """The negative probe for the folds: a ref prefix before an ordinary name, a zero that is
    not in the prefix, and words that merely start with 'heads'."""
    assert not nsc.is_lookalike(branch)
    assert nsc.applies(HUMAN, branch, nsc.read_logins(logins)) is None


def test_the_bridges_own_branch_is_not_a_lookalike_whatever_its_id_holds():
    """A zero in the REQUEST ID is not a zero in the prefix."""
    for branch in ("neo/chg-0001", "neo/0", "neo/00-x0"):
        assert not nsc.is_lookalike(branch)
        assert nsc.branch_refusals(branch) == []


@pytest.mark.parametrize("branch,rules", [
    ("neo/abc", []),
    ("neo/chg-0001_b", []),
    ("feature-x", ["branch_name"]),
    ("neo-abc", ["branch_name", "branch_lookalike"]),
    ("NEO/abc", ["branch_name"]),        # applies by the prefix, and is not the bridge's branch
    ("neo/a/b", ["branch_name"]),        # one request id, no deeper path
    ("neo/", ["branch_name"]),
    ("neo/-x", ["branch_name"]),         # the host's REQUEST_ID_RE starts with a letter or digit
    ("neo/" + "a" * 65, ["branch_name"]),
])
def test_the_branch_rules(branch, rules):
    assert [r.rule for r in nsc.branch_refusals(branch)] == rules


def test_the_logins_file_reads_comments_blanks_case_and_bots(tmp_path):
    path = tmp_path / "logins"
    path.write_text("# c\n\nOne-Account\nan-app[bot]\n")
    assert nsc.read_logins(path) == {"one-account", "an-app[bot]"}


@pytest.mark.parametrize("text", ["two words\n", "-leading\n", "a,b\n", "x" * 40 + "\n",
                                  "name@example.invalid\n"],
                         ids=["two-words", "leading-dash", "comma", "forty-chars", "an-email"])
def test_a_logins_file_with_a_line_that_is_not_a_login_is_refused(tmp_path, text):
    path = tmp_path / "logins"
    path.write_text(f"{BRIDGE}\n{text}")
    with pytest.raises(nsc.BadLogins):
        nsc.read_logins(path)


def test_the_real_logins_file_is_read_from_next_to_the_checker_and_parses():
    assert nsc.BRIDGE_LOGINS_FILE == SCRIPT.parent / "neo_bridge_logins"
    assert isinstance(nsc.read_logins(), frozenset)


def _pr(repo: Path, logins: Path, capsys, monkeypatch, *, author: str, branch: str,
        files: "dict[str, str]") -> "tuple[int, str]":
    """A pull request from ``branch`` by ``author``, judged in-process in ``--author`` mode."""
    _git(repo, "checkout", "-q", "-b", "pr-head", "main")
    for p, text in files.items():
        (repo / p).parent.mkdir(parents=True, exist_ok=True)
        (repo / p).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    capsys.readouterr()
    rc = nsc.main(["--author", author, "--branch", branch, "main", "pr-head"],
                  logins_file=logins)
    cap = capsys.readouterr()
    return rc, cap.out + cap.err


IN_SCOPE = {"cogno_praxis/scheduler/prompts/system.txt": "Be kind and brief.\n"}
OUT_OF_SCOPE = {"cogno_praxis/scheduler/prompts/system.txt": "Be kind and brief.\n",
                "pyproject.toml": "[project]\nname = 'x'\n"}


def test_bridge_on_its_branch_in_scope_passes(repo, logins, capsys, monkeypatch):
    rc, out = _pr(repo, logins, capsys, monkeypatch, author=BRIDGE, branch="neo/abc",
                  files=IN_SCOPE)
    assert rc == 0, out
    assert "the lock applies by author" in out and "NEO scope: ok" in out


def test_bridge_on_another_branch_is_judged_and_refused(repo, logins, capsys, monkeypatch):
    """The red of before: with the job's ``if:`` this pull request was SKIPPED, and green."""
    rc, out = _pr(repo, logins, capsys, monkeypatch, author=BRIDGE, branch="feature-x",
                  files=IN_SCOPE)
    assert rc == 1, out
    assert "REFUSED (branch feature-x): branch_name" in out
    assert "branch_lookalike" not in out


def test_bridge_on_a_dash_branch_is_refused_and_its_paths_judged(repo, logins, capsys,
                                                                 monkeypatch):
    """The bridge's own ``neo-<id>`` of before: the lock applies, and the path outside the
    scope is refused alongside the two branch rules."""
    rc, out = _pr(repo, logins, capsys, monkeypatch, author=BRIDGE, branch="neo-x",
                  files=OUT_OF_SCOPE)
    assert rc == 1, out
    assert "REFUSED (branch neo-x): branch_name" in out
    assert "REFUSED (branch neo-x): branch_lookalike" in out
    assert "REFUSED pyproject.toml: outside_scope" in out


def test_a_person_on_a_neo_branch_is_judged_by_the_branch(repo, logins, capsys, monkeypatch):
    rc, out = _pr(repo, logins, capsys, monkeypatch, author=HUMAN, branch="neo/abc",
                  files=OUT_OF_SCOPE)
    assert rc == 1, out
    assert "the lock applies by branch" in out
    assert "REFUSED pyproject.toml: outside_scope" in out
    assert "branch_" not in out


def test_a_person_on_a_lookalike_branch_is_refused(repo, logins, capsys, monkeypatch):
    rc, out = _pr(repo, logins, capsys, monkeypatch, author=HUMAN, branch="neo-abc",
                  files=IN_SCOPE)
    assert rc == 1, out
    assert "REFUSED (branch neo-abc): branch_lookalike" in out


def test_control_a_persons_ordinary_pull_request_runs_and_passes(repo, logins, capsys,
                                                                 monkeypatch):
    """The control: the job RUNS for a person's pull request, decides, and exits 0 without
    judging a path, so an out-of-scope change is not refused."""
    rc, out = _pr(repo, logins, capsys, monkeypatch, author=HUMAN, branch="fix-y",
                  files=OUT_OF_SCOPE)
    assert rc == 0, out
    assert out.strip() == (f"NEO scope: not a NEO pull request (author={HUMAN}, branch=fix-y)")


def test_an_unreadable_logins_file_refuses_every_pull_request(repo, tmp_path_factory, capsys,
                                                             monkeypatch):
    """Fail closed: not knowing who the bridge is must not read as "not a NEO pull request"."""
    missing = tmp_path_factory.mktemp("none") / "neo_bridge_logins"
    rc, out = _pr(repo, missing, capsys, monkeypatch, author=HUMAN, branch="fix-y",
                  files=IN_SCOPE)
    assert rc == 2, out
    assert "cannot read who the bridge is" in out


def test_the_decision_line_never_prints_a_character_outside_the_safe_set(capsys, logins):
    assert nsc.main(["--author", HUMAN, "--branch", "fix$y;x", "a", "b"],
                    logins_file=logins) == 0
    assert capsys.readouterr().out.strip().endswith("branch=fix?y?x)")
    # A non-ASCII branch applies (a lookalike); its line prints '?', never the letter.
    rc = nsc.main(["--author", HUMAN, "--branch", "fix\u0131y", "a", "b"], logins_file=logins)
    out = capsys.readouterr()
    assert rc != 0
    assert "the lock applies by lookalike (author=" in out.out
    assert "branch=fix?y)" in out.out and "\u0131" not in out.out + out.err


@pytest.mark.parametrize("argv", [
    ["--author", HUMAN, "--branch", "fix-y", "-x", "b"],
    ["--branch", "fix-y", "--author", HUMAN, "a", "b"],
    ["--author", HUMAN, "--branch", "fix-y", "a"],
    ["--author", HUMAN, "a", "b"],
])
def test_the_decision_mode_takes_exactly_one_shape(argv, logins):
    assert nsc.main(argv, logins_file=logins) == 2


# ── the workflow ────────────────────────────────────────────────────────────────────────
def _workflow() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 reads the bare key `on` as the boolean True.
    doc["on"] = doc.pop(True, doc.get("on"))
    return doc


def test_the_job_runs_on_every_pull_request_with_no_if_anywhere():
    """A skipped job reports success to a required check. The job used to carry
    ``if: startsWith(head.ref, 'neo/')``, and the host's bridge pushed ``neo-<id>``: every bridge
    pull request would have been skipped and read green. No ``if:`` on the job, and none on a
    step either: a step skipped over an output string is the same skip one level down."""
    jobs = _workflow()["jobs"]
    assert list(jobs) == ["scope"]
    assert "if" not in jobs["scope"], jobs["scope"].get("if")
    for step in jobs["scope"]["steps"]:
        assert "if" not in step, step


def test_the_check_step_decides_with_the_author_and_the_branch_through_env():
    step = _workflow()["jobs"]["scope"]["steps"][-1]
    assert step["env"] == {
        "PR_AUTHOR": "${{ github.event.pull_request.user.login }}",
        "HEAD_REF": "${{ github.event.pull_request.head.ref }}",
        "BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
    }
    assert step["run"].strip() == ('python scripts/neo_scope_check.py --author "$PR_AUTHOR" '
                                   '--branch "$HEAD_REF" "$BASE_SHA" "$HEAD_SHA"')


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
    assert runs[-1].strip().startswith("python scripts/neo_scope_check.py --author ")
    for text in runs:
        assert "${{" not in text, "an expression interpolated into a run: block"
    # Nothing from the head is installed or executed: no pip, no checkout of the head.
    assert not any("pip" in t for t in runs)
    assert all(s.get("with", {}).get("ref", "").endswith("base.sha }}") for s in steps
               if str(s.get("uses", "")).startswith("actions/checkout@"))


def test_the_trigger_is_every_pull_request_to_main_with_no_filter():
    """No ``paths:``/``paths-ignore:``/``branches-ignore:`` filter and no ``if:``: a filtered-out
    run is a check that never reports, and an ``if:`` is a skip that reads green."""
    doc = _workflow()
    assert doc["on"] == {"pull_request_target": {
        "branches": ["main"], "types": ["opened", "synchronize", "reopened", "edited"]}}
    assert "if" not in doc and all("if" not in job for job in doc["jobs"].values())
    text = WORKFLOW.read_text(encoding="utf-8")
    for key in ("paths:", "paths-ignore:", "branches-ignore:"):
        assert key not in text, key


def test_every_action_of_the_lock_is_pinned_by_commit_sha():
    steps = _workflow()["jobs"]["scope"]["steps"]
    uses = [s["uses"] for s in steps if "uses" in s]
    assert len(uses) == 2
    for ref in uses:
        name, _, sha = ref.partition("@")
        assert name in ("actions/checkout", "actions/setup-python")
        assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha), ref


def test_ci_lints_and_typechecks_the_checker():
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    runs = [s.get("run", "") for s in ci["jobs"]["test"]["steps"]]
    assert any(r.strip().startswith("ruff check") and "scripts" in r.split() for r in runs)
    assert any(r.strip().startswith("mypy") and "scripts" in r.split() for r in runs)


# ── the workflow, SIMULATED: its own run: blocks over a throwaway origin ────────────────
_EXPR = re.compile(r"\$\{\{\s*([^}]*?)\s*\}\}")
_JOB_IF = re.compile(r"startsWith\(github\.event\.pull_request\.head\.ref, '([^']*)'\)")


def _event_value(expr: str, event: dict) -> str:
    assert expr.startswith("github.event."), expr
    cur = event
    for key in expr[len("github.event."):].split("."):
        cur = cur[key]
    return str(cur)


def _simulate(checkout: Path, event: dict, shim: Path) -> "tuple[str, str]":
    """Run the scope job as GitHub would, for ``event``: ``skipped``, ``success`` or
    ``failure``. The two ``uses:`` steps are the fixture (a clone at the base SHA, this
    Python); every ``run:`` step runs in bash -eo pipefail, its env expressions read from the
    event. A job ``if:`` of the old shape is evaluated; any other ``if:`` fails the test."""
    job = _workflow()["jobs"]["scope"]
    if "if" in job:
        m = _JOB_IF.fullmatch(job["if"])
        assert m, f"an if: the simulator cannot read: {job['if']!r}"
        if not event["pull_request"]["head"]["ref"].lower().startswith(m.group(1).lower()):
            return "skipped", ""
    out = ""
    for step in job["steps"]:
        assert "if" not in step, step
        if "uses" in step:
            continue
        env = {"PATH": f"{shim}{os.pathsep}{os.environ.get('PATH', '')}", "HOME": str(checkout),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "LC_ALL": "C"}
        for key, value in step.get("env", {}).items():
            env[key] = _EXPR.sub(lambda mm: _event_value(mm.group(1), event), str(value))
        assert "${{" not in step["run"]
        done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
                               step["run"]], cwd=checkout, env=env, capture_output=True,
                              text=True)
        out += done.stdout + done.stderr
        if done.returncode != 0:
            return "failure", out
    return "success", out


@pytest.fixture
def origin(tmp_path: Path):
    """A base commit holding the REAL checker and an invented bridge login, pushed to a bare
    origin; ``open_pr`` pushes a head to ``refs/pull/7/head`` and returns the base checkout."""
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    files = {"scripts/neo_scope_check.py": SCRIPT.read_text(encoding="utf-8"),
             "scripts/neo_bridge_logins": f"# invented\n{BRIDGE}\n",
             "cogno_praxis/scheduler/prompts/system.txt": "Be kind.\n",
             "pyproject.toml": "[project]\n"}
    for p, text in files.items():
        (work / p).parent.mkdir(parents=True, exist_ok=True)
        (work / p).write_text(text)
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base")
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    _git(work, "push", "-q", str(bare), "main")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python").symlink_to(sys.executable)

    def open_pr(author: str, branch: str, changes: "dict[str, str]") -> "tuple[str, str]":
        _git(work, "checkout", "-q", "-B", "head", "main")
        for p, text in changes.items():
            (work / p).write_text(text)
        _git(work, "add", "-A")
        _git(work, "commit", "-qm", "head")
        _git(work, "push", "-q", "-f", str(bare), "head:refs/pull/7/head")
        base_sha = _git(work, "rev-parse", "main").strip()
        head_sha = _git(work, "rev-parse", "head").strip()
        checkout = tmp_path / f"checkout-{len(list(tmp_path.glob('checkout-*')))}"
        _git(tmp_path, "clone", "-q", str(bare), str(checkout))
        _git(checkout, "checkout", "-q", "--detach", base_sha)
        event = {"pull_request": {"number": 7, "user": {"login": author},
                                  "head": {"ref": branch, "sha": head_sha},
                                  "base": {"sha": base_sha}}}
        return _simulate(checkout, event, shim)

    return open_pr


def test_workflow_a_bridge_pull_request_on_a_dash_branch_is_judged_and_refused(origin):
    status, out = origin(BRIDGE, "neo-x", {"pyproject.toml": "[project]\nname = 'x'\n"})
    assert status == "failure", out
    assert "REFUSED pyproject.toml: outside_scope" in out
    assert "branch_lookalike" in out and "branch_name" in out


def test_workflow_a_bridge_pull_request_on_any_branch_is_judged(origin):
    """The mutation target: put the old job ``if:`` back and this one reads ``skipped``."""
    status, out = origin(BRIDGE, "feature-x",
                         {"cogno_praxis/scheduler/prompts/system.txt": "Be brief.\n"})
    assert status == "failure", out
    assert "REFUSED (branch feature-x): branch_name" in out


def test_workflow_a_lookalike_branch_is_refused(origin):
    status, out = origin(HUMAN, "neo-abc",
                         {"cogno_praxis/scheduler/prompts/system.txt": "Be brief.\n"})
    assert status == "failure", out
    assert "branch_lookalike" in out


def test_workflow_the_bridge_on_its_own_branch_passes(origin):
    status, out = origin(BRIDGE, "neo/abc",
                         {"cogno_praxis/scheduler/prompts/system.txt": "Be brief.\n"})
    assert status == "success", out
    assert "NEO scope: ok — 1 record(s) read, 0 refusal(s)" in out


def test_workflow_control_a_persons_pull_request_runs_and_succeeds_without_applying(origin):
    """Not skipped: the job ran, decided, and said so."""
    status, out = origin(HUMAN, "fix-y", {"pyproject.toml": "[project]\nname = 'x'\n"})
    assert status == "success", out
    assert f"NEO scope: not a NEO pull request (author={HUMAN}, branch=fix-y)" in out


def test_workflow_the_head_cannot_remove_the_bridge_from_the_logins(origin):
    """The bridge's head EMPTIES ``scripts/neo_bridge_logins``. The base's copy decides, so
    the lock still applies by author and refuses the branch and the path. A checker that read
    the head's copy would answer "not a NEO pull request" here."""
    status, out = origin(BRIDGE, "feature-x", {"scripts/neo_bridge_logins": "# nobody\n"})
    assert status == "failure", out
    assert "the lock applies by author" in out
    assert "REFUSED (branch feature-x): branch_name" in out
    assert "REFUSED scripts/neo_bridge_logins: outside_scope" in out


def test_the_logins_are_read_from_the_checkers_directory_never_from_git(repo, logins, capsys,
                                                                        monkeypatch):
    """In-process twin of the one above: the head rewrites the file in the tree's own
    ``scripts/``; the checker reads the file it was GIVEN (the base's, next to it)."""
    rc, out = _pr(repo, logins, capsys, monkeypatch, author=BRIDGE, branch="feature-x",
                  files={"scripts/neo_bridge_logins": "# nobody\n"})
    assert rc == 1, out
    assert "the lock applies by author" in out
    assert "REFUSED scripts/neo_bridge_logins: outside_scope" in out
