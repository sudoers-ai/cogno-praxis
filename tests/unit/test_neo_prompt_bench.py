"""NEO's prompt bench (``scripts/neo_prompt_bench.py``): the meter, before it measures a model.

* the grader tells a good transcript from a broken one on every criterion (the twins);
* the two CONTROL cases (its own vertical, a plain question) score a request as a failure;
* the size comes from ``impact.classify``, never a copy of the rule;
* the language of a reply is read without a dependency;
* the rubric reads the four slots: all five criteria are instructed today, and removing one
  sentence turns its criterion off;
* the cloud half: no key → refused (and the key is never printed); the preflight sends nothing and
  writes nothing; the ledger line is written BEFORE the first call and the cost line after the
  last; over the ceiling it stops and says so; a held ``request_change`` ends the loop.

Pure: no network (the transport is injected), no model.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("neo_prompt_bench", ROOT / "scripts" / "neo_prompt_bench.py")
B = importlib.util.module_from_spec(_spec)
sys.modules["neo_prompt_bench"] = B          # dataclasses resolve their module by name
_spec.loader.exec_module(B)

CASE = {c.id: c for c in B.CASES}
KEY = "sk-SENTINEL-not-a-real-key-0000"


def test_the_meter_discriminates_on_every_criterion():
    rows = B.meter_twins()
    assert {r[0] for r in rows} == set(B.CRITERIA)
    assert all(ok for _, _, ok in rows), rows


def test_a_request_on_a_control_case_is_a_failure():
    t = B.Transcript([("request_change", {"text": "x", "kind": "improvement"})], "Pedido aberto.")
    assert B.grade(CASE["C6_read_only"], t)["proactive"] is False
    assert B.grade(CASE["C4_self"], t)["proactive"] is False
    assert B.grade(CASE["C4_self"], t)["not_self"] is False
    # CONTROL: the same case, answered without a request
    quiet = B.Transcript([("list_verticals", {})], "Há sete verticais e o bookkeeper tem estas ferramentas.")
    assert B.grade(CASE["C6_read_only"], quiet)["proactive"] is True


def test_reading_its_own_vertical_on_the_self_case_fails_not_self():
    t = B.Transcript([("get_vertical_config", {"vertical": "admin"})], "Não posso pedir isso.")
    assert B.grade(CASE["C4_self"], t)["not_self"] is False


def test_the_read_must_be_of_the_case_s_vertical_and_before_the_request():
    other = B.Transcript([("get_vertical_config", {"vertical": "closer"}),
                          ("request_change", {"text": "x", "kind": "correction"})], "ok")
    after = B.Transcript([("request_change", {"text": "x", "kind": "correction"}),
                          ("get_vertical_config", {"vertical": "bookkeeper"})], "ok")
    assert B.grade(CASE["C1_correction"], other)["read_first"] is False
    assert B.grade(CASE["C1_correction"], after)["read_first"] is False


def test_the_size_is_impact_classify_s():
    assert B.size_of("correction", CASE["C1_correction"]) == "small"
    assert B.size_of("improvement", CASE["C1_correction"]) == "large"
    assert B.size_of("correction", CASE["C2_improvement"]) == "small"   # 60 lines: still small…
    t = B.Transcript([("get_vertical_config", {"vertical": "bookkeeper"}),
                      ("request_change", {"text": "x", "kind": "correction"})], "ok")
    assert B.grade(CASE["C2_improvement"], t)["size"] is False         # …but the kind is wrong
    assert B.grade(CASE["C5_find_en"], t)["size"] is None              # no expected kind: not measured


@pytest.mark.parametrize("text,lang", [
    ("Abri o pedido de correcção da descrição; é uma mudança pequena e fica na fila.", "pt"),
    ("I opened the correction request for the description; it is a small change in the queue.", "en"),
    ("ok", "unknown"),
])
def test_language_of(text, lang):
    assert B.language_of(text) == lang


def test_the_rubric_reads_the_slots_and_a_removed_sentence_turns_it_off():
    now = B.prompts_at(None)
    assert all(B.rubric(now).values())
    cut = dict(now, system=now["system"].replace("Be proactive", "Be"))
    assert B.rubric(cut)["proactive"] is False
    cut = dict(now, voice=now["voice"].replace("administrator's language", "language"))
    assert B.rubric(cut)["language"] is False


def _args(tmp_path, **kw):
    ns = dict(before_ref=None, preflight=False, ledger=str(tmp_path / "ledger.txt"),
              ledger_prefix="cloud ledger", n=3, max_usd=1.0, model="m", price_in=0.15,
              price_out=0.60, out=None)
    ns.update(kw)
    return type("A", (), ns)()


def test_no_key_is_refused_and_nothing_is_written(tmp_path, capsys):
    assert B.cloud(_args(tmp_path), environ={}) == 3
    assert "OPENAI_API_KEY is not in the environment" in capsys.readouterr().out
    assert not (tmp_path / "ledger.txt").exists()


def test_the_preflight_sends_nothing_writes_nothing_and_never_prints_the_key(tmp_path, capsys):
    def post(_):
        raise AssertionError("the preflight must not call the model")
    assert B.cloud(_args(tmp_path, preflight=True), environ={"OPENAI_API_KEY": KEY}, post=post) == 0
    out = capsys.readouterr().out
    assert KEY not in out and "present" in out and "estimate ≈US$" in out
    assert not (tmp_path / "ledger.txt").exists()


def test_a_missing_ledger_is_refused(tmp_path):
    assert B.cloud(_args(tmp_path, ledger=None), environ={"OPENAI_API_KEY": KEY}) == 2


def _answer(content="Pedido aberto; fica na fila.", tool_calls=None, tin=100, tout=20):
    msg = {"content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg}], "usage": {"prompt_tokens": tin, "completion_tokens": tout},
            "system_fingerprint": "fp_test"}


def test_the_ledger_line_is_written_before_the_first_call_and_the_cost_after(tmp_path, capsys):
    ledger = tmp_path / "ledger.txt"
    seen = []

    def post(payload):
        if not seen:
            seen.append(ledger.read_text(encoding="utf-8"))
        return _answer()
    assert B.cloud(_args(tmp_path), environ={"OPENAI_API_KEY": KEY}, post=post) == 0
    assert "estimate ≈US$" in seen[0] and "real" not in seen[0]
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and "ran:" in lines[1] and "real ≈US$" in lines[1]
    out = capsys.readouterr().out
    assert KEY not in out and KEY not in ledger.read_text(encoding="utf-8")
    assert "fp_test" in out


def test_over_the_ceiling_it_stops_and_says_so(tmp_path, capsys):
    def post(_):
        return _answer(tin=10_000_000)
    assert B.cloud(_args(tmp_path, max_usd=0.5), environ={"OPENAI_API_KEY": KEY}, post=post) == 1
    assert "STOPPED over the ceiling" in capsys.readouterr().out
    assert "stopped" in (tmp_path / "ledger.txt").read_text(encoding="utf-8").splitlines()[-1]


def test_a_held_request_change_ends_the_loop():
    calls = []

    def post(payload):
        calls.append(payload)
        if len(calls) == 1:
            return _answer(None, [{"id": "c1", "function": {"name": "get_vertical_config",
                                                           "arguments": json.dumps({"vertical": "bookkeeper"})}}])
        if len(calls) == 2:
            return _answer(None, [{"id": "c2", "function": {"name": "request_change",
                                                           "arguments": json.dumps({"text": "fix", "kind": "correction"})}}])
        return _answer("Abri o pedido de correcção; é pequeno.")
    t = B.run_case(CASE["C1_correction"], B.prompts_at(None), post, B.Meter(), model="m",
                   max_usd=1.0, svc=B.AdminService())
    assert [n for n, _ in t.calls] == ["get_vertical_config", "request_change"]
    assert len(calls) == 3                       # two executor steps, then the voice
    assert "Held for confirmation" in calls[2]["messages"][1]["content"]
    assert all(B.grade(CASE["C1_correction"], t).values())


def test_the_ceiling_is_checked_after_every_executor_step_not_only_after_the_voice():
    calls = []

    def post(payload):
        calls.append(payload)
        return _answer(None, [{"id": f"c{len(calls)}", "function": {"name": "list_verticals",
                                                                   "arguments": "{}"}}],
                       tin=10_000_000)
    with pytest.raises(B.OverBudget):
        B.run_case(CASE["C6_read_only"], B.prompts_at(None), post, B.Meter(), model="m",
                   max_usd=0.5, svc=B.AdminService())
    assert len(calls) == 1
