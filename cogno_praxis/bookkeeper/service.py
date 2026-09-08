"""``BookkeeperService`` — orchestrates the engine + store and applies role visibility.

The service is the injection seam: the host builds one over its own store adapter (or the
in-memory default) and hands it to ``build_server``. It raises ``BookkeeperError`` on a domain
violation; the server maps that to a recoverable tool error (fed back to the model).

**Role visibility** (mechanics only — the host authorises the role): an ``EMPLOYEE`` sees/searches
only the transactions they recorded; an oversight role (SUPERVISOR/ADMIN/OWNER) sees the whole
scope. Recording is always attributed to the caller's ``identity_id``; ``remove_by_search`` only
removes the caller's OWN entries (a guardrail — no cross-identity deletion).

**Removal proposes before it commits** (:class:`RemovalOutcome`): ``remove_by_search`` READS the
ledger first, and a call that does not name a row writes nothing — it answers with the entry it
would remove. See the class docstrings below for why that read is the whole point.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Optional

from cogno_praxis.bookkeeper.engine import (
    INCOME,
    OUTCOME,
    BookkeeperError,
    matches_entry,
    normalize_name,
    parse_amount,
    resolve_date,
    summarize,
)
from cogno_praxis.bookkeeper.store import (
    BookkeeperStore,
    InMemoryBookkeeperStore,
    Transaction,
    is_oversight,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


_ORDINAL = itertools.count()


def _now() -> str:
    """A strictly-increasing creation stamp (wall clock + a process ordinal tiebreaker) — sorts
    chronologically as a plain string, so "most recent" is deterministic even within a tx_date."""
    return f"{datetime.now(timezone.utc).isoformat()}-{next(_ORDINAL):09d}"


@dataclass
class RemovalProposal:
    """What a removal READ and deliberately did NOT delete.

    The entry the query selected, plus every other entry it also matched. Both halves are facts
    that only a call which already RAN can state, and that is the whole reason this type exists:
    the tool NAME is the same for every removal, so a rule written per name — "``remove_by_search``
    is destructive, hold it" — can say *that* something will be deleted and never *what*. Which
    row an accent-folded substring query selects, of what value, of what date, and whether it
    selected three siblings alongside it, is knowable only after the read.

    ``entry`` is the row this call would remove (the caller's most recent match, the same one the
    one-shot version deleted outright). ``others`` are the rest, in the same order — an ambiguity
    the query did not resolve, and which nobody downstream can see.
    """

    entry: dict
    others: list[dict] = field(default_factory=list)

    @property
    def confirm_tx_id(self) -> str:
        """The token that commits THIS row, and only it.

        A row id rather than a bare yes/no on purpose: between the proposal and the confirmation
        the caller may record a NEWER matching entry, and "the most recent match" would then be a
        different row than the one the user was shown. Pinning the id means what is deleted is
        what was proposed, or nothing at all.
        """
        return str(self.entry.get("tx_id", ""))


@dataclass
class RemovalOutcome:
    """The result of one :meth:`BookkeeperService.remove_by_search` call — three states, one true.

    ``removed``    the caller named a row (``confirm_tx_id``) and it is gone.
    ``proposal``   a row matched and was NOT deleted; the call is asking about THAT row.
    neither one    nothing matched — there is nothing to ask about (unchanged behaviour).

    :attr:`needs_confirmation` is the vertical half of the EGO's THIRD confirmation gate: the one
    where the skill itself, having read, says "I did not commit — ask first", and hands over a
    proposal grounded in real data instead of a generic "are you sure?".
    """

    removed: "Optional[dict]" = None
    proposal: "Optional[RemovalProposal]" = None

    @property
    def needs_confirmation(self) -> bool:
        """The call RAN, read the ledger, and decided it must not commit without asking.

        Maps onto ``cogno_anima.types.ToolResult.needs_confirmation`` (and, for an in-process
        skill, ``cogno_cortex.types.SkillResult.needs_confirmation``): the field an adapter sets
        so the EGO records the call as pending and stops to propose.

        ``True`` is a PROMISE that nothing was committed, and here that promise is structural
        rather than remembered — the proposal branch is the branch that never calls
        ``store.remove``, so ``removed`` is ``None`` whenever this is ``True``. A test pins the
        pair, because the EGO's contract (``ok`` AND ``side_effect`` for a write) is only worth
        anything if the producer keeps its end.
        """
        return self.proposal is not None

    @property
    def committed(self) -> bool:
        """A row was actually deleted by this call."""
        return self.removed is not None


class BookkeeperService:
    def __init__(self, store: Optional[BookkeeperStore] = None, *,
                 today: Optional[Callable[[], date]] = None) -> None:
        self._store: BookkeeperStore = store or InMemoryBookkeeperStore()
        self._today: Callable[[], date] = today or date.today

    # ── recording (mutating) ───────────────────────────────────────────
    def add_income(self, description: str, amount: object, identity_id: str, *,
                   client_name: str = "", tx_date: str = "") -> Transaction:
        amt = parse_amount(amount)
        desc = normalize_name(description)
        if not desc:
            raise BookkeeperError("description is required")
        client_id = ""
        cname = normalize_name(client_name)
        if cname:
            client_id = self._store.upsert_client(cname).client_id
        tx = Transaction(tx_id=_new_id(), kind=INCOME, identity_id=identity_id, description=desc,
                         amount=amt, tx_date=resolve_date(tx_date, self._today()),
                         client_id=client_id, client_name=cname, created_at=_now())
        self._store.add(tx)
        return tx

    def add_outcome(self, description: str, amount: object, identity_id: str, *,
                    tx_date: str = "") -> Transaction:
        amt = parse_amount(amount)
        desc = normalize_name(description)
        if not desc:
            raise BookkeeperError("description is required")
        tx = Transaction(tx_id=_new_id(), kind=OUTCOME, identity_id=identity_id, description=desc,
                         amount=amt, tx_date=resolve_date(tx_date, self._today()), created_at=_now())
        self._store.add(tx)
        return tx

    # ── reading (read-only, role-scoped) ───────────────────────────────
    def _scope(self, identity_id: str, role: str) -> Optional[str]:
        """The identity filter for a read: None (all) for oversight, else the caller's own id."""
        return None if is_oversight(role) else identity_id

    def get_summary(self, identity_id: str, role: str, *,
                    date_from: str = "", date_to: str = "") -> dict:
        who = self._scope(identity_id, role)
        df, dt = (date_from or None), (date_to or None)
        incomes = self._store.list(kind=INCOME, identity_id=who, date_from=df, date_to=dt)
        outcomes = self._store.list(kind=OUTCOME, identity_id=who, date_from=df, date_to=dt)
        totals = summarize((t.amount for t in incomes), (t.amount for t in outcomes))
        return {**totals, "income_count": len(incomes), "outcome_count": len(outcomes),
                "incomes": [self._row(t) for t in incomes],
                "outcomes": [self._row(t) for t in outcomes]}

    def list_clients(self) -> list[dict]:
        # clients are business-wide reference data (not identity-scoped)
        return [{"client_id": c.client_id, "name": c.name} for c in self._store.list_clients()]

    def search(self, query: str, identity_id: str, role: str, *,
               date_from: str = "", date_to: str = "") -> list[dict]:
        who = self._scope(identity_id, role)
        rows = self._store.list(identity_id=who, date_from=date_from or None, date_to=date_to or None)
        hits = [t for t in rows if matches_entry(t.description, t.client_name,
                                                 t.amount, query)]
        return [self._row(t) for t in hits]

    # ── removing (destructive — own entries only, and it PROPOSES first) ───
    def remove_by_search(self, query: str, identity_id: str, *,
                         confirm_tx_id: str = "") -> RemovalOutcome:
        """Find the caller's most recent transaction matching ``query`` — and ask before deleting.

        TWO STEPS, and the first one writes nothing:

        1. ``remove_by_search(query, identity_id)`` reads the ledger and returns a
           :class:`RemovalProposal` — the entry it would remove and the siblings the same query
           also matched. The store is untouched.
        2. ``remove_by_search(query, identity_id, confirm_tx_id=<the entry's id>)`` deletes that
           exact row.

        ``query`` selects on the entry's WORDS or on its exact AMOUNT (:func:`matches_entry`).
        Naming an entry by its value is how a contact actually refers to one, and until that
        axis existed a query of "45,00" searched a text field that never held a number.

        No match at all → an empty :class:`RemovalOutcome`: the store was not touched. That is a
        lookup which came up empty — NOT a failed removal, and NOT proof the entry is absent,
        since the search covers one wording over this identity's own rows. ``server.py`` says
        exactly that in the sentence it raises, because the model reads that channel as failure.

        The confirmation rides an argument this method OWNS, because what a removal needs in order
        to commit is this vertical's business — nothing above it invents the name. A
        ``confirm_tx_id`` that is not among the caller's current matches (already deleted, someone
        else's, or stale) does NOT fall back to "the most recent one": it proposes again over what
        is actually there. Guessing which row a stale id meant is exactly the mistake the two
        steps exist to prevent.
        """
        rows = self._store.list(identity_id=identity_id)   # own only, most-recent first
        hits = [t for t in rows if matches_entry(t.description, t.client_name,
                                                 t.amount, query)]
        if not hits:
            return RemovalOutcome()
        pinned = (confirm_tx_id or "").strip()
        for t in hits:
            if pinned and t.tx_id == pinned:
                self._store.remove(t.tx_id)
                return RemovalOutcome(removed=self._row(t))
        return RemovalOutcome(proposal=RemovalProposal(
            entry=self._row(hits[0]), others=[self._row(t) for t in hits[1:]]))

    # ── usage / help ───────────────────────────────────────────────────
    @staticmethod
    def usage_note() -> str:
        """AI token/usage is metered by the HOST (cogno-meter), not this vertical (decision #4)."""
        return ("AI usage/token metering is tracked by the host, not the bookkeeper. "
                "Ask the operator for the usage dashboard.")

    @staticmethod
    def help_note() -> str:
        return ("I am the financial bookkeeper: I record income (entradas) and expenses (saídas), "
                "track clients, search transactions and produce summaries. I do not schedule "
                "appointments or answer general questions — those go to reception.")

    @staticmethod
    def _row(t: Transaction) -> dict:
        return {"tx_id": t.tx_id, "kind": t.kind, "description": t.description,
                "amount": t.amount, "date": t.tx_date, "client": t.client_name}
