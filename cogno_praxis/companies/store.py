"""Domain type + the persistence port for the ``company`` vertical.

A registered company is **structured domain data**, so the vertical owns its store port (a
Protocol + an in-memory default; the host plugs the Pg adapter) — the same pattern as
``scheduler/store.py`` and ``bookkeeper/store.py``. The vertical is **tenant-agnostic**:
multi-tenancy is the host pointing at the right store/scope, never a column the vertical
filters. Identity fields are **opaque strings** the host resolves/authorizes; this vertical
just persists and echoes them back.

## Why the key is DERIVED from the name

``company_id`` is not a surrogate: it is :func:`~cogno_praxis.companies.identifiers.company_id_for`
over the accent-folded name, so registering "Padaria São João" twice UPDATES one row instead of
piling up a row per turn. That is the whole undo story for this vertical's one write (see
``server.py``), and it is why :meth:`CompanyStore.upsert` is an upsert rather than an insert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

# Roles whose view is UNSCOPED — they see every company in the scope. Anyone else (a GUEST, or
# a role this vertical has never heard of) sees only the companies THEY registered, matched on
# `created_by_user_id`. Written out here rather than imported from a sibling: three verticals
# define this set today and they do NOT agree (the scheduler counts SECRETARY, the bookkeeper
# counts OWNER), so a shared constant would be a fourth definition claiming to be the one.
#
# The vertical only maps role → VISIBILITY. The host AUTHORISES (`cogno_host/rbac.py` decides
# which tools a role even sees) and injects the role; nothing here trusts a value the model
# chose. An unknown role falls to the NARROWEST view, which is the direction a mistake should
# take: a role nobody taught this vertical about must not inherit oversight.
EMPLOYEE_ROLE = "EMPLOYEE"
OVERSIGHT_ROLES: "frozenset[str]" = frozenset({"EMPLOYEE", "SUPERVISOR", "ADMIN", "OWNER"})


def is_oversight(role: str) -> bool:
    """May this role see companies it did not register?

    ``EMPLOYEE`` is IN this set, which is where this vertical differs from the bookkeeper's
    identically-named predicate — and the difference is the owner's rule, not an oversight. A
    financial entry belongs to the person who recorded it; a registered company belongs to the
    BUSINESS, and every member of staff works for it. What is scoped here is the visitor: a
    lead who registered their own company sees that one and no other.

    A consequence, declared rather than left to be discovered: because the vertical's whole
    store is already ONE tenant's (the host injects `scope = tenant_id`), "the tenant's
    companies" and "all companies" are the SAME SET here. The policy distinguishes EMPLOYEE
    from SUPERVISOR/ADMIN and this vertical cannot: the difference would only become visible in
    a deployment whose scope is narrower than a tenant, and inventing one to honour the shape
    of the table would be a filter that answers a question nobody asked.
    """
    return (role or "").upper() in OVERSIGHT_ROLES


@dataclass
class Company:
    """One company registered by the business — brand parameters, visual identity, guidelines.

    ``cnpj`` carries NO DEFAULT while its neighbours do, and the asymmetry is the point: the
    chain from the model's argument to the stored row is four layers deep, and a default here
    is what lets any one of them be skipped in silence — a layer stops passing it and every
    registration quietly stores a blank, which is indistinguishable from "not supplied".
    Without one, the layer that forgets raises ``TypeError`` on its very first construction.

    ``cnpj`` is stored in the CLEAR, deliberately: it is the *company's* commercial-register
    number — public data in Brazil, published by the Receita Federal and printed on every
    invoice — not a contact's CPF. Hashing it would make the column unreadable for the one job
    it has, being shown back to the employee who registered the company.
    """

    company_id: str
    name: str
    cnpj: str
    segment: str = ""
    # The two free-text brand fields ride one jsonb under stable keys. An empty one is left OUT
    # rather than stored as "", so a later registration supplying only one does not read as
    # "the other was cleared on purpose" — and a reader can tell "never given" from "blank".
    visual_identity: "dict[str, Any]" = field(default_factory=dict)
    created_by_user_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


@runtime_checkable
class CompanyStore(Protocol):
    """The persistence port. In-memory default below; the host injects ``PgCompanyStore``."""

    def upsert(self, company: Company) -> Company: ...
    def get(self, company_id: str) -> Optional[Company]: ...
    def list_companies(self) -> "list[Company]": ...
    def delete(self, company_id: str) -> bool: ...


@dataclass
class InMemoryCompanyStore:
    """Process-local store — the standalone demo + unit tests. Production injects the Pg adapter."""

    companies: "dict[str, Company]" = field(default_factory=dict)

    def upsert(self, company: Company) -> Company:
        prior = self.companies.get(company.company_id)
        if prior is not None:
            # created_at/created_by survive an update, exactly as the SQL ON CONFLICT clause
            # leaves them alone: a correction is not a new registration by a new author.
            company.created_at = prior.created_at
            company.created_by_user_id = prior.created_by_user_id or company.created_by_user_id
        self.companies[company.company_id] = company
        return company

    def get(self, company_id: str) -> Optional[Company]:
        return self.companies.get(company_id)

    def list_companies(self) -> "list[Company]":
        return sorted(self.companies.values(), key=lambda c: c.company_id)

    def delete(self, company_id: str) -> bool:
        return self.companies.pop(company_id, None) is not None
