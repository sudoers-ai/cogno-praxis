"""Graph-durability veto for the BOOKKEEPER vertical.

Mirrors ``scheduler/durability.py`` for financial bookkeeping: the perishable RELATION names a
money conversation produces (a transaction, a balance, a payment/invoice state) — live figures
that a tool read owns, never durable graph knowledge. Durable relations (a client EMPLOYS a
person, a company OWNS an account) pass untouched. Generic signals (dates, money-amount
endpoints, generic concepts) are the host core's job.
"""

from __future__ import annotations

import re

# Transaction/payment-state relation stems + PT-BR forms.
_PERISHABLE_REL = re.compile(
    r"TRANSACTION|INVOICE|PAYMENT|PAID|UNPAID|BALANCE|DUE|OVERDUE|BILLED|CHARGE|REFUND|"
    r"DEPOSIT|WITHDRAW|INCOME|OUTCOME|EXPENSE|DEBT|OWES|TOTAL|"
    r"PAG|FATURA|SALDO|COBRAN|RECEB|DESPESA|DIVIDA|VENCIMENT|PENDENCIA", re.IGNORECASE)


def is_perishable_edge(source: str, target: str, relation: str) -> bool:
    """True iff this edge encodes volatile FINANCIAL state (belongs to a live tool read, not
    the durable graph). Only inspects the relation name — amounts/dates are host-core."""
    return bool(_PERISHABLE_REL.search(relation or ""))
