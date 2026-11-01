"""NEO's persona ships the four slots, carries its four limits, and fills no placeholder the host
does not already fill."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROMPTS = Path(__import__("cogno_praxis.admin", fromlist=["x"]).__file__).resolve().parent / "prompts"
_SLOTS = ("system", "scope", "limits", "voice")


def _read(slot: str) -> str:
    return (PROMPTS / f"{slot}.txt").read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_four_slots_and_nothing_else():
    assert sorted(p.stem for p in PROMPTS.glob("*.txt")) == sorted(_SLOTS)


@pytest.mark.parametrize("slot", _SLOTS)
def test_no_placeholder_at_all(slot):
    """NEO is not a tenant's persona: none of the host's tenant/identity placeholders applies, and
    inventing one would leave a literal the host never fills."""
    assert not re.search(r"\{\{?[A-Za-z_]+\}?\}", _read(slot)), slot


def test_the_scope_is_the_verticals_skills_and_the_administrator_only():
    scope = _flat(_read("scope"))
    assert "platform administrator only" in scope
    assert "Proposing improvements" in scope
    block = scope.split("OUT OF SCOPE (BLOCK):", 1)[1]
    assert "Changing the system itself" in block
    assert "Changes to the admin vertical itself" in block


@pytest.mark.parametrize("phrase", [
    "never change the system itself",                       # only the verticals' skills
    "never propose a change to your own vertical, `admin`",  # its own vertical
    "A large change waits for the administrator's decision",
    "never invent a tool result",
    "only a correction can be small",
])
def test_the_executor_carries_the_four_limits(phrase):
    assert phrase in _flat(_read("system"))


@pytest.mark.parametrize("phrase", [
    "Proposing a change to the admin vertical",
    "or to the system itself",
    "Presenting a change as applied, merged, deployed or done",
    "A tool result, figure, test outcome or reviewer opinion that was not read",
    "Calling a change SMALL when it is an improvement or an evolution rather than a correction",
])
def test_the_judge_holds_it_to_them(phrase):
    assert phrase in _flat(_read("limits"))


def test_the_tools_the_prompts_name_are_the_server_s():
    from cogno_praxis.admin.service import AdminService
    names = {t["name"] for t in AdminService().get_vertical_config("admin")["tools"]}
    assert names == {"list_verticals", "get_vertical_config"}
    for name in names:
        assert name in _read("system") and name in _read("limits")
