"""SECRETARY demo — a complete Cogno agent in your terminal, free and local.

One script marries the whole open-source stack: cogno-soma orchestrates the
cogno-anima cognitive stages over Ollama (cogno-synapse), with the scheduler
vertical served as a real MCP subprocess (this repo) bridged by cogno-mcp —
the exact same wiring a production host uses, minus the multi-tenant glue.

    ollama pull qwen3:8b && ollama pull nomic-embed-text
    python examples/secretary_demo.py                    # interactive REPL
    python examples/secretary_demo.py --trace            # + show the cognition
    python examples/secretary_demo.py --say "quero marcar uma consulta amanhã às 9 com o dr silva"

Type your requests in any language — the NOUMENO stage rewrites them into
canonical English before the pipeline reasons about them (visible with --trace).
"""

import argparse
import asyncio
import sys
import time
from datetime import date, timedelta
from pathlib import Path

PROMPTS = Path(__file__).resolve().parents[1] / "cogno_praxis" / "scheduler" / "prompts"

# Launch the scheduler server with its logging silenced: the subprocess inherits this
# terminal's stderr, and the MCP SDK's per-request INFO lines would clutter the chat.
SERVER_LAUNCHER = (
    "import logging, warnings, runpy;"
    "warnings.filterwarnings('ignore');"
    "logging.disable(logging.WARNING);"
    "runpy.run_module('cogno_praxis.scheduler.server', run_name='__main__')"
)

DIM = "\033[2m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _load_prompts() -> dict[str, str]:
    """The SECRETARY slot files, with the host-owned placeholders filled for the demo."""
    fills = {
        "{secretary_name}": "Sofia",
        "{tenant_name}": "Clínica Demo",
        "{identity_label}": "Ana",
        "{identity_role}": "guest",
        "{identity_email}": "ana@demo.com",
        "{{ROLE_CAPABILITIES}}": (
            "You can list professionals, check availability, book, list and cancel "
            "Ana's own appointments."
        ),
        "{{TENANT_PERSONAS}}": "(none — you are the only department)",
    }
    slots = {}
    for name in ("system", "scope", "limits", "voice"):
        text = (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")
        for key, val in fills.items():
            text = text.replace(key, val)
        slots[name] = text
    # Ground the model in real dates — an 8B model cannot do calendar arithmetic,
    # and a real host injects this context the same way.
    today = date.today()
    week = "\n".join(
        f"- {d.isoformat()} = {d.strftime('%A')}"
        for d in (today + timedelta(days=i) for i in range(8))
    )
    slots["system"] += f"\n\nToday is {today.isoformat()} ({today.strftime('%A')}). Calendar:\n{week}"
    return slots


def _trace_hooks():
    """Print the cognition as it happens — the pipeline made visible."""
    from cogno_soma import Hooks

    def noumeno(ctx):
        n = ctx.noumeno
        print(f"{DIM}  [NOUMENO]  \"{n.rewritten}\"  ({n.language} → en, {n.drift_tag}){RESET}")

    def ner(ctx):
        i = ctx.intent
        print(f"{DIM}  [NER]      {i.intent_class} · {i.sentiment} · domains={i.domains}"
              f" · pii_risk={i.pii_risk}{RESET}")

    def id_stage(ctx):
        r = ctx.id_result
        print(f"{DIM}  [ID]       route={r.triad_route} · goal={r.goal_status}"
              f" · turn={r.turn_number}{RESET}")

    def ego(ctx):
        if not ctx.ego_result:
            return
        for step in ctx.ego_result.steps:
            for call in step.tool_calls:
                mark = "✓" if call.ok else "✗"
                args = ", ".join(f"{k}={v}" for k, v in call.arguments.items())
                print(f"{DIM}  [EGO]      {call.tool}({args}) {mark}{RESET}")

    def superego(ctx):
        if ctx.superego_result:
            print(f"{DIM}  [JUDGE]    approved={ctx.superego_result.approved}{RESET}")

    return Hooks(after_noumeno=noumeno, after_ner=ner, after_id=id_stage,
                 after_ego=ego, after_superego=superego)


async def main() -> None:
    ap = argparse.ArgumentParser(description="Cogno SECRETARY demo (local, free)")
    ap.add_argument("--model", default="qwen3:8b", help="Ollama model (default: qwen3:8b)")
    ap.add_argument("--trace", action="store_true", help="show each cognitive stage")
    ap.add_argument("--say", action="append", default=[],
                    help="scripted message (repeatable); omit for the interactive REPL")
    args = ap.parse_args()

    from cogno_mcp import MCPDispatcher, stdio_session
    from cogno_soma import Pipeline, SessionRunner, TurnConfig
    from cogno_synapse import CachingEmbedder, OllamaBackend, OllamaEmbedder

    slots = _load_prompts()
    gen = OllamaBackend(model=args.model, temperature=0.0, format="json")
    ego = OllamaBackend(model=args.model, temperature=0.0)   # text path → <TOOL_CALL> fallback
    embedder = CachingEmbedder(OllamaEmbedder(model="nomic-embed-text"))

    pipe = Pipeline(embedder=embedder)
    cfg = TurnConfig(
        gen_backend=gen, ego_backend=ego,
        ego_prompt=slots["system"], limits_prompt=slots["limits"],
        voice_prompt=slots["voice"],
        hooks=_trace_hooks() if args.trace else None,
    )

    # The scheduler vertical runs as a real MCP server (subprocess, stdio) with its
    # in-memory demo catalog (Dr. Silva, Dr. Souza, Ana Reception) — cogno-mcp
    # bridges its tools into the EGO's ToolDispatcher contract.
    async with stdio_session(sys.executable, args=["-c", SERVER_LAUNCHER]) as s:
        disp = await MCPDispatcher.create(s)
        sess = SessionRunner(pipe, cfg, dispatcher=disp,
                             persona_id="SECRETARY", mcp_module="scheduler")

        print(f"{BOLD}SECRETARY{RESET} (Sofia · Clínica Demo · {args.model} local via Ollama)")
        print(f"{DIM}tools: " + ", ".join(
            t["function"]["name"] for t in disp.tools_schema()) + f"{RESET}")
        print(f"{DIM}fale em qualquer língua · Ctrl-D para sair{RESET}\n")

        async def turn(text: str) -> None:
            if args.say:  # scripted mode: type the message out so a recording reads naturally
                print(f"{BOLD}você>{RESET} ", end="", flush=True)
                for ch in text:
                    print(ch, end="", flush=True)
                    await asyncio.sleep(0.03)
                print()
            t0 = time.monotonic()
            ctx = await sess.run(text)
            dt = time.monotonic() - t0
            reply = ctx.superego_result.response if ctx.superego_result else "(sem resposta)"
            print(f"{CYAN}SECRETARY>{RESET} {reply}")
            print(f"{DIM}  ({dt:.0f}s · {ctx.total_tokens} tokens · stop={ctx.stop_reason}){RESET}\n")

        if args.say:
            for text in args.say:
                await turn(text)
            return

        while True:
            try:
                text = input(f"{BOLD}você>{RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\ntchau! 👋")
                return
            if not text:
                continue
            await turn(text)


if __name__ == "__main__":
    asyncio.run(main())
