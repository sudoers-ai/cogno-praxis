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
#: …and the host's READ tools (NEO's dynamic reads): offered where the platform switches them on
#: (``COGNO_NEO_READS``), never shipped here. The executor names them for what is happening NOW —
#: the state summary (``neo_system_summary``) and the three detail reads; the judge's limits do not
#: need to.
HOST_READ_TOOLS = {"neo_system_summary", "panel_read", "neo_tenant_logs", "neo_token_costs"}


def test_the_tools_the_prompts_name_are_the_server_s():
    from cogno_praxis.admin.service import AdminService
    names = {t["name"] for t in AdminService().get_vertical_config("admin")["tools"]}
    assert names == {"list_verticals", "get_vertical_config"}
    for name in names:
        assert name in _read("system") and name in _read("limits")


def test_the_executor_names_the_four_tools_and_no_other():
    """Every tool the executor's prompt writes — as ``name(`` or in `backticks` — is one it is
    offered: the admin server's two reads, the host's two change-request tools, and the host's
    dynamic reads (the state summary ``neo_system_summary`` and the three detail reads)."""
    from cogno_praxis.admin.service import AdminService
    reads = {t["name"] for t in AdminService().get_vertical_config("admin")["tools"]}
    system = _read("system")
    called = set(re.findall(r"\b([a-z]+(?:_[a-z]+)+)\(", system))
    backticked = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", system))
    assert called | backticked == reads | HOST_TOOLS | HOST_READ_TOOLS
    for name in HOST_TOOLS:
        assert name in _read("limits"), name


@pytest.mark.parametrize("phrase", [
    "Be proactive",
    "read the vertical (get_vertical_config) before you propose anything",
    "REQUEST it with request_change, with its kind",
    "there is no \"diagnosis\" kind yet",
    "opening an IMPROVEMENT request whose goal is the analysis",
    "The bridge opens a pull request; it never merges",
    "A small change is approved at review, without the decision keyword (it still shows in «Pedidos "
    "do NEO»); its pull request is merged by the platform's landing process, and the administrator "
    "is told when it is merged.",
    "Your tools are offered only where the platform switches them on. When they are not offered in "
    "this turn (the API key, "
    "a channel, or the feature switched off), say you cannot read or request from here and point to "
    "the admin panel; never describe a vertical or a request from memory.",
    "the dependencies or the admin code; when it creates a file a capability is made of (a "
    "vertical's __init__.py or server.py, a new prompts/*.txt)",
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
    "a small change is approved at review, without the decision keyword (it still shows in «Pedidos "
    "do NEO»); its pull request is merged by the platform's landing process, and the administrator "
    "is told when it is merged.",
    "saying it cannot read or request from here and pointing to the admin panel",
    "when no change_status read in this turn says merged or served",
])
def test_the_judge_passes_the_request_and_fails_the_keyword(phrase):
    assert phrase in _flat(_read("limits"))


def test_the_voice_answers_in_the_administrator_s_language():
    voice = _flat(_read("voice"))
    assert "Reply in the administrator's language" in voice
    assert "Never ask for the decision keyword here" in voice
    assert ("A small change is approved at review, without the decision keyword (it still shows in "
            "«Pedidos do NEO»); its pull request is merged by the platform's landing process, and you "
            "are told when it is merged." in voice)
    assert "say you cannot read or request from here and point to the admin panel" in voice


def test_the_executor_knows_the_facts_about_itself():
    """«## About you»: facts only, so a question about how NEO works is answered, not invented."""
    system = _read("system")
    about = system.split("## About you", 1)[1].split("\n## ", 1)[0]
    assert 6 <= len([ln for ln in about.splitlines() if ln.strip()]) <= 10
    flat = _flat(about)
    for fact in ("a system persona, for the platform administrator only",
                 "the admin panel, the API key, and the channel of an identity marked NEO",
                 "marked NEO alone, the whole channel",
                 "request_change → the queue → the bridge opens a pull request",
                 "with the decision keyword → merged. Serving it is the platform's, and nobody is told.",
                 "yours is `admin`, marked is_self",
                 "You do not read or change the host, the bridge, the configuration or the "
                 "decision keyword, and you do not change yourself"):
        assert fact in flat, fact


def test_the_voice_says_only_what_its_instructions_say_about_itself():
    assert ("About yourself, say only what your instructions say; what they do not say, say you do "
            "not know.") in _flat(_read("voice"))


@pytest.mark.parametrize("slot", ["system", "limits", "voice"])
def test_nobody_is_promised_a_notice_when_a_change_is_served(slot):
    """The host moves nothing to served and tells nobody: the prompts promise the merge only."""
    assert "when it is served" not in _flat(_read(slot))




# ── the owner (2026-11-04): what is happening NOW, by default; the fixed configuration on request ──
@pytest.mark.parametrize("phrase", [
    "Read what is happening NOW — by default",
    "The administrator wants the platform's DYNAMIC, RECENT state, not its fixed configuration",
    "For a STATE SUMMARY",
    "call `neo_system_summary` ONCE",
    "today's outcomes by reason and the failures by skill",
    "Use a DETAIL read (a `panel_read` view, `neo_token_costs`, `neo_tenant_logs`) only when the "
    "administrator asks about ONE aspect",
    "A part the summary marks as not read is reported as not read, never filled in",
    "`neo_tenant_logs` is the platform's AUDIT TRAIL (who did what), not an error log",
    "is read ONLY when the administrator asks for it explicitly",
    "Never answer a question about the state with the inventory",
])
def test_the_executor_reads_the_dynamic_state_by_default(phrase):
    """The owner on an «overview» answered with a table of verticals: «não quero saber de coisas
    fixas, e sim de coisas dinâmicas». The DEFAULT is what is happening; the inventory only when
    asked. For a state summary it reads once (``neo_system_summary``); the eight separate reads are
    gone and the detail reads are for one aspect."""
    assert phrase in _flat(_read("system"))


@pytest.mark.parametrize("gone", [
    'panel_read(view="served")', 'panel_read(view="channels")', 'panel_read(view="oauth_status")',
    'panel_read(view="outcomes")', 'neo_token_costs(period="today")',
    "neo_tenant_logs(period_hours=24)", "judge_exhausted and scope_blocked",
    "recent errors and warnings",
])
def test_the_eight_separate_reads_are_gone(gone):
    """The list of eight reads a state summary used to make, one by one, is replaced by the single
    ``neo_system_summary`` read."""
    assert gone not in _flat(_read("system"))


def test_the_dynamic_reads_come_before_the_tool_usage_rules():
    system = _read("system")
    assert system.index("Read what is happening NOW") < system.index("## Mandatory tool usage")


@pytest.mark.parametrize("phrase", [
    "In a chat channel — Telegram, WhatsApp — NEVER a table",
    "a markdown table shows there as raw pipes",
    "At most about 12 lines: the numbers first; mark ONLY what changed or is wrong with ⚠️;",
    "end EVERY such list with «Quer o detalhe de algum?».",
])
def test_the_voice_never_draws_a_table_in_a_chat(phrase):
    assert phrase in _flat(_read("voice"))



@pytest.mark.parametrize("phrase", [
    "Numbers come in the system's format, pt-BR — never the English one",
    "a decimal comma and a thousands dot, keeping every decimal the data carries and NEVER "
    "rounding",
    "(«R$ 2,5832», never «R$ 2.5832»; «4.354.192», never «4,354,192»)",
])
def test_the_voice_writes_numbers_in_pt_br(phrase):
    """The owner (2026-11-04): «os números precisam vir no formato do sistema, registado na UI,
    que é pt-br» — NEO had written «R$ 2.5832» and «4,354,192 tokens». Only the MARKS change:
    the core calls a rounded figure invented (anima's ``_FIGURES_HAVE_A_SOURCE`` and the
    divergence net), so the rule keeps every decimal the data carries."""
    assert phrase in _flat(_read("voice"))


# ── a state summary: the voice, the scope and the judge ──────────────────────────────────────
def test_the_voice_quotes_exactly_only_for_a_change_request():
    """The quote-exactly rule holds for a change request; a state summary uses the summary's own
    operation words, never an internal name — so the reads' field, class, net and digest names do
    not reach the reply."""
    voice = _flat(_read("voice"))
    assert ("Quote prompt texts, tool names, descriptions and annotations exactly as the tools "
            "returned them — never paraphrase a text you are proposing to change, never alter a "
            "name — for a change request.") in voice
    assert ("In a STATE SUMMARY, use the summary's own operation words and never an internal "
            "field, class, net or digest name.") in voice


def test_the_scope_allows_the_platform_operation_and_blocks_the_business():
    """The platform's OPERATIONAL state is in scope (a vague question, «bring what you can», asking
    for NEO); the business's own matters are out — that is the business personas' work."""
    scope = _flat(_read("scope"))
    allow = scope.split("IN SCOPE (ALLOW):", 1)[1].split("OUT OF SCOPE (BLOCK):", 1)[0]
    block = scope.split("OUT OF SCOPE (BLOCK):", 1)[1]
    assert ("The platform's OPERATIONAL state: how the system is, what happened today, errors, "
            "costs and AI usage, the channels — including a vague question about it or a request "
            "to bring whatever can be read, and a request to talk to NEO.") in allow
    assert ("The business's own matters — its sales, its customers, its finances: that is the "
            "business personas' work.") in block


def test_the_judge_accepts_a_state_summary_and_reads_ai_cost_as_operation():
    """A summary with its total in view is correct, a part marked not read is said as not read and
    not a fault, and the platform's AI cost is operation, never rejected as the business's
    finances."""
    assert ("A state summary is CORRECT when each figure is the summary's, with its total in view, "
            "and a part marked not read is said as not read — never a fault. The platform's AI "
            "cost is the platform's OPERATION, not the business's finances: never reject it as a "
            "finance answer.") in _flat(_read("limits"))
