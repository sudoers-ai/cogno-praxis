"""CLOSER — a consultative sales persona (prompts only, no vertical of its own).

It does not present a product and answer questions about it. It runs a DIAGNOSIS: it asks
about the contact's operation, names the bottleneck back to them in their own words and
numbers, and only then shows where the product fits. The "I need this" comes from the person,
not from us.

Prompts only, deliberately: the persona borrows the scheduler's tools for its closing step
(booking the follow-up), so there is no engine or MCP server here — just the four slots the
host's persona registry loads. If the arc ever needs to record what it learned across turns,
this package is where that vertical would grow.
"""
