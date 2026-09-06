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

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from cogno_praxis.companies.identifiers import (
    cnpj_is_acceptable,
    company_id_for,
    fold,
    normalize_cnpj,
)
from cogno_praxis.companies.store import (
    Company,
    CompanyStore,
    InMemoryCompanyStore,
    is_oversight,
)


class CompanyError(RuntimeError):
    """A call that was REFUSED — nothing was written.

    Used for a REFUSAL, never for "you may not see that". The difference is deliberate and it
    is the lesson of a live turn: a limit that leaves this vertical as an ERROR arrives at the
    contact as *"não consegui acessar"* — the voice reads a failure and apologises for the
    system instead of stating the boundary. So the READ tools never raise for scope: they
    answer normally and SAY the limit in their own words (:meth:`CompanyService.scope_note`).

    The WRITE tools DO raise on a cross-identity attempt, and that is not an exception to the
    rule but the other half of it. A mutating tool that returned a limit as ordinary text comes
    back through cogno-mcp as ``ToolResult(ok=True, side_effect=True)`` — a write that never
    happened, counted by the host's ``committed_this_turn`` and shown to every anti-fabrication
    net as a commit. So the transport for those is an error and the WORDING is a limit, which
    is the most this layer can do about it; the reason is written here rather than left for the
    next reader to rediscover from the two rules pulling against each other.
    """


@dataclass(frozen=True)
class DeletionProposal:
    """What :meth:`CompanyService.delete` answers when it has READ but not committed.

    ``confirm_company_id`` is the argument the caller must send back in order to delete, and it
    can only be learned from this proposal. That is what makes deletion a gate-C tool rather
    than a gate-B one: gate B decides by tool NAME before anything runs and can only say "a
    deletion is coming"; this one ran, read the row, and can say WHICH company — and, once the
    host tells it, what else points at that company.
    """

    company: Company
    confirm_company_id: str


@dataclass(frozen=True)
class DeletionOutcome:
    """Either the row LEFT (``removed``) or a grounded question was asked (``proposal``)."""

    removed: "Optional[Company]" = None
    proposal: "Optional[DeletionProposal]" = None


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

    # ── visibility ───────────────────────────────────────────────────────────────────────
    def _visible(self, identity_id: str, role: str) -> "list[Company]":
        """Every company this caller may see, newest identity rule first.

        Unscoped for staff; for anyone else, the companies THEY registered. The match is on
        ``created_by_user_id``, the field the host stamps from the authenticated identity — a
        value the model never supplies (the host's RBAC injects ``identity_id`` and PRUNES it
        from the schema the model reads).

        A blank ``identity_id`` on a scoped caller sees NOTHING rather than everything. That is
        the direction a missing value has to take: an anonymous visitor with no id would
        otherwise match every row whose author was also never recorded.
        """
        rows = self.store.list_companies()
        if is_oversight(role):
            return rows
        me = (identity_id or "").strip()
        if not me:
            return []
        return [c for c in rows if c.created_by_user_id == me]

    def scope_note(self, identity_id: str, role: str) -> str:
        """The LIMIT, in words, for a scoped caller — ``""`` when the caller sees everything.

        It travels appended to the read tools' own answers so that "I found nothing" and "I
        found nothing I am allowed to show you" are never the same sentence to the model. It is
        a limit, not an error: see :class:`CompanyError`.
        """
        if is_oversight(role):
            return ""
        return ("Só posso ver as empresas que você mesmo cadastrou — se a empresa foi "
                "cadastrada por outra pessoa, ela não aparece aqui.")

    def _mine_or_refuse(self, company_id: str, identity_id: str, role: str) -> Company:
        """The company, if this caller may WRITE to it. Raises a limit-worded refusal if not.

        The check is load-bearing and not a formality: ``company_id`` is DERIVED from the
        accent-folded name, so it is GUESSABLE — "Padaria Sol Nascente" is always
        ``padaria-sol-nascente``. A caller who cannot see a company through
        :meth:`_visible` can still name it, so the scope has to be re-decided on the way in
        rather than assumed from how the id was obtained.
        """
        row = self.store.get((company_id or "").strip())
        if row is None:
            raise CompanyError(
                f"Não encontrei nenhuma empresa com o identificador {company_id!r}. "
                "Busque a empresa primeiro e use o identificador que a busca devolver.")
        if not is_oversight(role) and row.created_by_user_id != (identity_id or "").strip():
            raise CompanyError(
                "Essa empresa foi cadastrada por outra pessoa — só posso alterar ou remover "
                "as que você mesmo cadastrou.")
        return row

    # ── reads ────────────────────────────────────────────────────────────────────────────
    def list_visible(self, *, identity_id: str = "", role: str = "") -> "list[Company]":
        """Every company this caller may see. A LISTING, and listings choose nothing."""
        return self._visible(identity_id, role)

    def search(self, query: str, *, identity_id: str = "", role: str = "") -> "list[Company]":
        """The companies this caller may see whose name or CNPJ matches ``query``.

        Accent- and case-insensitive on the name (the same fold the key is derived with, so a
        contact who types "padaria sao joao" finds "Padaria São João"), and digits-only on the
        CNPJ so a punctuated number matches a stored bare one.
        """
        q = fold(query or "", punctuation=True).strip()
        digits = re.sub(r"\D", "", query or "")
        if not q and not digits:
            return []
        out = []
        for c in self._visible(identity_id, role):
            if q and q in fold(c.name, punctuation=True):
                out.append(c)
            elif digits and c.cnpj and digits in c.cnpj:
                out.append(c)
        return out

    # ── writes ───────────────────────────────────────────────────────────────────────────
    def update(self, company_id: str, *, name: str = "", cnpj: str = "",
               visual_identity: str = "", guidelines: str = "", segment: str = "",
               identity_id: str = "", role: str = "") -> Company:
        """Change the fields GIVEN on a company this caller may write to.

        Only non-empty arguments are applied, and that is a rule with a victim if it is got
        wrong: a partial update that treated "" as "clear this field" would erase the brand
        guidelines of every company whose name a caller merely corrected. Clearing a field is
        not expressible here on purpose — it is a rarer act than correcting one, and the
        ambiguous spelling of it is the dangerous one.

        The NAME is the exception, and it is the sharp edge of this tool: ``company_id`` is
        derived from the name, so renaming a company would key a different row. It is therefore
        applied to the row's ``name`` and the KEY IS LEFT ALONE — the record keeps its identity
        and its history, and the id stops matching the name. That is the lesser of the two
        wrongs: re-keying would mean an insert plus an orphan, which is the same company twice.
        """
        row = self._mine_or_refuse(company_id, identity_id, role)
        clean = normalize_cnpj(cnpj)
        if cnpj and not cnpj_is_acceptable(clean):
            raise CompanyError(
                "O CNPJ informado (campo `cnpj`) não é válido: confira os 14 dígitos e os "
                "dígitos verificadores.")
        brand = dict(row.visual_identity or {})
        if visual_identity:
            brand["visual_identity"] = visual_identity
        if guidelines:
            brand["guidelines"] = guidelines
        updated = Company(company_id=row.company_id, name=(name or row.name),
                          cnpj=(clean or row.cnpj), segment=(segment or row.segment),
                          visual_identity=brand,
                          created_by_user_id=row.created_by_user_id,
                          created_at=row.created_at, updated_at=self._clock())
        try:
            return self.store.upsert(updated)
        except Exception as exc:  # noqa: BLE001
            raise CompanyError(
                f"Não consegui salvar a alteração agora ({type(exc).__name__}).") from exc

    def delete(self, company_id: str, *, identity_id: str = "", role: str = "",
               confirm_company_id: str = "") -> DeletionOutcome:
        """Remove a company — in TWO steps, and the first one commits nothing.

        Called without ``confirm_company_id`` it READS the row and answers with a proposal
        naming what it selected. Only a second call carrying the id the proposal named deletes.
        That is cogno-anima's gate C, and the write path is UNREACHABLE without the argument —
        the reachability claim ``tests/unit/test_tool_annotations.py`` performs.
        """
        row = self._mine_or_refuse(company_id, identity_id, role)
        if confirm_company_id.strip() != row.company_id:
            return DeletionOutcome(proposal=DeletionProposal(company=row,
                                                             confirm_company_id=row.company_id))
        try:
            gone = self.store.delete(row.company_id)
        except Exception as exc:  # noqa: BLE001
            raise CompanyError(
                f"Não consegui remover a empresa agora ({type(exc).__name__}).") from exc
        if not gone:
            raise CompanyError("A empresa já não estava cadastrada — nada foi removido.")
        return DeletionOutcome(removed=row)

    def search_payload(self, row: Company, *, note: str = "") -> "dict[str, Any]":
        """The answer to a search that found EXACTLY ONE company — as a MAPPING.

        The shape of a search's answer IS the rule, and that is the whole design here. The
        host's rule for "which company is this session about" is *"registered one just now, use
        it; searched for a SPECIFIC one, use it"*, and it reads the turn's tool answers to
        decide (``cogno_host.company_focus``). One match is the only case that identifies a
        company, so one match is the only case that answers with a machine-readable mapping;
        zero, several, and a listing answer in prose, which the host's parser rejects by
        failing closed. Nothing has to agree about a count across two repos — the count decided
        the SHAPE here, once.

        ``note`` rides INSIDE the mapping rather than after it: a limit appended as a trailing
        line would put text after the mapping, and the host parses the whole answer as one
        Python literal.
        """
        payload: "dict[str, Any]" = {
            "company_id": row.company_id,
            "company_name": row.name,
            "cnpj": row.cnpj,
            "segment": row.segment,
            "visual_identity": str((row.visual_identity or {}).get("visual_identity") or ""),
            "guidelines": str((row.visual_identity or {}).get("guidelines") or ""),
            "message": f"Found exactly one company matching your search: '{row.name}'.",
        }
        if note:
            payload["note"] = note
        return payload

    def help_note(self) -> str:
        """What this vertical does (scope guardrail)."""
        return ("I register the companies/brands this business works with: the name, an "
                "optional CNPJ, the visual identity and the brand guidelines. Registering the "
                "same company again UPDATES its record — it does not create a second one.")
