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

#: ``system.txt``: the confirmation section as 37b07df left it, and as the CALL convention
#: rewrote it (2026-10-14, ``test_the_bookkeeper_calls_the_write.py``). It swallowed the head of
#: ``NEW_READONLY``, so the reconstruction undoes that LATER edit first, and the twin below reads
#: the read-only list flattened.
ASKED_SECTION = (    '## Confirmation Before Recording\n'
    'Before recording an income or expense, present a brief summary (description, amount, client if\n'
    'any) and ask the user to confirm; call add_income/add_outcome ONLY after an explicit affirmative\n'
    '("sim", "pode registrar", "confirma", "ok", 👍). Read-only tools (get_summary, list_clients,\n'
    'search, get_usage, token_cost_analytics, help) run immediately — no confirmation.\n')
CALL_SECTION = (    "## Confirmation is the SYSTEM's job — CALL the tool, never negotiate it in prose\n"
    'To record an income or expense, CALL add_income/add_outcome with what the user gave you. The\n'
    'SYSTEM holds the call, shows the user what will be recorded and asks them to confirm — so do NOT\n'
    'write "posso registrar?", "confirma?" or any other confirmation question in your reply. Asking in\n'
    'prose WITHOUT calling the tool leaves nothing for the system to confirm, and the user has to say\n'
    'yes twice.\n'
    '- The user told you of an entry or asked you to record one, amount included → call the tool now.\n'
    '- The amount, or what the entry was for, is missing → ask for THAT detail and call nothing yet.\n'
    '- The user is ASKING about an entry, not making one ("quanto ficaria se eu lançasse…?", "posso\n'
    '  lançar depois?") → answer the question; call no write tool.\n'
    '- The user replied "sim" / "pode registrar" / "isso" to an entry you were about to record → that\n'
    '  reply IS the go-ahead: call the tool now, never answer it with another question.\n'
    'Read-only tools (get_summary, list_clients, search, get_usage, token_cost_analytics, help) run\n'
    'immediately — no confirmation.\n')

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

#: Request 66a0acf2 (2026-11-04) widened the two lines again — week and model, the split by model,
#: the "Not available" answer — on top of the B4b text above. The twins read the CURRENT lines;
#: the reconstruction undoes them first (``tests/unit/test_bookkeeper_ai_cost_by_week_and_model.py``).
CUR_MAPPING = ("- AI cost / token spend, by message, day, week, month, conversation, persona, user or model\n"
               "                 → token_cost_analytics(granularity?, period?, dimension?, by?), when it is among\n"
               "                   this turn's tools; by=\"model\" splits a day/week/month cut by model (a series\n"
               "                   per model). A cut it does not carry (per client, per expense category) comes\n"
               "                   back \"Not available\": say so, never rebuild it from the books. Otherwise\n"
               "                   get_usage(), which says the AI-cost report is not on this turn — no figures\n")
CUR_DISTINGUISH = ('- It distinguished AI cost/tokens from financial "despesas" (get_summary). AI cost and token\n'
                   '  spend, by any cut (message, day, week, month, conversation, persona, user or model, and a\n'
                   '  time cut split by model), comes from token_cost_analytics when that tool was offered, and a\n'
                   '  figure it returned is grounded; its "Not available" for a cut it does not carry, reported as\n'
                   '  such, is CORRECT; get_usage only says the AI-cost report is not on this turn and returns no\n'
                   '  figures.\n')

#: The claim the judge cited, in the two spellings it had at main.
OLD_CLAIMS = ('AI "tokens/usage" (get_usage)', "AI token/usage → get_usage()")

#: ``sha256`` of the two files at ``origin/main`` 45d2ed6.
SYSTEM_AT_MAIN = "8fc3ec6856ef0964406e59c16b032fad2f5d9a24ae5613895dd8c9db9bf30596"
LIMITS_AT_MAIN = "d1e1abdbb376861fe42b923037bf3341927306836c4e181247887b48608b7c54"

#: ``sha256`` of every OTHER prompt of every vertical at ``origin/main`` 45d2ed6 — plus the
#: ``admin/*`` slots (NEO), which arrived after it and are pinned at the commit that last changed
#: them on purpose: NEO's prompt v2 (change requests to the bridge).
NEIGHBOURS_AT_MAIN = {
    # all four admin slots regenerated deliberately: NEO answers a state summary with one
    # neo_system_summary read instead of the eight separate reads (neo_tenant_logs is named as the
    # audit trail, not an error log); the voice uses the summary's operation words with no internal
    # name; the scope allows the platform's operation and blocks the business's own matters; the
    # judge accepts a summary with its total in view and reads the AI cost as operation, not
    # finance — not the bookkeeper's
    "admin/limits.txt": "344a8403a2a81ed43b8eee1ea5abcafd7c04e1e945e58d183b002edb90c7e2bf",
    "admin/scope.txt": "52cbd68e35ebabe35c72161bf15ee472ad55fc38013c4b91e82649f526c8ac12",
    "admin/system.txt": "f6489a99a54039616830c01769d69b061b67d49609f849e8704d46afff21409c",
    "admin/voice.txt": "200bd3ecec05c057d23dbb3cd9172b70cb3c4f54e42b685567f6d21e69feee1c",
    "bookkeeper/scope.txt": "ed4a8c112f11d2c2bf480c4e8be806f9d1f707e12c1bf638e541e5f17f3ee342",
    # bookkeeper voice regenerated 2026-11-04: pt-BR marks in a Portuguese reply, never rounded
    "bookkeeper/voice.txt": "4360356043abd08b2edc375cf5d288aa0485009fe33c01c71e625e8b7be77f40",
    # closer/system.txt, closer/limits.txt and closer/voice.txt regenerated deliberately: the
    # seller's product knowledge now comes from the company's published DOCUMENTS, read this turn
    # with consult_documents, instead of a fixed product block — the executor, the judge and the
    # voicer all point at the documents. Only closer/scope.txt did not move. closer/system.txt
    # regenerated again, deliberately: the prompt now says WHEN to read the documents — at the
    # insight and the close, never during the diagnosis (limits.txt and voice.txt did not move).
    "closer/limits.txt": "a77a03ebe45a686c7b6d4df93f1400fa8f7942a8cfd213912aab08505dab69c5",
    "closer/scope.txt": "92c91dc45dbf3e7538b20f697e38ff99e8b3c69ba4f17d3bcb5b1dce746f3714",
    "closer/system.txt": "421c9c52560b9122757b7172f4e7e272a1fe116e3ee08882c3f9b128ed672c98",
    "closer/voice.txt": "59399234ad61341d54ffa76e4e86fefc3d037b96f67b735300aed9255c9c809d",
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
    # scheduler/system.txt: regenerated deliberately — a `{{SERVICES_CATALOG}}` host block was
    # added (the catalog step, filled host-side; empty renders byte-for-byte as before).
    "scheduler/system.txt": "4e00df4ee46cade9c804e2132ba6c74263dc611f19928a5eaf186ed434a92372",
    # scheduler/voice.txt: regenerated 2026-11-12, deliberately — the voice examples no longer
    # lend the reply a name, a title or a gender («a Dra. Silva» → «a profissional»).
    "scheduler/voice.txt": "b420762b7ac5f045503299c204ab63420033be450246f35e7a505541170b2d5e",
    # the three commercial personas — their slots are neighbours of the bookkeeper change (they
    # did not move it, it did not move them). system.txt and voice.txt of all three were
    # regenerated deliberately in the commercial-prompts change (capability-directed rewrite);
    # limits.txt and scope.txt stay byte-for-byte.
    # sdr/system.txt regenerated again, deliberately: the triage «problema que resolve» bullet now
    # names the HIRING company's problem, grounded in the documents it published, instead of a
    # fixed, built-in product pain — the SDR serves ANY company (test_sdr_prompts.py).
    # and the handoff «when it cannot pass» fallback no longer promises the team reaches out — it
    # forbids promising any action (contact, send, schedule, pass a message) without a tool that
    # performs it (test_sdr_prompts.py).
    "sdr/system.txt": "4514914c92e4188002a616b93264280ed3fd66323ad4b2929f26d5a0698aeb6f",
    "sdr/limits.txt": "c90e7bef43fe80f7ced5a92e8d80eb1753ee79b7af7b6130fc55e10fffc55ebd",
    "sdr/voice.txt": "8b0ff211c5c7c583ee21939bfb47216048ab51d6b1a6bf4753e882abd62c1d71",
    "sdr/scope.txt": "59606ef1b8665f94a40663f0dca7b7abec96e0ffe0b35696e3996d0a8551a495",
    # seller/system.txt regenerated again, deliberately: the same handoff fallback no longer
    # promises the team reaches out — it forbids promising an action with no tool that performs it.
    "seller/system.txt": "1691973b8675480fbf40d44c7ce7cfd6062d3099135b6ed8d9b424df8f17c3fb",
    "seller/limits.txt": "80f50734e11c67214e816cde43cd0ad86f83ec78591b2c1d05d62becb59f69af",
    "seller/voice.txt": "e1a9ff13f705c3af5c15d7143bb32d695b78fd5b7c870ebfda8c5566b5ce7394",
    "seller/scope.txt": "4f46f8016911d07af608eaa4be23c315474525443aa44abf977d8c9b7f4713bf",
    # aftersales/system, /limits and /voice regenerated again, deliberately: the satisfaction
    # check's example answers no longer cite a busy-morning workload (the product's own pain); the
    # closed question and the short-answer examples are business-neutral and identical across the
    # three slots (test_aftersales_prompts.py). aftersales/scope stays byte-for-byte.
    # aftersales/system.txt regenerated again, deliberately: the same handoff fallback no longer
    # promises the team reaches out (it forbids promising an action with no tool), and the «new
    # opportunity» clause no longer does sale discovery — it offers the seller instead of asking
    # what the customer wants to buy.
    # aftersales/system.txt and /voice.txt regenerated again, deliberately: satisfaction is now
    # measured IN TEXT only (the «use a poll tool if present» directive is gone — the persona has
    # none); and the new-opportunity fallback, with no tool to pass the conversation, says plainly
    # it cannot do that here and keeps helping — it no longer asks whether to forward nor promises
    # someone will contact the customer (test_aftersales_prompts.py). limits and scope stay.
    "aftersales/system.txt": "c009029f4b44c4c511d6015b319562590818b9a8b82adacd965b334960ed874a",
    "aftersales/limits.txt": "ac6ff5085a8c0de7c5b2da55f4e9994d01e31a50bcf38fe4bb91831a16bf6a74",
    "aftersales/voice.txt": "922316697153d8783bce4bb015d1095ae3d0fad7783fea785d2a4443a8d89c02",
    "aftersales/scope.txt": "dd79da1fd8cd14d32c234f8ed930433d96af8dc073be4d01118bf43bc6e1833d",
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
    for new in (CUR_MAPPING, NEW_SCOPE):
        assert system.count(new) == 1, new
    assert ("Read-only tools (get_summary, list_clients, search, get_usage, token_cost_analytics, "
            "help) run immediately") in _flat(system)
    assert _flat(OLD_MAPPING) not in _flat(system)
    for claim in OLD_CLAIMS:
        assert _flat(claim) not in _flat(system), claim


def test_the_judge_text_counts_the_cost_tool_as_a_source():
    """THE TWIN, judge half: both approve lines are the new ones and the old claim is gone."""
    limits = _read("limits.txt")
    for new in (NEW_TOOLS, CUR_DISTINGUISH):
        assert limits.count(new) == 1, new
    for claim in OLD_CLAIMS:
        assert _flat(claim) not in _flat(limits), claim


def test_get_usage_keeps_the_job_it_still_serves():
    """``get_usage`` is not removed: a deployment without the host's cost tool still has it, and
    the text says what it returns. The tool exists in the server and still says no figure."""
    from cogno_praxis.bookkeeper.service import BookkeeperService

    assert "Otherwise get_usage()" in _flat(_read("system.txt"))
    assert "get_usage only says the AI-cost report is not on this turn" in _flat(_read("limits.txt"))
    note = BookkeeperService.usage_note()
    assert "host" in note and not any(ch.isdigit() for ch in note)


# ── the reconstruction: nothing else moved ───────────────────────────────────────────────────
def test_putting_the_old_lines_back_gives_main_byte_for_byte():
    system = _read("system.txt")
    assert system.count(CALL_SECTION) == 1
    system = system.replace(CALL_SECTION, ASKED_SECTION, 1)
    assert system.count(CUR_MAPPING) == 1
    system = system.replace(CUR_MAPPING, NEW_MAPPING, 1)          # 66a0acf2 undone first
    for old, new in ((OLD_MAPPING, NEW_MAPPING), (OLD_READONLY, NEW_READONLY),
                     (OLD_SCOPE, NEW_SCOPE)):
        system = system.replace(new, old, 1)
    assert _sha(system) == SYSTEM_AT_MAIN
    limits = _read("limits.txt")
    assert limits.count(CUR_DISTINGUISH) == 1
    limits = limits.replace(CUR_DISTINGUISH, NEW_DISTINGUISH, 1)  # 66a0acf2 undone first
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
    old = (new.replace(CUR_DISTINGUISH, NEW_DISTINGUISH, 1).replace(NEW_TOOLS, OLD_TOOLS, 1)
           .replace(NEW_DISTINGUISH, OLD_DISTINGUISH, 1))
    assert _sha(old) == LIMITS_AT_MAIN

    before = _flat(_judge_prompt(old))
    assert _flat(OLD_CLAIMS[0]) in before, "the broken world must show the claim, or this proves nothing"

    after = _flat(_judge_prompt(new))
    assert _flat(OLD_CLAIMS[0]) not in after
    assert ("comes from token_cost_analytics when that tool was offered, and a figure it "
            "returned is grounded") in after
    assert 'its "Not available" for a cut it does not carry, reported as such, is CORRECT' in after
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
