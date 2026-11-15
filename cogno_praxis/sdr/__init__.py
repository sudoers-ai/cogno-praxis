"""SDR — the first-contact triage persona (prompts only, no vertical of its own).

It is the front door of the commercial chain: it talks to whoever arrives for the first time,
runs a SHORT qualification (is this person a decision-maker, do they have the problem we solve,
are they the size we serve), and either sets up a short conversation with the human team or says
— plainly — that it is not a fit. It does NOT run the deep diagnosis (that is the CLOSER), it
does NOT present a proposal, it quotes no price and it never charges.

Prompts only, deliberately (``allowed_modules=()``, ``conversational=True``): the persona
borrows the runtime's built-in ``human_handoff`` to pass a qualified contact to the human sales
group. There is no engine or MCP server here — just the four slots the host's persona registry
loads. It is one of the three commercial personas built on the CLOSER mould (SDR → CLOSER →
SELLER → AFTERSALES); they change role, not mechanics.
"""
