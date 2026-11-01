#!/usr/bin/env python3
"""The scope lock for the pull requests the NEO bridge opens.

NEO is an admin persona. When the owner approves a change to a vertical's skills, a headless code
agent edits a worktree of this repo and opens a pull request from a branch named
``neo/<request_id>``. The owner's rule is that NEO only improves the verticals' skills: it never
changes the system, and it never changes itself. This script is that rule as code. CI runs it on
every pull request whose head branch starts with ``neo/`` (``.github/workflows/neo-scope.yml``)
and nowhere else.

**Allowed:** a path under ``cogno_praxis/`` that is not the admin package (``cogno_praxis/admin``,
in any case, as a directory or a module). **Everything else is refused**, the build configuration,
the workflows, this script, the docs and the tests included.

Usage::

    python scripts/neo_scope_check.py <base> <head>   # runs git itself (three-dot: merge base)
    git diff --raw -z -M <base>...<head> | python scripts/neo_scope_check.py --stdin

Exit codes: 0 = every changed path is in scope; 1 = refused, one line per offending path naming
the rule it broke; 2 = the diff could not be read (usage, git failure, malformed input). Every
exit but 0 is a refusal: a checker that cannot read the diff must not pass it.

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

# Whether a NEO pull request may also change tests. STRICT (False) until the owner decides.
# Measured on 232e72d: appending one neutral sentence to each of the 21 prompt files fails 95 unit
# tests, so a real prompt improvement will often need its pinned test updated, and under the
# strict rule that pull request stays red until a person edits the test. The other side: a NEO
# that may edit tests may weaken the tests that hold its own output. When True, only ADDING or
# MODIFYING a regular `tests/unit/test_*.py` is allowed: never a deletion, a rename, a helper, a
# conftest, an integration test, or one of PROTECTED_TESTS.
NEO_MAY_EDIT_TESTS = False
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
    "test_edit": "a test change the test allowance does not cover",
}


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
        name = parts[-1]
        ok = (len(parts) == 3 and name.startswith("test_") and name.endswith(".py")
              and path not in PROTECTED_TESTS and status in ("A", "M")
              and new_mode == REGULAR_FILE)
        return None if ok else "test_edit"
    return "outside_scope"


def check(records: Iterable[Record], *, allow_tests: bool = NEO_MAY_EDIT_TESTS) -> List[Refusal]:
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


def _git_diff(base: str, head: str) -> str:
    cmd = ["git", "-c", "core.quotePath=false", "diff", "--raw", "-z", "-M",
           "--no-ext-diff", "--no-textconv", f"{base}...{head}"]
    done = subprocess.run(cmd, capture_output=True)
    if done.returncode != 0:
        raise MalformedDiff(f"git diff failed (rc={done.returncode}): "
                            f"{done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return done.stdout.decode("utf-8", "surrogateescape")


def main(argv: Optional[Sequence[str]] = None, stdin: Optional[str] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args == ["--stdin"]:
            data = sys.stdin.buffer.read().decode("utf-8", "surrogateescape") if stdin is None \
                else stdin
        elif len(args) == 2 and not any(a.startswith("-") for a in args):
            data = _git_diff(args[0], args[1])
        else:
            print("usage: neo_scope_check.py <base> <head> | --stdin", file=sys.stderr)
            return 2
        records = parse_raw_z(data)
    except MalformedDiff as exc:
        print(f"NEO scope: cannot read the diff — {exc}", file=sys.stderr)
        return 2
    refusals = check(records)
    for refusal in refusals:
        print(refusal.line())
    verdict = "REFUSED" if refusals else "ok"
    print(f"NEO scope: {verdict} — {len(records)} record(s) read, {len(refusals)} refusal(s)")
    return 1 if refusals else 0


if __name__ == "__main__":
    sys.exit(main())
