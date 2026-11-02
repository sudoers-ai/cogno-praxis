#!/usr/bin/env python3
"""The scope lock for the pull requests the NEO bridge opens.

NEO is an admin persona. When the owner approves a change to a vertical's skills, a headless code
agent edits a worktree of this repo and opens a pull request from a branch named
``neo/<request_id>``. The owner's rule is that NEO only improves the verticals' skills: it never
changes the system, and it never changes itself. This script is that rule as code. CI runs it on
EVERY pull request to ``main`` (``.github/workflows/neo-scope.yml``), and the first thing it does
is decide whether the lock APPLIES (see *Who the lock applies to*).

**Allowed:** a path under ``cogno_praxis/`` that is not the admin package (``cogno_praxis/admin``,
in any case, as a directory or a module). **Everything else is refused**, the build configuration,
the workflows, this script, the docs and the tests included.

Usage::

    # what the workflow runs: decide first, then judge the head when the lock applies
    python scripts/neo_scope_check.py --author <login> --branch <ref> <base> <head>
    python scripts/neo_scope_check.py <base> <head>   # the lock applies; runs git itself
    git diff --raw -z -M <base>...<head> | python scripts/neo_scope_check.py --stdin

Exit codes: 0 = every changed path is in scope, or the lock does not apply to this pull request;
1 = refused, one line per offence naming the rule it broke; 2 = the input could not be read
(usage, git failure, malformed input, an unreadable bridge-logins file). Every exit but 0 is a
refusal: a checker that cannot read its input must not pass it.

**Who the lock applies to** (``--author``/``--branch`` mode). The job used to carry an ``if:`` on
the branch prefix, and a SKIPPED job reports success to a required check: a pull request from the
bridge on any other branch (the host's bridge named its branch ``neo-<id>`` until it was fixed)
was never judged and read green. So the workflow has no ``if:`` at all, and this script decides:

* the AUTHOR (``github.event.pull_request.user.login``) is one of the bridge's accounts, read from
  ``scripts/neo_bridge_logins`` in the BASE's checkout, next to this file; or
* the BRANCH starts with ``neo/`` (in any case, as GitHub's ``startsWith`` did); or
* the BRANCH imitates the prefix (``neo-x``, ``NEO_x``, ``neo.x``, ``neo``, ``ne0/x``,
  ``refs/heads/neo/x``), or holds any non-ASCII character (a homoglyph, a zero-width joiner).

When none holds the script prints ``NEO scope: not a NEO pull request (…)`` and exits 0: the job
RAN and decided, it was not skipped. When one holds, two more rules join the path rules:
``branch_name`` (the branch is not exactly ``neo/<request_id>``) and ``branch_lookalike``.

**A NEO head is LINEAR on ONE merge base**, and in ``<base> <head>`` mode the checker refuses
anything else before it reads a path (``history``). The three-dot diff is taken from ONE merge
base, while GitHub's merge (``ort``/``recursive``) builds a VIRTUAL base from ALL of them. So on a
criss-cross history the diff can show an in-scope prompt edit while landing the pull request
REVERTS a file the diff never showed. Measured on a throwaway repository: a head of
``B + merge -s ours A + a prompt edit`` against a main that merged ``A`` (hardening a workflow)
and ``B`` read "ok, 1 record", and merging it put the old workflow back. Two conditions, either
one refuses:

* ``git merge-base --all <base> <head>`` must print EXACTLY one commit. Zero bases (unrelated
  histories) is refused too, with a rule, rather than reaching ``git diff`` and failing there.
* ``git rev-list --merges <base>..<head>`` must be empty: no merge commit in the head's own
  history. With two or more bases this one always fires as well, because whatever joins the
  bases is a merge that the base cannot reach. The base-count check is the second wall, and on its
  own it is the one that names unrelated histories.

``--stdin`` reads a diff and knows no history: it is for tests and ad-hoc use, and the workflow
never calls it.

Why ``--raw`` and not ``--name-status``: ``--name-status`` prints a ``chmod +x`` as ``M`` and a new
symlink as ``A``, so neither can be seen there. ``--raw`` carries the old and new MODE of every
record. ``-z`` keeps a path byte for byte (no C-quoting) and lets nothing in a name split a record.

Pure: no network, no import from the package it guards, standard library only.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

# The one directory NEO may change, and the one subtree of it NEO may never change: its own code.
ALLOWED_ROOT = "cogno_praxis"
ADMIN_NAME = "admin"

# What a skill is made of today, measured over `git ls-files cogno_praxis` on 232e72d: 51 `.py`,
# 21 `.txt` (the prompts) and `py.typed`. Nothing else. A narrower set than "any file" because a
# file's TYPE can change the system from inside the allowed directory: an extension module
# (`server.cpython-312-x86_64-linux-gnu.so`) is loaded BEFORE the `.py` of the same name
# (importlib tries ExtensionFileLoader first), and a `.gitattributes` with `-diff` would show the
# owner "Binary files differ" instead of the change he is approving. A new type is a decision.
ALLOWED_SUFFIXES = frozenset({".py", ".txt"})
ALLOWED_NAMES = frozenset({"py.typed"})

# A regular, non-executable file. The only mode the package holds today (73 of 73 files).
REGULAR_FILE = "100644"
ABSENT = "000000"

# Every path in this repo today matches this (0 of the tracked files do not). Spaces, control
# characters, backslashes and non-ASCII letters are refused rather than normalised: a homoglyph
# or a case fold is how `cogno_praxis/admın/` or `Cogno_Praxis/` would pass for something else.
_PATH_CHARS = re.compile(r"[A-Za-z0-9._/-]+")

# The owner's rule on tests: NEO may never EDIT a test, but may CREATE new ones. This constant is
# the switch for the second half, and it is OFF (strict) by default: with False every test path
# is refused. With True the ONLY test change allowed is ADDING A NEW FILE: status `A` (the path
# did not exist at the merge base), a regular non-executable file, directly in `tests/unit/`,
# named `test_<lowercase>.py`. Never a modification, a deletion, a rename or copy, a mode change,
# a conftest, a helper, an integration test, or one of PROTECTED_TESTS. The lowercase name is
# what keeps an "added" `test_Neo_Scope_Check.py` from being, on a case-insensitive filesystem,
# an edit of an existing file. There is no command-line flag: the switch lives in the BASE's copy
# of this file, which a NEO pull request cannot change.
#
# Why it matters: measured on 232e72d, one neutral sentence appended to the 21 prompt files fails
# 95 unit tests, so a prompt improvement often needs a pinned test updated, and that edit is
# always a person's. A new test cannot weaken an old one by path, but it runs in the same pytest
# process, so module-level code in it could still patch what other tests read: the switch keeps
# a reviewer reading every new test.
NEO_MAY_ADD_TESTS = False
_NEW_TEST_NAME = re.compile(r"test_[a-z0-9_]+\.py")
TESTS_ROOT = "tests/unit"
PROTECTED_TESTS = frozenset({
    "tests/unit/test_neo_scope_check.py",        # the tests of this lock
    "tests/unit/test_ci_runs_every_test_file.py",  # the guard that every test file runs in CI
})

# The rules, by name. The name is what a refusal prints; the sentence is the reason.
RULES = {
    "empty_diff": "the diff has no records; nothing to approve, and a checker that read nothing "
                  "must not pass it",
    "malformed": "the record could not be parsed",
    "status": "an unknown or unmerged diff status",
    "absolute": "an absolute path",
    "traversal": "a '.' or '..' component, or an empty one",
    "path_chars": "a character outside [A-Za-z0-9._/-]",
    "hidden": "a component starting with '.' (a dotfile changes how git or a tool reads the tree)",
    "outside_scope": "outside cogno_praxis/ (NEO changes the verticals' skills, never the system)",
    "admin": "inside the admin package (NEO never changes itself)",
    "file_type": "a file type a skill is not made of",
    "mode": "not a regular non-executable file (symlink, executable, submodule)",
    "mode_change": "a mode change",
    "rename_across": "a rename or copy whose source and destination are not both in scope",
    "test_add": "a test change other than adding a new tests/unit/test_<lowercase>.py",
    "merge_bases": "the head does not have exactly one merge base with the base (a criss-cross "
                   "history: the diff is taken from one base, GitHub merges over all of them)",
    "merge_commit": "a merge commit in the head's history (a NEO head is linear)",
    "branch_name": "the lock applies, and the head branch is not exactly neo/<request_id> (the "
                   "one branch the bridge creates)",
    "branch_lookalike": "the head branch imitates the neo/ prefix (neo-x, neo_x, neo.x): it would "
                        "read as NEO's to a person and escape a prefix check",
}

# Who counts as the bridge: one GitHub login per line, in the BASE's checkout next to this file,
# so a pull request cannot add itself or remove the bridge (``scripts/**`` is outside the scope).
# Not a repository variable: a variable changes without a pull request.
BRIDGE_LOGINS_FILE = Path(__file__).resolve().parent / "neo_bridge_logins"
# A GitHub login (letters, digits, single hyphens, at most 39) or an app's ``<name>[bot]``.
_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?")
# The host's ``REQUEST_ID_RE`` (cogno_host/neo/changes.py), restated: this script imports nothing.
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
NEO_PREFIX = "neo/"
# A ref-path prefix a branch name can carry in front of ``neo/``: ``refs/heads/neo/x`` and
# ``heads/neo/x`` are branches GitHub names exactly so, and they read as NEO's to a person.
_REF_PREFIX = re.compile(r"(?:refs/heads/|heads/)", re.IGNORECASE)
# What a decision line may print of a branch or a login: anything else becomes ``?``.
_PRINTABLE = re.compile(r"[^A-Za-z0-9._/@+\[\]-]")


@dataclass(frozen=True)
class Record:
    """One record of ``git diff --raw -z``. ``old_path`` is set only for a rename or a copy."""

    old_mode: str
    new_mode: str
    status: str
    path: str
    old_path: Optional[str] = None


@dataclass(frozen=True)
class Refusal:
    path: str
    rule: str

    def line(self) -> str:
        return f"REFUSED {self.path}: {self.rule} — {RULES[self.rule]}"


class MalformedDiff(ValueError):
    """The input is not the output of ``git diff --raw -z``."""


def parse_raw_z(data: str) -> List[Record]:
    """Parse ``git diff --raw -z`` output.

    Each record is ``:<old mode> <new mode> <old sha> <new sha> <status>`` NUL ``<path>`` NUL, and a
    rename or copy (``R<score>``, ``C<score>``) carries a second path NUL-terminated after it.
    """
    fields = data.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    records: List[Record] = []
    i = 0
    while i < len(fields):
        head = fields[i]
        if not head.startswith(":"):
            raise MalformedDiff(f"field {i}: expected a ':' header, got {head[:40]!r}")
        parts = head[1:].split(" ")
        if len(parts) != 5:
            raise MalformedDiff(f"field {i}: header has {len(parts)} parts, expected 5")
        old_mode, new_mode, _old_sha, _new_sha, status = parts
        two_paths = status[:1] in ("R", "C")
        need = 2 if two_paths else 1
        if i + need >= len(fields):
            raise MalformedDiff(f"field {i}: record {status!r} is missing its path")
        if two_paths:
            records.append(Record(old_mode, new_mode, status, path=fields[i + 2],
                                  old_path=fields[i + 1]))
        else:
            records.append(Record(old_mode, new_mode, status, path=fields[i + 1]))
        i += 1 + need
    return records


def _shape(path: str) -> Optional[str]:
    """The first SHAPE rule ``path`` breaks, or None. Shape is checked before scope, so a
    traversal never reaches the comparison it is trying to fool."""
    if path.startswith("/"):
        return "absolute"
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return "traversal"
    if not _PATH_CHARS.fullmatch(path):
        return "path_chars"
    if any(p.startswith(".") for p in parts):
        return "hidden"
    return None


def _is_admin(parts: Sequence[str]) -> bool:
    """``cogno_praxis/admin/...`` or a module ``cogno_praxis/admin.<ext>``, in any case. Case is
    folded because on a case-insensitive filesystem ``cogno_praxis/Admin/`` IS the admin package."""
    return len(parts) >= 2 and parts[1].split(".", 1)[0].lower() == ADMIN_NAME


def _path_rule(path: str, *, allow_tests: bool, status: str, new_mode: str) -> Optional[str]:
    """The rule ``path`` breaks as a side of a change, or None when it is in scope."""
    shape = _shape(path)
    if shape:
        return shape
    parts = path.split("/")
    if parts[0] == ALLOWED_ROOT and len(parts) >= 2:
        if _is_admin(parts):
            return "admin"
        name = parts[-1]
        if name not in ALLOWED_NAMES and not any(name.endswith(s) for s in ALLOWED_SUFFIXES):
            return "file_type"
        return None
    if allow_tests and path.startswith(TESTS_ROOT + "/"):
        ok = (len(parts) == 3 and _NEW_TEST_NAME.fullmatch(parts[-1]) is not None
              and path not in PROTECTED_TESTS and status == "A"
              and new_mode == REGULAR_FILE)
        return None if ok else "test_add"
    return "outside_scope"


def check(records: Iterable[Record], *, allow_tests: bool = NEO_MAY_ADD_TESTS) -> List[Refusal]:
    """Every refusal the records earn, in diff order. Empty means in scope."""
    records = list(records)
    if not records:
        return [Refusal("(no records)", "empty_diff")]
    out: List[Refusal] = []
    for r in records:
        kind = r.status[:1]
        if kind not in ("A", "M", "D", "T", "R", "C") or (kind in "AMDT" and len(r.status) != 1):
            out.append(Refusal(r.path, "status"))
            continue
        # Both sides of a rename or a copy are paths of this change. Checking only the
        # destination would let `tests/x.py -> cogno_praxis/x.py` delete a test unseen.
        sides = [r.path] if r.old_path is None else [r.old_path, r.path]
        refused_side = False
        for path in sides:
            rule = _path_rule(path, allow_tests=allow_tests,
                              status=kind if r.old_path is None else "R",
                              new_mode=r.new_mode)
            if rule:
                out.append(Refusal(path, rule))
                refused_side = True
        if r.old_path is not None and refused_side:
            out.append(Refusal(f"{r.old_path} -> {r.path}", "rename_across"))
        # The mode: what the change LEAVES must be a regular, non-executable file, and a
        # change may not flip a mode at all (a `chmod -x` is still a change to the system's
        # view of the file). A deletion leaves nothing, so it has no new mode to judge.
        if kind != "D":
            if r.new_mode != REGULAR_FILE:
                out.append(Refusal(r.path, "mode"))
            elif r.old_mode not in (ABSENT, r.new_mode):
                out.append(Refusal(r.path, "mode_change"))
    return out


class BadLogins(ValueError):
    """``scripts/neo_bridge_logins`` is missing or holds a line that is not a login."""


def read_logins(path: Path = BRIDGE_LOGINS_FILE) -> "frozenset[str]":
    """The bridge's logins, case-folded (GitHub logins are case-insensitive). Blank lines and
    ``#`` comments are skipped; any other line must be ONE login, or the whole file is refused:
    a file nobody can read must not shrink the set of pull requests the lock applies to."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BadLogins(f"cannot read {path.name}: {type(exc).__name__}") from None
    out = set()
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not _LOGIN.fullmatch(line):
            raise BadLogins(f"{path.name} line {n} is not a GitHub login")
        out.add(line.casefold())
    return frozenset(out)


def is_lookalike(branch: str) -> bool:
    """A branch that imitates the ``neo/`` prefix without being a plain ``neo/…`` branch. It FAILS
    CLOSED: a lookalike makes the lock apply and is then refused.

    * Any NON-ASCII branch. A homoglyph (Cyrillic U+0435 for ``e``, full-width U+FF4E for
      ``n``, Greek U+039D for ``N``) or an invisible character (U+200D, the zero-width joiner)
      is how a name reads as ``neo/`` and is not.
      Measured on 2026-11-02 over the last 130 pull requests of this repository: 0 non-ASCII
      branches, so nobody's ordinary work is caught.
    * Otherwise, after removing every leading ``refs/heads/`` and ``heads/`` and reading a ``0`` in
      the first three characters as ``o``, the name starts with ``neo`` followed by the end or by
      a character that is not a letter or a digit: ``neo-x``, ``NEO_x``, ``neo.x``, ``neo``,
      ``ne0/x``, ``refs/heads/neo/x``. Not ``neon-x``, ``neo2``, ``neo4j-…``, ``fix/neo-x``.
    * The one exception is a plain ``neo/…`` (any case, no ref prefix, no zero): that is the
      prefix itself, judged by ``branch_name``. A zero in the request id is not in the prefix."""
    if not branch.isascii():
        return True
    name = branch
    while (m := _REF_PREFIX.match(name)) is not None:
        name = name[m.end():]
    head, rest = name[:3], name[3:]
    if head.lower().replace("0", "o") != "neo":
        return False
    if rest[:1].isalnum():
        return False                                   # neon, neo2, ne0n: another word
    plain_prefix = name == branch and head.lower() == "neo" and rest.startswith("/")
    return not plain_prefix


def applies(author: str, branch: str, logins: "frozenset[str]") -> "Optional[str]":
    """Why the lock applies to a pull request (``author``, ``branch``, ``lookalike``), or None.
    The author is asked FIRST: the bridge's pull request is judged whatever branch it names."""
    if author.casefold() in logins:
        return "author"
    if branch.lower().startswith(NEO_PREFIX):
        return "branch"
    if is_lookalike(branch):
        return "lookalike"
    return None


def branch_refusals(branch: str) -> List[Refusal]:
    """The branch rules, for a pull request the lock applies to."""
    where = f"(branch {_shown(branch)})"
    out: List[Refusal] = []
    if not (branch.startswith(NEO_PREFIX)
            and _REQUEST_ID.fullmatch(branch[len(NEO_PREFIX):]) is not None):
        out.append(Refusal(where, "branch_name"))
    if is_lookalike(branch):
        out.append(Refusal(where, "branch_lookalike"))
    return out


def _shown(value: str) -> str:
    return _PRINTABLE.sub("?", value[:100]) or "?"


def _git_diff(base: str, head: str) -> str:
    cmd = ["git", "-c", "core.quotePath=false", "diff", "--raw", "-z", "-M",
           "--no-ext-diff", "--no-textconv", f"{base}...{head}"]
    done = subprocess.run(cmd, capture_output=True)
    if done.returncode != 0:
        raise MalformedDiff(f"git diff failed (rc={done.returncode}): "
                            f"{done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return done.stdout.decode("utf-8", "surrogateescape")


def _git_lines(*args: str, ok_rcs: Sequence[int] = (0,)) -> List[str]:
    done = subprocess.run(["git", *args], capture_output=True)
    if done.returncode not in ok_rcs:
        raise MalformedDiff(f"git {args[0]} failed (rc={done.returncode}): "
                            f"{done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return done.stdout.decode("utf-8", "replace").split()


def history_refusals(base: str, head: str) -> List[Refusal]:
    """The refusals the head's HISTORY earns: a NEO head is linear on exactly one merge base.

    Returns ``[]`` for a linear head. A merge-base count other than one is refused before the
    merge-commit walk, and with zero bases the caller must not take the three-dot diff at all."""
    for ref in (base, head):
        _git_lines("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    # rc 1 with no output is "no common ancestor"; anything above 1 is an error.
    bases = _git_lines("merge-base", "--all", base, head, ok_rcs=(0, 1))
    if len(bases) != 1:
        return [Refusal(f"(merge bases: {len(bases)})", "merge_bases")]
    merges = _git_lines("rev-list", "--merges", f"{base}..{head}")
    return [Refusal(f"(commit {sha[:12]})", "merge_commit") for sha in merges]


def main(argv: Optional[Sequence[str]] = None, stdin: Optional[str] = None,
         logins_file: Path = BRIDGE_LOGINS_FILE) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    history: List[Refusal] = []
    # ``--author A --branch B <base> <head>``: positional, so no value is ever read as a flag.
    if len(args) == 6 and args[0] == "--author" and args[2] == "--branch":
        author, branch = args[1], args[3]
        args = args[4:]
        if any(a.startswith("-") for a in args):
            print("usage: neo_scope_check.py --author <login> --branch <ref> <base> <head>",
                  file=sys.stderr)
            return 2
        try:
            why = applies(author, branch, read_logins(logins_file))
        except BadLogins as exc:
            print(f"NEO scope: cannot read who the bridge is — {exc}", file=sys.stderr)
            return 2
        shown = f"author={_shown(author)}, branch={_shown(branch)}"
        if why is None:
            print(f"NEO scope: not a NEO pull request ({shown})")
            return 0
        print(f"NEO scope: the lock applies by {why} ({shown})")
        history = branch_refusals(branch)
    try:
        if args == ["--stdin"]:
            data = sys.stdin.buffer.read().decode("utf-8", "surrogateescape") if stdin is None \
                else stdin
        elif len(args) == 2 and not any(a.startswith("-") for a in args):
            history = history + history_refusals(args[0], args[1])
            # With no single merge base the three-dot diff has nothing honest to say.
            if any(r.rule == "merge_bases" for r in history):
                for refusal in history:
                    print(refusal.line())
                print(f"NEO scope: REFUSED — history, 0 record(s) read, {len(history)} refusal(s)")
                return 1
            data = _git_diff(args[0], args[1])
        else:
            print("usage: neo_scope_check.py <base> <head> | --stdin", file=sys.stderr)
            return 2
        records = parse_raw_z(data)
    except MalformedDiff as exc:
        print(f"NEO scope: cannot read the diff — {exc}", file=sys.stderr)
        return 2
    refusals = history + check(records)
    for refusal in refusals:
        print(refusal.line())
    verdict = "REFUSED" if refusals else "ok"
    print(f"NEO scope: {verdict} — {len(records)} record(s) read, {len(refusals)} refusal(s)")
    return 1 if refusals else 0


if __name__ == "__main__":
    sys.exit(main())
