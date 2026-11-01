"""The admin server: exactly two tools, both READ-ONLY by annotation, and nothing that writes.

The read-only claim is checked three ways, because each one alone can be satisfied by accident:
the annotations FastMCP really registers; the same annotations as the admin vertical reads them
about ITSELF; and the source of the vertical, which must not import a sibling vertical, a network
or database client, or the environment.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from cogno_praxis.admin.server import build_server
from cogno_praxis.admin.service import AdminService

ADMIN = Path(__import__("cogno_praxis.admin", fromlist=["x"]).__file__).resolve().parent


def _text(result) -> str:
    content = result[0] if isinstance(result, tuple) else result
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


async def test_exactly_two_tools_both_read_only_none_destructive():
    tools = await build_server().list_tools()
    assert [t.name for t in tools] == ["list_verticals", "get_vertical_config"]
    for t in tools:
        assert t.annotations is not None and t.annotations.readOnlyHint is True, t.name
        assert not t.annotations.destructiveHint, t.name


def test_the_admin_vertical_reads_itself_as_read_only():
    row = {v["id"]: v for v in AdminService().list_verticals()}["admin"]
    assert row["tools"] and all(t["read_only"] and not t["destructive"] for t in row["tools"])


async def test_list_verticals_answers_json_with_every_vertical():
    out = json.loads(_text(await build_server().call_tool("list_verticals", {})))
    assert [v["id"] for v in out] == [v["id"] for v in AdminService().list_verticals()]


async def test_get_vertical_config_answers_the_prompts():
    out = json.loads(_text(await build_server().call_tool("get_vertical_config",
                                                          {"vertical": "bookkeeper"})))
    assert out["prompts"]["scope"] == (ADMIN.parent / "bookkeeper" / "prompts" /
                                       "scope.txt").read_text(encoding="utf-8")


async def test_an_unknown_id_is_refused_in_words_by_the_tool():
    text = _text(await build_server().call_tool("get_vertical_config", {"vertical": "nope"}))
    assert text.startswith("ERROR: Unknown vertical 'nope'. Known verticals: ")
    assert "scheduler" in text and "bookkeeper" in text and "admin" in text


# Imports and names that would mean a write, a network call, a database or a secret.
_FORBIDDEN_IMPORTS = ("os", "socket", "subprocess", "httpx", "requests", "urllib", "psycopg",
                      "sqlite3", "shutil", "tempfile")
#: The other verticals, DERIVED — a vertical added tomorrow is a sibling the day it lands.
_SIBLINGS = tuple(v for v in AdminService().known_ids() if v != "admin")


def _imported(tree: ast.Module) -> "set[str]":
    names: "set[str]" = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_the_vertical_imports_no_io_and_no_sibling():
    assert {"scheduler", "bookkeeper"} <= set(_SIBLINGS)
    sources = sorted(ADMIN.glob("*.py"))
    assert {p.name for p in sources} >= {"server.py", "service.py", "impact.py", "summary.py"}
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = _imported(tree)
        bad = {m for m in imported if m.split(".")[0] in _FORBIDDEN_IMPORTS}
        assert not bad, f"{path.name} imports {bad}"
        siblings = {m for m in imported
                    if m.startswith("cogno_praxis.") and m.split(".")[1] in _SIBLINGS}
        assert not siblings, f"{path.name} imports a sibling vertical: {siblings}"


def test_no_file_is_opened_for_writing_and_no_environment_is_read():
    for path in sorted(ADMIN.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("write_text", "write_bytes",
                                                                 "unlink", "mkdir", "environ",
                                                                 "getenv", "rmdir", "rename"):
                raise AssertionError(f"{path.name}:{node.lineno} uses .{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "open":
                raise AssertionError(f"{path.name}:{node.lineno} calls open()")


def test_the_control_the_write_detector_sees_a_planted_write():
    """The detector above fires on what it must: the same walk over a planted source."""
    planted = ast.parse("from pathlib import Path\nPath('x').write_text('y')\nimport os\n")
    attrs = {n.attr for n in ast.walk(planted) if isinstance(n, ast.Attribute)}
    assert "write_text" in attrs
    assert "os" in _imported(planted)
