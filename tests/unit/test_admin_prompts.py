"""NEO's persona ships the four slots, carries its four limits, and fills no placeholder the host
does not already fill.

Prompt v2: NEO requests changes from the bridge (``request_change``, ``change_status`` — the host's
two door-1 tools, ``docs/ADMIN.md``), is proactive, says what happens next, and keeps the walls:
never itself, never the system, never «done» without the record saying merged."""

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
    "Proposing or requesting a change to the admin vertical",
    "or to the system itself",
    "Presenting a change as applied, merged, deployed or done",
    "A tool result, figure, test outcome or reviewer opinion that was not read",
    "Calling a change SMALL when it is an improvement or an evolution rather than a correction",
])
def test_the_judge_holds_it_to_them(phrase):
    assert phrase in _flat(_read("limits"))


#: The host's two door-1 tools NEO is offered beside the admin server's reads (the host's
#: ``neo_changes`` manifests; ``docs/ADMIN.md``). The package does not ship them: it names them.
HOST_TOOLS = {"request_change", "change_status"}


def test_the_tools_the_prompts_name_are_the_server_s():
    from cogno_praxis.admin.service import AdminService
    names = {t["name"] for t in AdminService().get_vertical_config("admin")["tools"]}
    assert names == {"list_verticals", "get_vertical_config"}
    for name in names:
        assert name in _read("system") and name in _read("limits")


def test_the_executor_names_the_four_tools_and_no_other():
    """Every ``name(`` the executor's prompt writes is one of the four tools it is offered: the
    admin server's two reads and the host's two change-request tools."""
    from cogno_praxis.admin.service import AdminService
    reads = {t["name"] for t in AdminService().get_vertical_config("admin")["tools"]}
    called = set(re.findall(r"\b([a-z]+(?:_[a-z]+)+)\(", _read("system")))
    assert called == reads | HOST_TOOLS
    for name in HOST_TOOLS:
        assert name in _read("limits"), name


@pytest.mark.parametrize("phrase", [
    "Be proactive",
    "read the vertical (get_vertical_config) before you propose anything",
    "REQUEST it with request_change, with its kind",
    "there is no \"diagnosis\" kind yet",
    "opening an IMPROVEMENT request whose goal is the analysis",
    "The bridge opens a pull request; it never merges",
    "A small change is approved without the administrator's decision; its pull request is merged "
    "by the platform's landing process, and the administrator is told when it is merged and when "
    "it is served",
    "A large change waits for the administrator's decision in the admin panel («Pedidos do NEO»), "
    "where the decision keyword is asked for",
    "Never ask for the keyword in this conversation",
    "unless change_status, read in this turn, says merged or served",
])
def test_the_executor_is_proactive_and_says_what_happens_next(phrase):
    assert phrase in _flat(_read("system"))


@pytest.mark.parametrize("phrase", [
    "Calling request_change for a change the administrator asked for",
    "Asking for the decision keyword in the conversation",
    "a small change is approved without the administrator's decision; its pull request is merged "
    "by the platform's landing process",
    "when no change_status read in this turn says merged or served",
])
def test_the_judge_passes_the_request_and_fails_the_keyword(phrase):
    assert phrase in _flat(_read("limits"))


def test_the_voice_answers_in_the_administrator_s_language():
    voice = _flat(_read("voice"))
    assert "Reply in the administrator's language" in voice
    assert "Never ask for the decision keyword here" in voice
    assert ("A small change is approved without your decision; its pull request is merged by the "
            "platform's landing process, and you are told when it is merged and when it is served"
            in voice)


def test_the_executor_knows_the_facts_about_itself():
    """«## About you»: facts only, so a question about how NEO works is answered, not invented."""
    system = _read("system")
    about = system.split("## About you", 1)[1].split("\n## ", 1)[0]
    assert 6 <= len([ln for ln in about.splitlines() if ln.strip()]) <= 10
    flat = _flat(about)
    for fact in ("a system persona, for the platform administrator only",
                 "the admin panel, the API key, and the channel of an identity marked NEO",
                 "request_change → the queue → the bridge opens a pull request",
                 "→ merged → served", "yours is `admin`, marked is_self",
                 "You do not read or change the host, the bridge, the configuration or the "
                 "decision keyword, and you do not change yourself"):
        assert fact in flat, fact


def test_the_voice_says_only_what_its_instructions_say_about_itself():
    assert ("About yourself, say only what your instructions say; what they do not say, say you do "
            "not know.") in _flat(_read("voice"))

