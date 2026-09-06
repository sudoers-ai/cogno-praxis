"""Company registration — the domain logic, over a :class:`CompanyStore`.

Ported from the host's ``company_registration`` skill + ``company_adapter`` (2026-09-06). Two
rules travel with it unchanged, and both are refusals BEFORE the store is touched:

* **an empty name is refused** — the row's whole meaning is its name;
* **CNPJ: optional to give, VALIDATED when given.** A company registration with no tax number
  is a normal registration — plenty of a tenant's clients are informal, and refusing them would
  make the vertical useless for exactly the contacts it was built for. A registration with a
  WRONG one is worse than one with none: it is a legal identifier that will be read back,
  copied into an invoice and matched against a public register, and nobody downstream
  re-checks it.

**A refused write is never a success.** Every path out of :meth:`CompanyService.register` that
did not reach the store raises :class:`CompanyError`; the server turns that into an MCP error
result, which is ``ok=False`` at the EGO. That mapping is not decoration — see the note in
``server.py`` on why this vertical does NOT use the sibling verticals' ``return "ERROR: ..."``
convention.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from cogno_praxis.company.identifiers import (
    cnpj_is_acceptable,
    company_id_for,
    normalize_cnpj,
)
from cogno_praxis.company.store import Company, CompanyStore, InMemoryCompanyStore


class CompanyError(RuntimeError):
    """A registration that was REFUSED — nothing was written."""


class CompanyService:
    """Register and read back the companies of one scope. Sync, like its store port."""

    def __init__(self, store: Optional[CompanyStore] = None, *,
                 clock: Callable[[], float] = time.time) -> None:
        self.store: CompanyStore = store if store is not None else InMemoryCompanyStore()
        self._clock = clock

    def register(self, name: str, *, cnpj: str = "", visual_identity: str = "",
                 guidelines: str = "", identity_id: str = "") -> Company:
        """Persist one company and return the stored row. Raises :class:`CompanyError`.

        ``identity_id`` is the AUTHOR — an opaque string the host injects (it is never a value
        the model chooses). It is recorded on creation and, on a later correction, the original
        author survives: a correction is not a new registration by a new person.
        """
        cname = (name or "").strip()
        if not cname:
            raise CompanyError("company_name is required — say which company to register.")
        clean = normalize_cnpj(cnpj)
        if not cnpj_is_acceptable(clean):
            # NAMING THE FIELD is the requirement, not a nicety: this refusal is fed back to
            # the EGO, and "não consegui cadastrar" with no field named leaves the model
            # guessing which of four arguments to ask about — so it re-sends the same wrong one,
            # or asks for the company name again. The VALUE is deliberately not echoed: the
            # contact typed it and already has it, and repeating a document-shaped number into
            # the reply buys nothing while adding a span for every downstream guard to decide
            # about.
            raise CompanyError(
                "O CNPJ informado (campo `cnpj`) não é válido: confira os 14 dígitos e os "
                "dígitos verificadores, ou deixe o campo em branco — o CNPJ é opcional no "
                "cadastro.")
        brand = {k: v for k, v in (("visual_identity", visual_identity),
                                   ("guidelines", guidelines)) if v}
        now = self._clock()
        row = Company(company_id=company_id_for(cname), name=cname, cnpj=clean,
                      visual_identity=brand, created_by_user_id=identity_id,
                      created_at=now, updated_at=now)
        try:
            return self.store.upsert(row)
        except Exception as exc:  # noqa: BLE001 — any store failure is "it did not land"
            # Only the exception's CLASS travels. The message can carry the DSN, a role name or
            # a column value, and this string ends up in the tool's output and from there in a
            # turn trace.
            raise CompanyError(
                f"Não consegui salvar o cadastro da empresa agora ({type(exc).__name__}).") from exc

    def get(self, company_id: str) -> Optional[Company]:
        return self.store.get(company_id)

    def list_companies(self) -> "list[Company]":
        return self.store.list_companies()

    def registration_payload(self, row: Company, *, visual_identity: str = "",
                             guidelines: str = "") -> "dict[str, Any]":
        """The tool's answer, as a MAPPING — rendered by the server, read by the host's focus.

        The keys and their order are the ones the host's native skill produced before this
        vertical existed (``cogno_host/company_registration.py``), and they are preserved
        deliberately: ``cogno_host.company_focus`` decides which company a session is talking
        about by reading ``company_id``/``company_name`` out of this very answer. Renaming a
        key here does not fail anywhere — the focus simply stops moving, and a later planning
        turn is built for the wrong company while the text still reads plausibly.

        ``cnpj`` is the stored, NORMALISED form ('' when none was supplied). It is here so the
        executor can ground a read-back on what LANDED rather than on what the contact typed,
        which is the difference between confirming a record and repeating an argument.
        """
        return {
            "company_id": row.company_id,
            "company_name": row.name,
            "cnpj": row.cnpj,
            "visual_identity": visual_identity,
            "guidelines": guidelines,
            "message": f"Successfully registered company brand profile for '{row.name}'.",
        }

    def help_note(self) -> str:
        """What this vertical does (scope guardrail)."""
        return ("I register the companies/brands this business works with: the name, an "
                "optional CNPJ, the visual identity and the brand guidelines. Registering the "
                "same company again UPDATES its record — it does not create a second one.")
