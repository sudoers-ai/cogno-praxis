"""SELLER (Vendedor) — the order-taking persona (prompts only, no vertical of its own).

It receives a contact who ALREADY wants to buy — the proposal was the CLOSER's job, the
decision is the contact's. The SELLER confirms the order (what, how many, the catalogue value of
each item), lets the TOTAL be summed by the system (never its own arithmetic), registers the
interest and hands the conversation to the human sales group that closes the payment. It does
NOT present a proposal and it NEVER charges — payment is a human/finance step.

Prompts only, deliberately (``allowed_modules=()``, ``conversational=True``): the persona
borrows the runtime's built-in ``human_handoff`` to pass the confirmed order to the human team.
There is no engine or MCP server here — just the four slots the host's persona registry loads.
One of the three commercial personas built on the CLOSER mould (SDR → CLOSER → SELLER →
AFTERSALES); they change role, not mechanics.
"""
