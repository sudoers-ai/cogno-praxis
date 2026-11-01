"""What the ``admin`` vertical READS: the verticals of this package, by inspection.

Pure logic over the files of the installed package. Nothing here imports another vertical, opens a
connection, reads the environment or writes anything — the two tools in ``server.py`` are thin
shells over :class:`AdminService`.

**The tool surface is read from the SOURCE (``ast``), never by building the servers.** Building a
vertical's FastMCP object means importing its ``server.py``, and importing is where the side
effects are: ``bookkeeper/server.py`` and ``coordinator/server.py`` build a module-level ``mcp`` on
import, and the bookkeeper's reads ``COGNO_BOOKKEEPER_DSN`` / ``COGNO_PG_DSN`` and opens Postgres
when one is set. The scheduler has no module-level ``mcp`` for exactly that reason (its comment:
building it on import opened two connections per subprocess). A reader that imported the servers
inside a host process would connect wherever that host's environment points. So every vertical is
read the same way — the admin vertical included — and the reading is static:

* a tool is a function decorated ``@<x>.tool(...)`` (or ``@<x>.tool``) anywhere in ``server.py``,
  in source order — the order FastMCP registers them;
* its name is ``name=`` when given, else the function's name;
* its description is ``description=`` when given (string literals, ``+`` and names bound to
  either, followed into ``cogno_praxis`` modules by ``from … import``), else the docstring,
  cleaned. A description that cannot be resolved statically is ``None`` and says so
  (``description_resolved=False``) — never a guess;
* its annotations are the ``ToolAnnotations(...)`` keywords written as literals;
* its input schema is what the signature says without running it: the parameter names, which are
  required (no default), the literal defaults, the annotation AS WRITTEN, and the JSON type for the
  four scalar annotations (``str``, ``int``, ``float``, ``bool``). FastMCP's own schema (pydantic)
  is richer for the composite ones; ``tests/unit/test_admin_service.py`` compares this reading
  with a real build of every vertical whose server can be built in-process, so the two cannot drift
  silently.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: The package this vertical belongs to. The admin vertical reads its siblings from the disk the
#: package was imported from — the installed package, never a path relative to the CWD.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

#: This vertical's own id, DERIVED from where this file lives, so a rename cannot leave a stale
#: literal behind.
SELF_ID = Path(__file__).resolve().parent.name

#: The four prompt slots a host loads (``docs/HOST_INTEGRATION.md`` §3). A vertical may ship fewer
#: (``companies`` ships only a scope); every ``prompts/*.txt`` is reported, in this order first.
PROMPT_SLOTS = ("system", "scope", "limits", "voice")

#: The annotation keywords MCP defines on ``ToolAnnotations``.
ANNOTATION_KEYS = ("title", "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

_SCALAR_TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}
_UNSET = object()


class AdminError(Exception):
    """A request the admin vertical refuses, in words a model can act on."""


class UnknownVerticalError(AdminError):
    """``get_vertical_config`` was asked for an id that is not a vertical of this package."""


@dataclass(frozen=True)
class ToolInfo:
    """One tool of a vertical's server, read statically from ``server.py``."""

    name: str
    description: Optional[str]
    description_resolved: bool
    annotations: "dict[str, Any]"
    input_schema: "dict[str, Any]"

    @property
    def read_only(self) -> bool:
        """``readOnlyHint=True`` written on the tool — the EGO's read-only mask reads this."""
        return self.annotations.get("readOnlyHint") is True

    @property
    def destructive(self) -> bool:
        """``destructiveHint=True`` written on the tool — what cogno-mcp turns into
        ``requires_confirmation`` (gate B, ``docs/HOST_INTEGRATION.md`` §5). An absent hint is
        NOT destructive here, because that is how the host's gate reads it."""
        return self.annotations.get("destructiveHint") is True


@dataclass(frozen=True)
class VerticalInfo:
    """One directory of the package: a vertical, what it ships, and its tool surface."""

    id: str
    is_self: bool
    has_server: bool
    has_entry_point: bool
    prompt_slots: "tuple[str, ...]"
    tools: "tuple[ToolInfo, ...]" = ()
    read_error: Optional[str] = None
    path: Path = field(default=PACKAGE_ROOT, compare=False, repr=False)


# ── the static reader ────────────────────────────────────────────────────────────────────────
def _parse(path: Path) -> Optional[ast.Module]:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return None


def _module_path(module: str, package_root: Path) -> Optional[Path]:
    """The file of a ``cogno_praxis.…`` module under ``package_root``; None for anything else."""
    parts = module.split(".")
    if not parts or parts[0] != package_root.name:
        return None
    base = package_root.joinpath(*parts[1:])
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


class _StaticStrings:
    """Resolves a string expression without executing anything: literals, ``+``, and names bound
    at module level (or imported from another ``cogno_praxis`` module) to such expressions."""

    def __init__(self, package_root: Path) -> None:
        self._root = package_root
        self._modules: "dict[Path, Optional[ast.Module]]" = {}

    def _tree(self, path: Path) -> Optional[ast.Module]:
        if path not in self._modules:
            self._modules[path] = _parse(path)
        return self._modules[path]

    def resolve(self, node: ast.expr, path: Path, depth: int = 0) -> Optional[str]:
        if depth > 8:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.resolve(node.left, path, depth + 1)
            right = self.resolve(node.right, path, depth + 1)
            return None if left is None or right is None else left + right
        if isinstance(node, ast.Name):
            return self._name(node.id, path, depth + 1)
        return None

    def _name(self, name: str, path: Path, depth: int) -> Optional[str]:
        tree = self._tree(path)
        if tree is None:
            return None
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == name for t in stmt.targets):
                    return self.resolve(stmt.value, path, depth)
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                if isinstance(stmt.target, ast.Name) and stmt.target.id == name:
                    return self.resolve(stmt.value, path, depth)
            elif isinstance(stmt, ast.ImportFrom) and stmt.module and stmt.level == 0:
                for alias in stmt.names:
                    if (alias.asname or alias.name) == name:
                        source = _module_path(stmt.module, self._root)
                        return None if source is None else self._name(alias.name, source, depth + 1)
        return None


def _tool_decorator(fn: "ast.FunctionDef | ast.AsyncFunctionDef") -> "tuple[bool, Optional[ast.Call]]":
    """(is a tool, the decorator call when it has arguments)."""
    for deco in fn.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(target, ast.Attribute) and target.attr == "tool":
            return True, deco if isinstance(deco, ast.Call) else None
    return False, None


def _literal(node: ast.expr) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return _UNSET


def _annotations(call: Optional[ast.Call]) -> "dict[str, Any]":
    if call is None:
        return {}
    for kw in call.keywords:
        if kw.arg == "annotations" and isinstance(kw.value, ast.Call):
            out: "dict[str, Any]" = {}
            for inner in kw.value.keywords:
                if inner.arg in ANNOTATION_KEYS:
                    value = _literal(inner.value)
                    if value is not _UNSET:
                        out[inner.arg] = value
            return out
    return {}


def _input_schema(fn: "ast.FunctionDef | ast.AsyncFunctionDef") -> "dict[str, Any]":
    args = fn.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults: "dict[str, ast.expr]" = {}
    for arg, default in zip(positional[len(positional) - len(args.defaults):], args.defaults):
        defaults[arg.arg] = default
    for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults):
        if kw_default is not None:
            defaults[arg.arg] = kw_default
    properties: "dict[str, Any]" = {}
    required: "list[str]" = []
    for arg in positional + list(args.kwonlyargs):
        prop: "dict[str, Any]" = {}
        if arg.annotation is not None:
            # A quoted annotation (a forward reference) is the same annotation, as written.
            written = (arg.annotation.value if isinstance(arg.annotation, ast.Constant)
                       and isinstance(arg.annotation.value, str) else ast.unparse(arg.annotation))
            prop["annotation"] = written
            if written in _SCALAR_TYPES:
                prop["type"] = _SCALAR_TYPES[written]
        if arg.arg in defaults:
            value = _literal(defaults[arg.arg])
            if value is not _UNSET:
                prop["default"] = value
        else:
            required.append(arg.arg)
        properties[arg.arg] = prop
    schema: "dict[str, Any]" = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def read_tool_surface(server_path: Path, package_root: Path = PACKAGE_ROOT) -> "tuple[ToolInfo, ...]":
    """Every tool ``server_path`` registers, in source order, read without importing it.

    Raises :class:`AdminError` when the file does not parse — a vertical whose surface cannot be
    read is reported as such, never as a vertical with no tools.
    """
    tree = _parse(server_path)
    if tree is None:
        raise AdminError(f"{server_path.name} could not be read as Python")
    strings = _StaticStrings(package_root)
    found: "list[tuple[int, ToolInfo]]" = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_tool, call = _tool_decorator(node)
        if not is_tool:
            continue
        name = node.name
        description: Optional[str] = None
        resolved = True
        explicit = False
        for kw in call.keywords if call is not None else []:
            if kw.arg == "name":
                literal = _literal(kw.value)
                if isinstance(literal, str):
                    name = literal
            elif kw.arg == "description":
                explicit = True
                description = strings.resolve(kw.value, server_path)
                resolved = description is not None
        if not explicit:
            description = ast.get_docstring(node, clean=True)
        found.append((node.lineno, ToolInfo(name=name, description=description,
                                            description_resolved=resolved,
                                            annotations=_annotations(call),
                                            input_schema=_input_schema(node))))
    return tuple(tool for _, tool in sorted(found, key=lambda pair: pair[0]))


def _has_entry_point(server_path: Path) -> bool:
    """``if __name__ == "__main__":`` at module level — the ``python -m`` entry."""
    tree = _parse(server_path)
    if tree is None:
        return False
    for stmt in tree.body:
        if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Compare):
            names = [stmt.test.left, *stmt.test.comparators]
            texts = {n.id if isinstance(n, ast.Name) else _literal(n) for n in names}
            if "__name__" in texts and "__main__" in texts:
                return True
    return False


def _prompt_slots(vertical_dir: Path) -> "tuple[str, ...]":
    prompts = vertical_dir / "prompts"
    if not prompts.is_dir():
        return ()
    stems = {p.stem for p in prompts.glob("*.txt") if p.is_file()}
    known = [s for s in PROMPT_SLOTS if s in stems]
    return tuple(known + sorted(stems - set(PROMPT_SLOTS)))


def discover_verticals(package_root: Path = PACKAGE_ROOT,
                       self_id: str = SELF_ID) -> "tuple[VerticalInfo, ...]":
    """Every vertical of the package, by inspection of the disk — never a hand-written list.

    A vertical is a sub-package (a directory with ``__init__.py``) that ships a ``server.py`` or a
    ``prompts/`` directory with at least one ``.txt``. Sorted by id.
    """
    found: "list[VerticalInfo]" = []
    for child in sorted(package_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if not (child / "__init__.py").is_file():
            continue
        server = child / "server.py"
        slots = _prompt_slots(child)
        has_server = server.is_file()
        if not has_server and not slots:
            continue
        tools: "tuple[ToolInfo, ...]" = ()
        error: Optional[str] = None
        if has_server:
            try:
                tools = read_tool_surface(server, package_root)
            except AdminError as exc:
                error = str(exc)
        found.append(VerticalInfo(id=child.name, is_self=child.name == self_id,
                                  has_server=has_server,
                                  has_entry_point=has_server and _has_entry_point(server),
                                  prompt_slots=slots, tools=tools, read_error=error, path=child))
    return tuple(found)


# ── the service ──────────────────────────────────────────────────────────────────────────────
def _tool_listing(tool: ToolInfo) -> "dict[str, Any]":
    return {"name": tool.name, "read_only": tool.read_only, "destructive": tool.destructive,
            "annotations": dict(tool.annotations)}


def _tool_config(tool: ToolInfo) -> "dict[str, Any]":
    return {"name": tool.name, "description": tool.description,
            "description_resolved": tool.description_resolved,
            "input_schema": tool.input_schema, "annotations": dict(tool.annotations),
            "read_only": tool.read_only, "destructive": tool.destructive}


class AdminService:
    """The two reads the admin vertical offers, over a package root (injectable for tests)."""

    def __init__(self, package_root: Optional[Path] = None, *, self_id: str = SELF_ID) -> None:
        self._root = package_root if package_root is not None else PACKAGE_ROOT
        self._self_id = self_id

    def _verticals(self) -> "tuple[VerticalInfo, ...]":
        # Read on every call: the disk is the source, and a cached reading would describe a tree
        # that may have changed under it.
        return discover_verticals(self._root, self._self_id)

    def known_ids(self) -> "list[str]":
        return [v.id for v in self._verticals()]

    def list_verticals(self) -> "list[dict[str, Any]]":
        out: "list[dict[str, Any]]" = []
        for v in self._verticals():
            row: "dict[str, Any]" = {
                "id": v.id, "is_self": v.is_self, "has_server": v.has_server,
                "has_entry_point": v.has_entry_point,
                "has_prompts": bool(v.prompt_slots), "prompt_slots": list(v.prompt_slots),
                "tools": [_tool_listing(t) for t in v.tools],
            }
            if v.read_error is not None:
                row["read_error"] = v.read_error
            out.append(row)
        return out

    def get_vertical_config(self, vertical: str) -> "dict[str, Any]":
        verticals = {v.id: v for v in self._verticals()}
        if not isinstance(vertical, str) or vertical not in verticals:
            known = ", ".join(sorted(verticals)) or "(none)"
            raise UnknownVerticalError(
                f"Unknown vertical {vertical!r}. Known verticals: {known}. "
                "Call list_verticals to see them, and pass one of those ids exactly.")
        v = verticals[vertical]
        prompts = {slot: (v.path / "prompts" / f"{slot}.txt").read_text(encoding="utf-8")
                   for slot in v.prompt_slots}
        config: "dict[str, Any]" = {
            "id": v.id, "is_self": v.is_self, "has_server": v.has_server,
            "has_entry_point": v.has_entry_point, "prompts": prompts,
            "tools": [_tool_config(t) for t in v.tools],
        }
        if v.read_error is not None:
            config["read_error"] = v.read_error
        return config


__all__ = [
    "ANNOTATION_KEYS",
    "PACKAGE_ROOT",
    "PROMPT_SLOTS",
    "SELF_ID",
    "AdminError",
    "AdminService",
    "ToolInfo",
    "UnknownVerticalError",
    "VerticalInfo",
    "discover_verticals",
    "read_tool_surface",
]
