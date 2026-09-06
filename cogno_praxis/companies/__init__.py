"""The ``company`` vertical — company/brand registration behind a FastMCP server.

A TRANSVERSAL capability rather than a persona's own domain: the SECRETARY carries it beside
the ``scheduler``, and any front-desk persona can. Mirrors the other verticals — a store port
+ a service + a FastMCP server, tenant-agnostic, with the host deciding the scope and the role.

Moved here from the host's native cortex skill on 2026-09-06 (``cogno_host/company_registration.py``
+ ``company_adapter.py``). The tool NAME and the shape of its answer are preserved byte for
byte: the host reads both to decide which company a session is talking about — see the module
docstring of ``server.py``.

**No ``durability`` module, deliberately.** Its three siblings each ship an
``is_perishable_edge`` to veto volatile edges from the knowledge graph (a balance, a booking).
A company's name, CNPJ and brand guidelines are the opposite of perishable — they are exactly
the durable facts the graph is for — so there is nothing here to veto, and an empty veto
function would read as coverage.
"""

from cogno_praxis.companies.identifiers import (
    cnpj_is_acceptable,
    cnpj_valid,
    company_id_for,
    fold,
    normalize_cnpj,
)
from cogno_praxis.companies.server import build_server
from cogno_praxis.companies.service import (
    CompanyError,
    CompanyService,
    DeletionOutcome,
    DeletionProposal,
)
from cogno_praxis.companies.store import (
    Company,
    CompanyStore,
    InMemoryCompanyStore,
    is_oversight,
)

__all__ = [
    "build_server", "CompanyError", "CompanyService", "CompanyStore",
    "InMemoryCompanyStore", "Company", "DeletionOutcome", "DeletionProposal", "is_oversight",
    "cnpj_is_acceptable", "cnpj_valid", "company_id_for", "fold", "normalize_cnpj",
]
