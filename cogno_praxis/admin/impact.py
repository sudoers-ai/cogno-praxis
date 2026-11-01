"""Is a proposed change SMALL or LARGE? Pure, no I/O, over a typed description of the change.

Three questions decide it: does the change CORRECT or ADD (its declared ``kind``), what does it
TOUCH, and how BIG is it. Only a CORRECTION can be small: an improvement or an evolution is LARGE
whatever its diff (the owner's rule: «sobre as evoluções e melhoria, não entra também»).

The rules are CLOSED: they are the owner's decision, written here once, and every one of them
raises the size — none lowers it. A change is LARGE when ANY of these holds:

0. ``kind_not_declared`` — ``kind`` is missing, blank, or not one of :data:`KINDS`;
   ``not_a_correction`` — ``kind`` is ``improvement`` or ``evolution``;

1. ``new_capability`` — a new vertical, persona or tool (declared by a flag, or derived from a
   path the change CREATES: a vertical's ``__init__.py`` / ``server.py``, or a ``prompts/*.txt``);
2. ``scope_or_limits`` — a change to a ``scope.txt`` or a ``limits.txt`` (what the guard lets in
   and what the judge holds the persona to);
3. ``store_or_schema`` — a ``store.py``, anything under a ``stores/`` directory, a migration, or a
   declared schema change (``_ensure_schema`` lives inside a store adapter; a change that touches
   it elsewhere says so by the flag);
4. ``dependency`` — ``pyproject.toml``;
5. ``diff_size`` — more than :data:`MAX_SMALL_DIFF_LINES` lines added + removed, over all paths;
6. ``admin_code`` — any path under ``cogno_praxis/admin/``, or a package-root module or package
   named ``admin.*`` / ``admin_*`` (``admin.py``, ``admin_x.py``), in any case: NEO's own vertical.

Every path rule matches CASE-INSENSITIVELY: a rule that only raises the size reads a name the way
the most permissive filesystem would, so ``Scope.txt`` or ``Admin/`` cannot make a change small.

Otherwise SMALL. **When in doubt, LARGE** (``doubt``): a path whose type is not one of the
:data:`KNOWN_PATH_KINDS`, a path that does not read as a repo-relative POSIX path, a missing line
count, or a change with no paths at all. A classifier that answered SMALL on what it could not
read would be the size decided by the gap.

:func:`escalate` can only RAISE a classification: it takes no size and always answers LARGE.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Literal, Optional

Size = Literal["small", "large"]

#: The boundary of rule 5. 200 lines added + removed is still SMALL; 201 is LARGE.
MAX_SMALL_DIFF_LINES = 200

#: The rule codes, closed. Every reason starts with one of them followed by ``": "``.
RULES = ("kind_not_declared", "not_a_correction", "new_capability", "scope_or_limits",
         "store_or_schema", "dependency", "diff_size",
         "admin_code", "doubt", "escalated")

#: The path types the classifier KNOWS, as ``fnmatch`` patterns over the repo-relative path (the
#: depth must match too). Anything else is DOUBT. A rule above may still make a known path LARGE
#: (``store.py`` is a ``.py``, ``pyproject.toml`` is rule 4); this list only decides what is known.
KNOWN_PATH_KINDS = (
    "cogno_praxis/*.py",
    "cogno_praxis/*/*.py",
    "cogno_praxis/*/*/*.py",
    "cogno_praxis/*/prompts/*.txt",
    "tests/*.py",
    "tests/*/*.py",
    "docs/*.md",
    "examples/*.py",
    "*.md",
    "pyproject.toml",
)

#: The kinds of change, CLOSED and declared by whoever describes the change. Only the first can be
#: small.
KINDS = ("correction", "improvement", "evolution")
CORRECTION = "correction"

#: NEO's own vertical: the package-root segment ``admin`` followed by nothing, a ``.`` or a ``_``
#: (``admin/``, ``admin.py``, ``admin_x.py``, ``admin_tools/``), matched CASE-INSENSITIVELY. A
#: case-insensitive filesystem (or a checkout tool) treats ``Admin/`` and ``admin/`` as one place,
#: and a module beside the package is NEO's code all the same; a rule that only raises the size
#: must not be dodged by a capital letter or a suffix. ``administrative/`` is not this.
_ADMIN_SEGMENT = re.compile(r"admin(?:[._].*)?")
_SCOPE_OR_LIMITS = ("scope.txt", "limits.txt")
_DEPENDENCY_FILES = ("pyproject.toml",)


@dataclass(frozen=True)
class PathChange:
    """One changed path: repo-relative POSIX, the lines it adds and removes (``None`` = not
    known), and whether the change CREATES it."""

    path: str
    added: Optional[int]
    removed: Optional[int]
    created: bool = False


@dataclass(frozen=True)
class Change:
    """A proposed change: what it is (``kind``), its paths, plus the facts a path list cannot
    show. ``kind`` has no default that means anything: absent, it is LARGE."""

    paths: "tuple[PathChange, ...]"
    kind: Optional[str] = None
    new_vertical: bool = False
    new_persona: bool = False
    new_tool: bool = False
    schema_change: bool = False


@dataclass(frozen=True)
class Classification:
    size: Size
    reasons: "tuple[str, ...]" = ()


def _reads_as_path(path: str) -> bool:
    if not isinstance(path, str) or not path or path != path.strip():
        return False
    if path.startswith("/") or "\\" in path or "\x00" in path:
        return False
    parts = path.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def _known_path_kind(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) and _depth_ok(path, pattern)
               for pattern in KNOWN_PATH_KINDS)


def _depth_ok(path: str, pattern: str) -> bool:
    # fnmatch's ``*`` crosses ``/``; a kind is a SHAPE, so the depth must match too.
    return path.count("/") == pattern.count("/")


def _created_capability(path: str) -> Optional[str]:
    parts = path.casefold().split("/")
    if len(parts) == 3 and parts[0] == "cogno_praxis" and parts[2] in ("__init__.py", "server.py"):
        return f"creates {path} (a new vertical)"
    if len(parts) == 4 and parts[0] == "cogno_praxis" and parts[2] == "prompts" \
            and parts[3].endswith(".txt"):
        return f"creates {path} (a new persona slot)"
    return None


def _name(path: str) -> str:
    """The basename, case-folded: every path rule below only RAISES the size, so it reads a name
    the way the most permissive filesystem would."""
    return path.rsplit("/", 1)[-1].casefold()


def _is_admin_code(path: str) -> bool:
    parts = path.casefold().split("/")
    return (len(parts) >= 2 and parts[0] == "cogno_praxis"
            and _ADMIN_SEGMENT.fullmatch(parts[1]) is not None)


def _store_or_schema(path: str) -> bool:
    parts = path.casefold().split("/")
    name = parts[-1]
    return (name == "store.py" or "stores" in parts[:-1] or "migrations" in parts[:-1]
            or "migration" in name.lower())


def classify(change: Change) -> Classification:
    """SMALL or LARGE, with every rule that made it LARGE (one reason per hit, in rule order)."""
    reasons: "list[str]" = []

    def hit(rule: str, detail: str) -> None:
        reasons.append(f"{rule}: {detail}")

    kind = change.kind
    if not isinstance(kind, str) or kind not in KINDS:
        hit("kind_not_declared", "kind not declared"
            + (f" ({kind!r} is not one of {', '.join(KINDS)})"
               if isinstance(kind, str) and kind.strip() else ""))
    elif kind != CORRECTION:
        hit("not_a_correction", f"an {kind} is large whatever its diff")

    paths = tuple(change.paths) if change.paths is not None else ()
    for flag, what in ((change.new_vertical, "a new vertical"), (change.new_persona, "a new persona"),
                       (change.new_tool, "a new tool")):
        if flag:
            hit("new_capability", f"declared: {what}")
    readable = [p for p in paths if isinstance(p, PathChange) and _reads_as_path(p.path)]
    for p in readable:
        if p.created:
            created = _created_capability(p.path)
            if created:
                hit("new_capability", created)
    for p in readable:
        if _name(p.path) in _SCOPE_OR_LIMITS:
            hit("scope_or_limits", p.path)
    if change.schema_change:
        hit("store_or_schema", "declared: a schema change")
    for p in readable:
        if _store_or_schema(p.path):
            hit("store_or_schema", p.path)
    for p in readable:
        if _name(p.path) in _DEPENDENCY_FILES:
            hit("dependency", p.path)
    counted = [p for p in readable if _is_count(p.added) and _is_count(p.removed)]
    total = sum(int(p.added or 0) + int(p.removed or 0) for p in counted)
    if total > MAX_SMALL_DIFF_LINES:
        hit("diff_size", f"{total} lines added + removed > {MAX_SMALL_DIFF_LINES}")
    for p in readable:
        if _is_admin_code(p.path):
            hit("admin_code", p.path)

    if not paths:
        hit("doubt", "the change names no path")
    for p in paths:
        if not isinstance(p, PathChange) or not _reads_as_path(p.path):
            hit("doubt", "a path that does not read as a repo-relative path")
            continue
        if not (_is_count(p.added) and _is_count(p.removed)):
            hit("doubt", f"{p.path}: a missing line count")
        if not _known_path_kind(p.path):
            hit("doubt", f"{p.path}: an unknown path type")

    return Classification("large" if reasons else "small", tuple(reasons))


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def escalate(classification: Classification, *, by: str = "reviewer", reason: str) -> Classification:
    """Raise a classification to LARGE, recording who did and why. It takes NO size: there is no
    way to ask it for SMALL, and a LARGE stays LARGE (its reasons kept, this one added).

    ``by`` is the role that escalates — by default ``reviewer``. A blank
    ``reason`` is refused: an escalation nobody can read back is a size nobody can explain.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("escalate needs a reason")
    who = by.strip() if isinstance(by, str) and by.strip() else "reviewer"
    return Classification("large", tuple(classification.reasons)
                          + (f"escalated: by {who}: {' '.join(reason.split())}",))


__all__ = [
    "CORRECTION",
    "KINDS",
    "MAX_SMALL_DIFF_LINES",
    "RULES",
    "KNOWN_PATH_KINDS",
    "Change",
    "Classification",
    "PathChange",
    "Size",
    "classify",
    "escalate",
]
