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

import pytest

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


#: Modules whose import would mean a write, a process, a thread, a network call, a database, an
#: import by name, or a secret. Matched on the first segment of the module name.
_FORBIDDEN_IMPORTS = frozenset({
    "os", "sys", "socket", "ssl", "select", "selectors", "subprocess", "pty", "signal",
    "threading", "_thread", "multiprocessing", "concurrent", "asyncio", "sched",
    "httpx", "requests", "urllib", "urllib3", "http", "aiohttp", "smtplib", "ftplib", "telnetlib",
    "psycopg", "psycopg2", "sqlite3", "dbm", "shelve",
    "shutil", "tempfile", "importlib", "runpy", "ctypes", "pickle",
})
#: Attribute names whose CALL or ACCESS writes, spawns, connects or reads the environment. Read
#: methods (``read_text``, ``iterdir``, ``glob``, ``is_file``) are not here: the vertical reads.
_FORBIDDEN_ATTRS = frozenset({
    "open", "write_text", "write_bytes", "touch", "unlink", "mkdir", "makedirs", "rmdir",
    "rename", "chmod", "symlink_to", "hardlink_to",
    "environ", "getenv", "putenv", "system", "popen", "fork",
    "create_subprocess_exec", "create_subprocess_shell", "run_in_executor",
    "Thread", "Timer", "Process", "Popen", "start_new_thread",
    "import_module", "connect", "urlopen",
})
#: Bare names whose CALL executes code, opens a file or starts a worker.
_FORBIDDEN_CALLS = frozenset({"open", "exec", "eval", "compile", "__import__", "breakpoint",
                              "Thread", "Timer", "Process", "Popen"})
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


def _is_main_guard(node: ast.stmt) -> bool:
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__")


def _runs_on_import(tree: ast.Module) -> "list[int]":
    """Line numbers of statements that CALL something when the module is imported: a bare call
    (``Thread(...).start()``, ``setup()``) at module level or inside a module-level block other
    than the ``__main__`` guard. Assignments are not here (``ROOT = Path(...)`` is a value); a
    call that starts a worker through an assignment is caught by its name above."""
    lines: "list[int]" = []
    pending: "list[ast.stmt]" = list(tree.body)
    while pending:
        stmt = pending.pop()
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if _is_main_guard(stmt):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, (ast.Call, ast.Await)):
            lines.append(stmt.lineno)
        for field in ("body", "orelse", "finalbody", "handlers"):
            pending.extend(getattr(stmt, field, []) or [])
    return sorted(lines)


def _violations(source: str) -> "list[str]":
    """Everything in ``source`` that would make the vertical do more than READ its package."""
    tree = ast.parse(source)
    found: "list[str]" = []
    for module in sorted(_imported(tree)):
        if module.split(".")[0] in _FORBIDDEN_IMPORTS:
            found.append(f"imports {module}")
        if module.startswith("cogno_praxis.") and module.split(".")[1] in _SIBLINGS:
            found.append(f"imports a sibling vertical: {module}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
            found.append(f"line {node.lineno}: .{node.attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FORBIDDEN_CALLS:
            found.append(f"line {node.lineno}: {node.func.id}()")
    found.extend(f"line {n}: runs a call on import" for n in _runs_on_import(tree))
    return found


def test_the_vertical_does_nothing_but_read():
    assert {"scheduler", "bookkeeper"} <= set(_SIBLINGS)
    sources = sorted(ADMIN.glob("*.py"))
    assert {p.name for p in sources} >= {"server.py", "service.py", "impact.py", "summary.py"}
    for path in sources:
        assert _violations(path.read_text(encoding="utf-8")) == [], path.name


#: One planted source per thing the detector must see. Each is the SMALLEST source that has it,
#: and several deliberately avoid the import so that the attribute or the on-import rule is the
#: only thing that can catch them.
_PLANTED = {
    "a thread module": "import threading\n",
    "a process module": "import multiprocessing\n",
    "an event loop module": "import asyncio\n",
    "an executor module": "from concurrent.futures import ThreadPoolExecutor\n",
    "Path.open in append mode": "def f(p):\n    return p.open('a')\n",
    "an async subprocess, no import": (
        "async def f(loop):\n    return await loop.create_subprocess_exec('ls')\n"),
    "a thread started on import, no import of threading": (
        "from somewhere import T\nT(target=print).start()\n"),
    "a thread started on import": (
        "import threading\nthreading.Thread(target=print, daemon=True).start()\n"),
    "a call on import inside a module-level block": (
        "try:\n    setup()\nexcept Exception:\n    pass\n"),
    "a thread built by name inside a function": (
        "from threading import Thread as T2\ndef f():\n    return Thread(target=f)\n"),
    "exec": "def f(src):\n    exec(src)\n",
    "an import by name": "def f(name):\n    return __import__(name)\n",
    "importlib": "import importlib\n",
    "the environment": "def f(e):\n    return e.environ\n",
    "a write": "def f(p):\n    p.write_text('x')\n",
    "a sibling vertical": "from cogno_praxis.scheduler.server import build_server\n",
}


@pytest.mark.parametrize("case", sorted(_PLANTED))
def test_the_detector_sees_each_planted_case(case):
    assert _violations(_PLANTED[case]), case


def test_the_detector_passes_a_source_that_only_reads():
    """THE CONTROL: reads, values, a function and the ``__main__`` guard are not violations."""
    clean = ("from pathlib import Path\n"
             "ROOT = Path(__file__).resolve().parent\n"
             "NAMES = sorted(p.name for p in ROOT.iterdir())\n"
             "def f(p):\n    return p.read_text(encoding='utf-8')\n"
             "if __name__ == '__main__':\n    print(f(ROOT))\n")
    assert _violations(clean) == []
