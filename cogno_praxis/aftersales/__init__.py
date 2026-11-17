"""AFTERSALES (Pós-venda) — the follow-up persona (prompts only, no vertical of its own).

It enters AFTER the sale, with the customer already using the product. Its job is to follow up:
a check-in on whether the original bottleneck was solved, answers to usage questions, a reading
of satisfaction, and an early catch of the signal that a customer might leave. It does not
charge and it does not renegotiate price on its own initiative.

What it knows about the product comes from the DOCUMENTS the company published for it, read this
turn with ``consult_documents`` — never a fixed product block. The moment to read is a usage
doubt. It measures satisfaction **in TEXT** — one plain question (a word, or a 0–10 read, written
in the reply). It has NO poll tool: the survey service does not exist yet, and this persona is
born without it. When an opportunity appears, it hands back to the SELLER; when a customer is
unhappy and asks for a person, it uses the runtime's built-in ``human_handoff``.

Prompts only, deliberately (``allowed_modules=()``, ``conversational=True``): there is no engine
or MCP server here — just the four slots the host's persona registry loads. One of the three
commercial personas built on the CLOSER mould (SDR → CLOSER → SELLER → AFTERSALES); they change
role, not mechanics.
"""
