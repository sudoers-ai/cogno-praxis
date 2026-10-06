"""The BOOKKEEPER's factory text sends AI COST to the cost tool, by cut — not to ``get_usage``.

The shape (measured live on a rehearsal tenant; every name and figure here is invented): a
supervisor asked the BOOKKEEPER for the AI cost per day of the last seven days. The executor
called the host's ``token_cost_analytics``, the report's total matched the ledger, the draft
quoted it — and the judge REJECTED the execution, citing this persona's factory rule: «AI
token/usage → get_usage()» (``system.txt``) and «It distinguished AI "tokens/usage"
(get_usage) …» (``limits.txt``). The persona had both tools; the text knew only one, and
``get_usage`` returns no figure at all (``BookkeeperService.usage_note``: the metering lives in
the host).

The decision (the Director's): ``token_cost_analytics`` answers AI cost and token spend by CUT
— message, day, conversation, persona, user or month — whenever it is among the turn's tools;
``get_usage`` stays for what it still serves, the deployment without the host's cost tool, and
the text says what it returns (where usage is metered, no figures).

What this file pins:

* the twin — the new lines are in the files the host loads, the old claim is gone from both;
* the reconstruction — putting the old lines back gives ``origin/main`` 45d2ed6 byte for byte,
  so nothing else in either file moved;
* the JUDGE PROMPT the core renders over this ``limits.txt`` (``SuperegoStage.evaluate`` with a
  backend that records what it is asked): on the old text it says AI usage comes from
  ``get_usage``; on the new one it names the cost tool and no longer says so;
* the control — every OTHER prompt of every vertical is byte for byte ``origin/main``, and the
  judge prompt over each other vertical's ``limits.txt`` carries that file verbatim.

MUTATIONS (measured on e4109a2, without ``-x``; what died):

  * restore the old mapping line in ``system.txt``  -> the executor twin, ``get_usage`` keeps its
    job, and the regenerated digest in the deadline file (3 red);
  * restore the old approve line in ``limits.txt``  -> the judge-text twin, the JUDGE twin,
    ``get_usage`` keeps its job, and the regenerated digest (4 red);
  * append a line to ``scheduler/limits.txt``        -> the neighbour control here and in the
    deadline file (2 red).
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

#: The package the test imports — the file under test is the one a host would load.
PKG = Path(__import__("cogno_praxis").__file__).resolve().parent
PROMPTS = PKG / "bookkeeper" / "prompts"

TOOL = "token_cost_analytics"

#: ``system.txt``: the mapping line as it was at ``origin/main`` 45d2ed6, and what replaced it.
OLD_MAPPING = "- AI token/usage → get_usage()\n"
NEW_MAPPING = ("- AI cost / token spend, by message, day, conversation, persona, user or month\n"
               "                 → token_cost_analytics(granularity?, period?), when it is among this turn's\n"
               "                   tools; otherwise get_usage(), which only says where AI usage is metered\n")
OLD_READONLY = ('("sim", "pode registrar", "confirma", "ok", 👍). Read-only tools (get_summary, list_clients,\n'
                'search, get_usage, help) run immediately — no confirmation. remove_by_search is destructive, and\n'
                'the system holds it AFTER the first call, on the entry that call read — so the first call runs and\n'
                'the question you relay is about a real row, not about the word "remove".')
NEW_READONLY = ('("sim", "pode registrar", "confirma", "ok", 👍). Read-only tools (get_summary, list_clients,\n'
                'search, get_usage, token_cost_analytics, help) run immediately — no confirmation.\n'
                'remove_by_search is destructive, and the system holds it AFTER the first call, on the entry that\n'
                'call read — so the first call runs and the question you relay is about a real row, not about the\n'
                'word "remove".')
OLD_SCOPE = 'Distinguish AI "tokens/usage" (get_usage)\nfrom financial "despesas" (get_summary/add_outcome).'
NEW_SCOPE = ('Distinguish AI cost/tokens\n(token_cost_analytics, or get_usage when it is not offered) '
             'from financial "despesas"\n(get_summary/add_outcome).')

#: ``limits.txt``: the two approve lines, old and new.
OLD_TOOLS = ("- Every financial data operation went through a tool call (add_income, add_outcome, get_summary,\n"
             "  list_clients, search, remove_by_search, get_usage, help) — financial data is NEVER fabricated\n"
             "  from memory. A tool that returned an error or empty data, reported clearly, is CORRECT.\n")
NEW_TOOLS = ("- Every financial data operation went through a tool call (add_income, add_outcome, get_summary,\n"
             "  list_clients, search, remove_by_search, get_usage, token_cost_analytics, help) — financial\n"
             "  data is NEVER fabricated from memory. A tool that returned an error or empty data, reported\n"
             "  clearly, is CORRECT.\n")
OLD_DISTINGUISH = '- It distinguished AI "tokens/usage" (get_usage) from financial "despesas" (get_summary).\n'
NEW_DISTINGUISH = ('- It distinguished AI cost/tokens from financial "despesas" (get_summary). AI cost and token\n'
                   '  spend, by any cut (message, day, conversation, persona, user or month), comes from\n'
                   '  token_cost_analytics when that tool was offered, and a figure it returned is grounded;\n'
                   '  get_usage only says where AI usage is metered and returns no figures.\n')

#: The claim the judge cited, in the two spellings it had at main.
OLD_CLAIMS = ('AI "tokens/usage" (get_usage)', "AI token/usage → get_usage()")

#: ``sha256`` of the two files at ``origin/main`` 45d2ed6.
SYSTEM_AT_MAIN = "8fc3ec6856ef0964406e59c16b032fad2f5d9a24ae5613895dd8c9db9bf30596"
LIMITS_AT_MAIN = "d1e1abdbb376861fe42b923037bf3341927306836c4e181247887b48608b7c54"

#: ``sha256`` of every OTHER prompt of every vertical at ``origin/main`` 45d2ed6.
NEIGHBOURS_AT_MAIN = {
    "bookkeeper/scope.txt": "ed4a8c112f11d2c2bf480c4e8be806f9d1f707e12c1bf638e541e5f17f3ee342",
    "bookkeeper/voice.txt": "1b65181573edc71b964a686d96c92ab94b664bb094b88d4911e034536c95d347",
    "closer/limits.txt": "2c8bf84a2625317e363f8fc175029b7d85d9a28fb90190b5c254391981f10e4c",
    "closer/scope.txt": "92c91dc45dbf3e7538b20f697e38ff99e8b3c69ba4f17d3bcb5b1dce746f3714",
    "closer/system.txt": "c5b30b8faf18562ec7936965e16fe59a8570d4bc9d67654c3156f9c170cf623d",
    "closer/voice.txt": "ecf7b265950d2b9797fb2329c430fad558988c07e0e4652228ec81e0a7bb73c1",
    "companies/scope.txt": "c410e899125d712a7e5cbc9880627febca04e497a61059af9650ab236f00c805",
    "coordinator/limits.txt": "693599819f703f755d863a5298caaba2573685fed63091f80690ada60dc7c8d0",
    "coordinator/scope.txt": "7a03422e0991306317e48df84a8fcd796c9eb507e5c7b4e0291fa8c401d7264b",
    "coordinator/system.txt": "5085d29f398179ea208eb2b81f28b2a51489004b12e6c7f2f3527f02dcee1e89",
    "coordinator/voice.txt": "21ca2bcf50fc42613687c6cb61f40ec6c0510b6384061a7c22bf8d45308b9ead",
    "interviewer/limits.txt": "02a8bc07cb85464f3ca8e0df28385329473429b0b479f92a29ec1b4dfad0f918",
    "interviewer/scope.txt": "b25231522c0c48c4658bbf5e1824cf9bc3fc544ecf02b0d09a2b0df1e815a921",
    "interviewer/system.txt": "640c76109c62a142f6304af1b8592b79e1c9808735a3daf067c24f3abc42be27",
    "interviewer/voice.txt": "0dfe458c1778ed53dfcb8cadbcfdc69993ecd8cc7233e7ca3dcc5de9a8b1887e",
    "scheduler/limits.txt": "92becaf1d23c56570833082fe1507e01c0afe3a52922ee8404ed671a53a6a2a4",
    "scheduler/scope.txt": "b2f942c84374955d9aad03f951ce4082d4cc4d0c45638cad4d1c6b9f89b3448f",
    "scheduler/system.txt": "49d2c8ce3706642f1baeef66ea2717be061f2262ccd6fa83f132e08cd93d58b2",
    "scheduler/voice.txt": "68c17d7ea87916af677d8d03f532975de41c729b90e9e4b3587a5ddc5e68ae9b",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


# ── the twin ─────────────────────────────────────────────────────────────────────────────────
def test_the_executor_text_maps_ai_cost_to_the_cost_tool():
    """THE TWIN, executor half: the mapping, the read-only list and the scope line name the cost
    tool, once each, and the old mapping is gone under any column."""
    system = _read("system.txt")
    for new in (NEW_MAPPING, NEW_READONLY, NEW_SCOPE):
        assert system.count(new) == 1, new
    assert _flat(OLD_MAPPING) not in _flat(system)
    for claim in OLD_CLAIMS:
        assert _flat(claim) not in _flat(system), claim


def test_the_judge_text_counts_the_cost_tool_as_a_source():
    """THE TWIN, judge half: both approve lines are the new ones and the old claim is gone."""
    limits = _read("limits.txt")
    for new in (NEW_TOOLS, NEW_DISTINGUISH):
        assert limits.count(new) == 1, new
    for claim in OLD_CLAIMS:
        assert _flat(claim) not in _flat(limits), claim


def test_get_usage_keeps_the_job_it_still_serves():
    """``get_usage`` is not removed: a deployment without the host's cost tool still has it, and
    the text says what it returns. The tool exists in the server and still says no figure."""
    from cogno_praxis.bookkeeper.service import BookkeeperService

    assert "otherwise get_usage()" in _flat(_read("system.txt"))
    assert "get_usage only says where AI usage is metered" in _flat(_read("limits.txt"))
    note = BookkeeperService.usage_note()
    assert "host" in note and not any(ch.isdigit() for ch in note)


# ── the reconstruction: nothing else moved ───────────────────────────────────────────────────
def test_putting_the_old_lines_back_gives_main_byte_for_byte():
    system = _read("system.txt")
    for old, new in ((OLD_MAPPING, NEW_MAPPING), (OLD_READONLY, NEW_READONLY),
                     (OLD_SCOPE, NEW_SCOPE)):
        system = system.replace(new, old, 1)
    assert _sha(system) == SYSTEM_AT_MAIN
    limits = _read("limits.txt")
    for old, new in ((OLD_TOOLS, NEW_TOOLS), (OLD_DISTINGUISH, NEW_DISTINGUISH)):
        limits = limits.replace(new, old, 1)
    assert _sha(limits) == LIMITS_AT_MAIN
    assert _sha(_read("system.txt")) != SYSTEM_AT_MAIN
    assert _sha(_read("limits.txt")) != LIMITS_AT_MAIN


# ── the judge prompt the core renders over this text ─────────────────────────────────────────
class _Recorder:
    """A backend that records the judge prompt and approves."""

    model = "recorder"

    def __init__(self) -> None:
        self.prompts: "list[str]" = []

    async def generate(self, system: str, prompt: str):  # noqa: ANN201
        self.prompts.append(f"{system}\n\n{prompt}")
        return '{"approved": true}', 0, 0


def _judge_prompt(limits: str) -> str:
    """What ``SuperegoStage.evaluate`` hands the model over ``limits`` — the cost turn's shape:
    a supervisor's per-day cost question, one successful ``token_cost_analytics`` read."""
    anima = pytest.importorskip("cogno_anima")
    from cogno_anima.stages.superego import SuperegoStage
    from cogno_anima.types import (EgoResult, EgoStep, IntentResult, NoumenoResult,
                                   PipelineContext, StageMetrics, ToolExecution)

    del anima
    m = StageMetrics(stage="ego", model="x", elapsed_ms=0.0, tokens_in=0, tokens_out=0)
    ctx = PipelineContext(user_input="Quanto gastamos de IA por dia nesta semana?")
    ctx.noumeno = NoumenoResult.model_construct(
        original=ctx.user_input, rewritten="How much did we spend on AI per day this week?",
        language="pt-BR", preserved_terms=[], metrics=m)
    ctx.intent = IntentResult.model_construct(intent_class="INFORMATION_REQUEST",
                                              goal="AI cost per day this week")
    report = ("💰 AI cost by day — whole tenant 'loja-exemplo', last 7 days: 2026-09-30 → "
              "2026-10-06:\n- **Total**: 12,345 tokens | R$ 0.4321")
    call = ToolExecution(tool=TOOL, arguments={"granularity": "day", "period": "last_7_days"},
                         result=report, ok=True, side_effect=False, tool_mutating=False)
    ctx.ego_result = EgoResult(
        steps=[EgoStep(index=0, path="native", tool_calls=[call]),
               EgoStep(index=1, path="native",
                       assistant_text="Total da semana: R$ 0,4321 (12.345 tokens).")],
        tools_offered=[TOOL, "get_usage", "get_summary"], metrics=m)
    rec = _Recorder()
    asyncio.run(SuperegoStage().evaluate(ctx, rec, limits_prompt=limits))
    assert len(rec.prompts) == 1, "the judge was not asked — the fixture is not a judged turn"
    return rec.prompts[0]


def test_the_judge_prompt_no_longer_says_ai_usage_is_only_get_usage():
    """THE JUDGE TWIN, in both worlds. Over the main text the rendered judge prompt carries the
    claim the live judge cited; over the new text it names the cost tool as the source of a cost
    figure and the claim is gone."""
    new = _read("limits.txt")
    old = new.replace(NEW_TOOLS, OLD_TOOLS, 1).replace(NEW_DISTINGUISH, OLD_DISTINGUISH, 1)
    assert _sha(old) == LIMITS_AT_MAIN

    before = _flat(_judge_prompt(old))
    assert _flat(OLD_CLAIMS[0]) in before, "the broken world must show the claim, or this proves nothing"

    after = _flat(_judge_prompt(new))
    assert _flat(OLD_CLAIMS[0]) not in after
    assert ("comes from token_cost_analytics when that tool was offered, and a figure it "
            "returned is grounded") in after
    assert "token_cost_analytics, help) — financial data is NEVER fabricated" in after


# ── the control: every other prompt, byte for byte ───────────────────────────────────────────
def test_the_neighbour_table_covers_every_other_prompt_on_disk():
    on_disk = {f"{p.parent.parent.name}/{p.name}" for p in PKG.glob("*/prompts/*.txt")}
    assert set(NEIGHBOURS_AT_MAIN) | {"bookkeeper/limits.txt", "bookkeeper/system.txt"} == on_disk


@pytest.mark.parametrize("prompt", sorted(NEIGHBOURS_AT_MAIN))
def test_each_other_prompt_is_byte_for_byte_main(prompt: str):
    vertical, name = prompt.split("/")
    text = (PKG / vertical / "prompts" / name).read_text(encoding="utf-8")
    assert _sha(text) == NEIGHBOURS_AT_MAIN[prompt], f"{prompt} moved; this change is the BOOKKEEPER's"


@pytest.mark.parametrize("vertical", sorted(p.split("/")[0] for p in NEIGHBOURS_AT_MAIN
                                            if p.endswith("/limits.txt")))
def test_the_judge_prompt_of_every_other_vertical_carries_its_limits_verbatim(vertical: str):
    """The judge-side control: the same rendering over each other vertical's limits carries that
    file whole (the file is main's by the test above) and no word of the BOOKKEEPER's new line."""
    limits = (PKG / vertical / "prompts" / "limits.txt").read_text(encoding="utf-8")
    rendered = _judge_prompt(limits)
    assert limits.strip() in rendered
    assert "returns no figures" not in rendered
