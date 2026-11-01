"""The admin vertical READS the package: which verticals exist, their prompts, their tool surface.

Three kinds of assertion:

* **The real tree.** The inspection finds the scheduler and the bookkeeper with their real tools
  and annotations, finds every vertical on disk (the denominator is derived, not typed), and
  lists ``admin`` itself, flagged.
* **The parity pair.** The tool surface is read STATICALLY (``ast``), so it could drift from what
  FastMCP really registers. Every vertical whose server can be built in-process here is built,
  and its ``list_tools()`` is compared with the static reading: names in order, annotations,
  descriptions, parameter names, required set, defaults and the scalar types. A static reader
  that missed a decorator, a ``description=`` or a keyword would fail here, not in production.
* **A planted tree.** A package written to ``tmp_path`` proves what the reader does with what
  the real tree does not have today: a server that does not parse, a server whose import would
  have a side effect (it is never imported), a ``description=`` it cannot resolve, a ``name=``.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from cogno_praxis.admin.service import (
    PACKAGE_ROOT,
    SELF_ID,
    AdminService,
    UnknownVerticalError,
    discover_verticals,
    read_tool_surface,
)

PKG = Path(__import__("cogno_praxis").__file__).resolve().parent


def _on_disk() -> "set[str]":
    """The verticals by the definition, computed here independently of the service."""
    out = set()
    for d in PKG.iterdir():
        if d.is_dir() and not d.name.startswith(("_", ".")) and (d / "__init__.py").is_file():
            if (d / "server.py").is_file() or any((d / "prompts").glob("*.txt")):
                out.add(d.name)
    return out


def _by_id() -> "dict[str, dict]":
    return {v["id"]: v for v in AdminService().list_verticals()}


# ── the real tree ────────────────────────────────────────────────────────────────────────────
def test_the_package_root_is_the_installed_package():
    assert PACKAGE_ROOT == PKG
    assert SELF_ID == "admin"


def test_every_vertical_on_disk_is_listed_and_nothing_else():
    listed = set(_by_id())
    assert listed == _on_disk()
    # the denominator, stated: the ones the brief names are in it
    assert {"scheduler", "bookkeeper", "coordinator", "companies", "closer", "interviewer",
            "admin"} <= listed


def test_the_listing_is_sorted_and_deterministic():
    first = AdminService().list_verticals()
    assert [v["id"] for v in first] == sorted(v["id"] for v in first)
    assert json.dumps(first) == json.dumps(AdminService().list_verticals())


def test_admin_lists_itself_and_is_the_only_one_flagged():
    rows = _by_id()
    assert rows["admin"]["is_self"] is True
    assert [v for v, row in rows.items() if row["is_self"]] == ["admin"]
    assert [t["name"] for t in rows["admin"]["tools"]] == ["list_verticals", "get_vertical_config"]


def test_the_scheduler_is_read_with_its_real_tools_and_annotations():
    sched = _by_id()["scheduler"]
    assert sched["has_server"] and sched["has_entry_point"]
    assert sched["prompt_slots"] == ["system", "scope", "limits", "voice"]
    tools = {t["name"]: t for t in sched["tools"]}
    assert list(tools) == [
        "list_schedulable_hosts", "resolve_date", "check_availability", "book_appointment",
        "block_schedule", "list_appointments", "reschedule_appointment", "confirm_appointment",
        "complete_appointment", "cancel_appointment", "get_schedule_settings",
        "set_schedule_settings", "set_auto_confirm"]
    assert tools["check_availability"]["read_only"] is True
    assert tools["book_appointment"]["read_only"] is False
    assert tools["book_appointment"]["destructive"] is False
    assert tools["cancel_appointment"]["destructive"] is True
    assert tools["cancel_appointment"]["annotations"] == {"readOnlyHint": False,
                                                          "destructiveHint": True}
    assert {n for n, t in tools.items() if t["destructive"]} == {
        "cancel_appointment", "reschedule_appointment"}


def test_the_bookkeeper_is_read_with_its_real_tools_and_annotations():
    book = _by_id()["bookkeeper"]
    tools = {t["name"]: t for t in book["tools"]}
    assert list(tools) == ["add_income", "add_outcome", "get_summary", "list_clients", "search",
                           "remove_by_search", "get_usage", "math", "help"]
    assert {n for n, t in tools.items() if t["read_only"]} == {
        "get_summary", "list_clients", "search", "get_usage", "math", "help"}
    # remove_by_search asks by itself (gate C) and declares no destructiveHint
    assert tools["remove_by_search"]["destructive"] is False


def test_a_vertical_with_prompts_and_no_server_is_listed_as_such():
    closer = _by_id()["closer"]
    assert closer["has_server"] is False and closer["tools"] == []
    assert closer["has_prompts"] is True
    companies = _by_id()["companies"]
    assert companies["prompt_slots"] == ["scope"]


# ── get_vertical_config ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vertical", ["scheduler", "bookkeeper", "admin", "closer"])
def test_the_config_returns_the_real_prompt_texts(vertical):
    cfg = AdminService().get_vertical_config(vertical)
    on_disk = {p.stem: p.read_text(encoding="utf-8")
               for p in (PKG / vertical / "prompts").glob("*.txt")}
    assert cfg["prompts"] == on_disk
    assert cfg["prompts"], "the control: there was something to compare"


def test_the_config_carries_descriptions_schemas_and_annotations():
    tools = {t["name"]: t for t in AdminService().get_vertical_config("scheduler")["tools"]}
    avail = tools["check_availability"]
    assert avail["description"].startswith("List free time slots for a professional")
    assert avail["input_schema"]["required"] == ["host_id", "date"]
    assert avail["input_schema"]["properties"]["host_name"] == {
        "annotation": "str", "type": "string", "default": ""}
    # a description= built from constants in ANOTHER module, resolved statically
    from cogno_praxis.scheduler.service import (RESOLVE_DATE_DESCRIPTION,
                                                RESOLVE_DATE_SCHEDULER_SUFFIX)
    assert tools["resolve_date"]["description"] == (RESOLVE_DATE_DESCRIPTION
                                                    + RESOLVE_DATE_SCHEDULER_SUFFIX)
    assert tools["resolve_date"]["description_resolved"] is True


@pytest.mark.parametrize("bad", ["nope", "Scheduler", "../scheduler", "scheduler/", "", " admin",
                                 "__pycache__", "prompts"])
def test_an_unknown_id_is_refused_in_words_listing_the_known(bad):
    with pytest.raises(UnknownVerticalError) as err:
        AdminService().get_vertical_config(bad)
    text = str(err.value)
    assert text.startswith("Unknown vertical")
    for known in _on_disk():
        assert known in text


def test_a_non_string_id_is_refused_too():
    with pytest.raises(UnknownVerticalError):
        AdminService().get_vertical_config(None)  # type: ignore[arg-type]


# ── the parity pair: static reading == FastMCP's real registration ───────────────────────────
def _real_servers():
    from cogno_praxis.admin.server import build_server as admin
    from cogno_praxis.bookkeeper.server import build_server as bookkeeper
    from cogno_praxis.companies.server import build_server as companies
    from cogno_praxis.coordinator.server import build_server as coordinator
    from cogno_praxis.scheduler.server import build_server as scheduler
    return {"admin": admin, "bookkeeper": bookkeeper, "companies": companies,
            "coordinator": coordinator, "scheduler": scheduler}


def test_the_parity_covers_every_vertical_with_a_server():
    with_server = {v for v, row in _by_id().items() if row["has_server"]}
    assert with_server == set(_real_servers())


@pytest.mark.parametrize("vertical", sorted(_real_servers()))
async def test_the_static_reading_is_what_fastmcp_registers(vertical):
    real = await _real_servers()[vertical]().list_tools()
    static = AdminService().get_vertical_config(vertical)["tools"]
    assert [t.name for t in real] == [t["name"] for t in static]
    for r, s in zip(real, static):
        ann = r.annotations.model_dump(exclude_none=True) if r.annotations else {}
        assert ann == s["annotations"], r.name
        assert s["description_resolved"] is True, r.name
        assert inspect.cleandoc(r.description or "") == inspect.cleandoc(s["description"] or ""), \
            r.name
        props = r.inputSchema.get("properties", {})
        assert list(props) == list(s["input_schema"]["properties"]), r.name
        assert set(r.inputSchema.get("required", [])) == set(s["input_schema"].get("required", [])), \
            r.name
        for pname, sprop in s["input_schema"]["properties"].items():
            if "default" in sprop:
                assert props[pname].get("default") == sprop["default"], (r.name, pname)
            if "type" in sprop:
                assert props[pname].get("type") == sprop["type"], (r.name, pname)


# ── a planted tree ───────────────────────────────────────────────────────────────────────────
def _plant(root: Path) -> Path:
    pkg = root / "cogno_praxis"
    (pkg / "alpha" / "prompts").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "texts.py").write_text('SHARED = "shared " + "text"\n')
    (pkg / "alpha" / "__init__.py").write_text("")
    (pkg / "alpha" / "prompts" / "voice.txt").write_text("voz\n", encoding="utf-8")
    (pkg / "alpha" / "prompts" / "extra.txt").write_text("x\n", encoding="utf-8")
    (pkg / "alpha" / "server.py").write_text(
        "from cogno_praxis.texts import SHARED\n"
        "LOCAL = SHARED + '!'\n"
        "def build_server():\n"
        "    @mcp.tool(name='renamed', annotations=ToolAnnotations(readOnlyHint=True))\n"
        "    def original(a: int, b: 'list[str]', c: bool = True) -> str:\n"
        "        '''  Doc\n            indented.'''\n"
        "    @mcp.tool(description=LOCAL)\n"
        "    async def from_constant() -> str: ...\n"
        "    @mcp.tool(description=f'{LOCAL}')\n"
        "    def unresolved() -> str: ...\n"
        "    @mcp.tool\n"
        "    def bare(*, k: str = 'v') -> str: ...\n"
        "if __name__ == '__main__':\n"
        "    build_server()\n")
    # THE CANARY: a server that IMPORTS CLEANLY (stdlib only; the names it uses inside
    # build_server are only looked up if that is called) and writes a file when it is imported.
    # A reader that executed it (import, exec, runpy) would leave the file behind, and one that
    # swallowed an error afterwards would still have run it.
    (pkg / "canary").mkdir()
    (pkg / "canary" / "__init__.py").write_text("")
    (pkg / "canary" / "server.py").write_text(
        "import pathlib\n"
        f"pathlib.Path({str(root / 'IMPORTED')!r}).write_text('imported')\n"
        "def build_server():\n"
        "    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))\n"
        "    def ping() -> str:\n"
        "        \"\"\"Ping.\"\"\"\n")
    (pkg / "broken").mkdir()
    (pkg / "broken" / "__init__.py").write_text("")
    (pkg / "broken" / "server.py").write_text("def (:\n")
    (pkg / "no_init").mkdir()
    (pkg / "no_init" / "server.py").write_text("")
    (pkg / "_private").mkdir()
    (pkg / "_private" / "__init__.py").write_text("")
    (pkg / "_private" / "server.py").write_text("")
    (pkg / "plain_lib").mkdir()
    (pkg / "plain_lib" / "__init__.py").write_text("")
    return pkg


def test_the_canary_fires_when_imported(tmp_path):
    """THE CONTROL the next test needs: the canary is valid Python and DOES write its file when it
    is executed. Without this, "the file is absent" could mean "the canary never works"."""
    import runpy
    pkg = _plant(tmp_path)
    runpy.run_path(str(pkg / "canary" / "server.py"))
    assert (tmp_path / "IMPORTED").read_text() == "imported"


def test_a_server_that_imports_cleanly_is_never_executed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = _plant(tmp_path)
    found = {v.id: v for v in discover_verticals(pkg)}
    AdminService(pkg).list_verticals()
    AdminService(pkg).get_vertical_config("canary")
    assert not (tmp_path / "IMPORTED").exists()
    assert [t.name for t in found["canary"].tools] == ["ping"]


_PROBE = """
import json, sys
from cogno_praxis.admin.service import AdminService
svc = AdminService()
svc.list_verticals()
for v in svc.known_ids():
    svc.get_vertical_config(v)
for extra in sys.argv[1:]:
    __import__(extra)
print(json.dumps(sorted(m for m in sys.modules if m.startswith("cogno_praxis"))))
"""


def _modules_after_reading(*extra: str) -> "list[str]":
    """The ``cogno_praxis`` modules a FRESH interpreter holds after reading every vertical.

    A subprocess, so nothing this test session imported earlier can hide or fake an import. Its
    environment carries no ``COGNO_*`` / ``PG*`` variable, so even a regression cannot connect.
    """
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COGNO", "PG"))}
    env["PYTHONPATH"] = str(PKG.parent)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    out = subprocess.run([sys.executable, "-c", _PROBE, *extra], env=env, capture_output=True,
                         text=True, timeout=60, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_reading_every_vertical_imports_no_other_vertical():
    loaded = _modules_after_reading()
    siblings = [v for v in AdminService().known_ids() if v != SELF_ID]
    assert {"scheduler", "bookkeeper", "coordinator", "companies"} <= set(siblings)
    imported = [m for m in loaded if len(m.split(".")) > 1 and m.split(".")[1] in siblings]
    assert imported == [], imported
    servers = [m for m in loaded if m.endswith(".server") and m != "cogno_praxis.admin.server"]
    assert servers == [], servers


def test_control_the_probe_sees_a_server_import():
    """The same probe, told to import the scheduler's server after reading: it must show it, or
    the empty list above would prove nothing."""
    loaded = _modules_after_reading("cogno_praxis.scheduler.server")
    assert "cogno_praxis.scheduler.server" in loaded


def test_the_planted_tree_is_read_statically(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = _plant(tmp_path)
    found = {v.id: v for v in discover_verticals(pkg, self_id="alpha")}
    # no __init__, _private, a plain lib: out
    assert set(found) == {"alpha", "broken", "canary"}
    alpha = found["alpha"]
    assert alpha.is_self and alpha.has_entry_point
    assert alpha.prompt_slots == ("voice", "extra")  # the four slots first, then the rest
    tools = {t.name: t for t in alpha.tools}
    assert list(tools) == ["renamed", "from_constant", "unresolved", "bare"]
    assert tools["renamed"].read_only and tools["renamed"].description == "Doc\nindented."
    assert tools["renamed"].input_schema == {
        "type": "object",
        "properties": {"a": {"annotation": "int", "type": "integer"},
                       "b": {"annotation": "list[str]"},
                       "c": {"annotation": "bool", "type": "boolean", "default": True}},
        "required": ["a", "b"]}
    assert tools["from_constant"].description == "shared text!"
    assert tools["unresolved"].description is None
    assert tools["unresolved"].description_resolved is False
    assert tools["bare"].annotations == {} and not tools["bare"].read_only
    assert tools["bare"].input_schema["properties"]["k"]["default"] == "v"


def test_a_server_that_does_not_parse_is_reported_never_an_empty_surface(tmp_path):
    pkg = _plant(tmp_path)
    broken = {v.id: v for v in discover_verticals(pkg)}["broken"]
    assert broken.has_server and broken.tools == ()
    assert broken.read_error and "could not be read" in broken.read_error
    row = {r["id"]: r for r in AdminService(pkg).list_verticals()}["broken"]
    assert "read_error" in row
    with pytest.raises(Exception):
        read_tool_surface(pkg / "broken" / "server.py", pkg)
