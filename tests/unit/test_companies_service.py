"""The ``company`` vertical's domain rules — a refused write never lands, a re-registration updates.

Ported with the code from the host's ``company_registration`` skill (2026-09-06). The rules are
asserted here rather than re-derived: an empty name and an unacceptable CNPJ are refusals BEFORE
the store is touched, and the row's key is derived from the accent-folded name so registering
the same company twice UPDATES one row.
"""

from __future__ import annotations

import pytest

from cogno_praxis.companies import (
    CompanyError,
    CompanyService,
    InMemoryCompanyStore,
    cnpj_is_acceptable,
    company_id_for,
    normalize_cnpj,
)

_CNPJ_OK = "11.222.333/0001-81"
_CNPJ_BAD = "11.222.333/0001-99"


def _svc() -> CompanyService:
    return CompanyService(InMemoryCompanyStore())


# ── the two refusals, and the store is untouched by both ────────────────────────────────
@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_an_empty_name_is_refused_and_nothing_is_stored(name):
    svc = _svc()
    with pytest.raises(CompanyError, match="company_name"):
        svc.register(name)
    assert svc.list_companies() == []


def test_a_wrong_cnpj_is_refused_by_the_check_digits_and_nothing_is_stored():
    svc = _svc()
    with pytest.raises(CompanyError, match="cnpj"):
        svc.register("Acme", cnpj=_CNPJ_BAD)
    assert svc.list_companies() == []


def test_the_refusal_names_the_field_and_never_echoes_the_value():
    """The message is fed back to the model, so it must say WHICH argument to fix — and the
    value is deliberately absent: the contact typed it and already has it, and repeating a
    document-shaped number adds a span every downstream guard then has to decide about."""
    svc = _svc()
    with pytest.raises(CompanyError) as exc:
        svc.register("Acme", cnpj=_CNPJ_BAD)
    assert "cnpj" in str(exc.value)
    assert "11222333000199" not in str(exc.value) and _CNPJ_BAD not in str(exc.value)


def test_no_cnpj_is_a_normal_registration():
    """Optional to give: plenty of a tenant's clients are informal, and refusing them would
    make the vertical useless for exactly the contacts it was built for."""
    row = _svc().register("Padaria Sol Nascente")
    assert row.cnpj == ""


def test_a_valid_cnpj_is_stored_NORMALISED():
    assert _svc().register("Acme", cnpj=_CNPJ_OK).cnpj == "11222333000181"


def test_a_valid_number_with_junk_stapled_to_it_is_refused():
    """`cnpj_valid` strips every non-digit before it counts, so it says True for a valid number
    with a sentence after it. The SHAPE test is what stops that being stored as if it were clean."""
    assert not cnpj_is_acceptable(normalize_cnpj("11222333000181 e mais alguma coisa"))


def test_a_normaliser_that_deleted_LETTERS_would_store_a_lie():
    """"não sei" must not normalise to "" — "" means *not supplied*, so the contact who said
    they did not know would be recorded as a company with no CNPJ and told it succeeded."""
    assert normalize_cnpj("não sei") != ""
    assert not cnpj_is_acceptable(normalize_cnpj("não sei"))


# ── the key is the NAME, folded — which is this vertical's whole undo story ──────────────
def test_registering_the_same_company_again_UPDATES_one_row():
    svc = _svc()
    svc.register("Padaria São João", visual_identity="azul")
    svc.register("padaria sao joao", visual_identity="verde")
    rows = svc.list_companies()
    assert len(rows) == 1, "the accent-folded name is the key — this must not be two rows"
    assert rows[0].visual_identity == {"visual_identity": "verde"}


def test_a_name_that_folds_to_nothing_still_gets_a_deterministic_key():
    assert company_id_for("🎉!!!") == company_id_for("🎉!!!") != ""
    assert company_id_for("🎉!!!").startswith("c-")


def test_the_original_author_survives_a_correction():
    """A correction is not a new registration by a new person."""
    svc = _svc()
    svc.register("Acme", identity_id="u1")
    assert svc.register("Acme", identity_id="u2").created_by_user_id == "u1"


def test_an_empty_brand_field_is_left_OUT_rather_than_stored_blank():
    """So a later registration supplying only one does not read as "the other was cleared on
    purpose" — and a reader can tell "never given" from "given as blank"."""
    row = _svc().register("Acme", guidelines="tom formal")
    assert row.visual_identity == {"guidelines": "tom formal"}


# ── a store failure is REPORTED, never swallowed ─────────────────────────────────────────
class _BrokenStore(InMemoryCompanyStore):
    def upsert(self, company):
        raise RuntimeError("connection to 10.0.0.1 as role 'admin' failed")


def test_a_store_failure_is_refused_and_only_the_exception_CLASS_travels():
    """The message can carry the DSN, a role name or a column value, and this string ends up in
    the tool's output and from there in a turn trace."""
    with pytest.raises(CompanyError) as exc:
        CompanyService(_BrokenStore()).register("Acme")
    assert "RuntimeError" in str(exc.value)
    assert "10.0.0.1" not in str(exc.value) and "admin" not in str(exc.value)


def test_get_reads_back_what_register_wrote():
    svc = _svc()
    row = svc.register("Padaria Sol Nascente")
    assert svc.get(row.company_id) is not None
    assert svc.get("nao-existe") is None


def test_delete_removes_the_row_and_answers_whether_it_did():
    svc = _svc()
    row = svc.register("Acme")
    assert svc.store.delete(row.company_id) is True
    assert svc.store.delete(row.company_id) is False


def test_help_note_says_the_update_rule_the_model_must_know():
    assert "UPDATES" in _svc().help_note()


# ── cnpj_valid is a DUPLICATED CONTRACT — the host pins it against the core's copy ────────
#
# `cogno_anima.security.detector.cnpj_valid` is the original and cannot be imported here:
# cogno-praxis depends on `mcp` and nothing else, so a vertical that could only validate by
# importing the cognition library would have the dependency arrow backwards. The two copies are
# pinned against each other in the HOST, which has both on its path
# (`tests/unit/test_company_rules_match_the_core.py`). What is asserted HERE is the rule itself,
# so this side has its own definition of right and does not merely agree with whatever the
# other side happens to say.
@pytest.mark.parametrize("value,expected", [
    ("11222333000181", True),               # the checksum, straight
    ("11.222.333/0001-81", True),           # punctuation is stripped before counting
    ("11222333000199", False),              # both check digits wrong
    ("11222333000182", False),              # only the LAST digit wrong
    ("11222333000191", False),              # only the FIRST check digit wrong
    ("1122233300018", False),               # thirteen digits
    ("112223330001811", False),             # fifteen
    ("11111111111111", False),              # a repdigit passes the checksum and is still not one
    ("", False),
])
def test_cnpj_valid_is_the_check_digit_rule_and_not_a_shape_test(value, expected):
    from cogno_praxis.companies import cnpj_valid

    assert cnpj_valid(value) is expected


# ══════════════════════════════════════════════════════════════════════════════════════════
#  VISIBILITY — the vertical's half of the role policy
#
#  The policy has two halves and they live in different repos. WHICH TOOLS a role is handed is
#  the host's (`cogno_host/rbac.py::companies_rbac`); WHAT A ROLE SEES once it holds a tool is
#  this vertical's, and it is what these tests own. Neither half is sufficient: a host that
#  hands `company_search` to a GUEST is relying on this file to scope the answer, and this
#  file scoping the answer is worth nothing if the host hands out `company_delete`.
#
#  The rule: staff see the business's companies; anyone else sees the ones THEY registered.
#  `EMPLOYEE` counts as staff here and does NOT in the bookkeeper, and that difference is the
#  owner's rule rather than drift — a financial entry belongs to whoever recorded it, a
#  registered company belongs to the business.
# ══════════════════════════════════════════════════════════════════════════════════════════

def _peopled() -> CompanyService:
    svc = _svc()
    svc.register("Padaria Sol Nascente", identity_id="lead-1")
    svc.register("Acme", identity_id="lead-2")
    svc.register("Initech", identity_id="staff-1")
    return svc


@pytest.mark.parametrize("role", ["EMPLOYEE", "SUPERVISOR", "ADMIN"])
def test_staff_see_every_company_of_the_business(role):
    seen = _peopled().list_visible(identity_id="staff-1", role=role)
    assert {c.name for c in seen} == {"Padaria Sol Nascente", "Acme", "Initech"}


@pytest.mark.parametrize("role", ["GUEST", "", "   ", "VISITOR", "some-role-nobody-taught-us"])
def test_everyone_else_sees_only_what_they_registered(role):
    """An unknown role falls to the NARROWEST view — the direction a mistake has to take."""
    seen = _peopled().list_visible(identity_id="lead-1", role=role)
    assert [c.name for c in seen] == ["Padaria Sol Nascente"]


def test_a_scoped_caller_with_no_identity_sees_NOTHING_not_everything():
    """A blank id must not match every row whose author was also never recorded."""
    assert _peopled().list_visible(identity_id="", role="GUEST") == []


def test_a_guest_search_cannot_reach_another_leads_company():
    svc = _peopled()
    assert svc.search("Acme", identity_id="lead-1", role="GUEST") == []
    assert [c.name for c in svc.search("Acme", identity_id="lead-2", role="GUEST")] == ["Acme"]


def test_the_limit_is_SAID_and_is_not_an_error():
    """A refusal that leaves this vertical as an exception arrives at the contact as "não
    consegui acessar" — the voice reads a failure and apologises for the system instead of
    stating the boundary. So the reads answer normally and carry the limit in words."""
    svc = _peopled()
    note = svc.scope_note("lead-1", "GUEST")
    assert "cadastrou" in note
    assert svc.scope_note("staff-1", "ADMIN") == ""      # nothing to say to someone unscoped


def test_search_ignores_accents_and_case_the_same_way_the_key_does():
    svc = _svc()
    svc.register("Padaria São João", identity_id="u1")
    for q in ("padaria sao joao", "PADARIA SÃO JOÃO", "sao joao", "São"):
        assert [c.name for c in svc.search(q, identity_id="u1", role="GUEST")] == \
            ["Padaria São João"], q


def test_search_by_cnpj_matches_however_it_is_punctuated():
    svc = _svc()
    svc.register("Acme", cnpj=_CNPJ_OK, identity_id="u1")
    for q in ("11.222.333/0001-81", "11222333000181"):
        assert [c.name for c in svc.search(q, identity_id="u1", role="GUEST")] == ["Acme"], q


def test_an_empty_query_finds_nothing_rather_than_everything():
    """`company_search` is the tool whose result MOVES the host's company focus. An empty
    query returning the whole table would make a fumbled search choose a company."""
    assert _peopled().search("", identity_id="staff-1", role="ADMIN") == []


# ── writes: the scope is re-decided on the way IN, because the key is guessable ──────────
def test_a_guest_cannot_update_a_company_someone_else_registered():
    svc = _peopled()
    with pytest.raises(CompanyError, match="outra pessoa"):
        svc.update("acme", name="Roubada", identity_id="lead-1", role="GUEST")
    assert svc.get("acme").name == "Acme"


def test_a_guessable_id_is_why_the_write_check_is_not_a_formality():
    """`company_id` is derived from the accent-folded NAME, so anyone who knows a company is
    called "Acme" can write `acme` without ever having been able to SEE it. The scope has to
    be re-decided here rather than assumed from how the id was obtained."""
    svc = _peopled()
    assert svc.search("Acme", identity_id="lead-1", role="GUEST") == []   # cannot see it
    with pytest.raises(CompanyError):                                     # nor reach it
        svc.delete("acme", identity_id="lead-1", role="GUEST")
    assert svc.get("acme") is not None


def test_a_refusal_is_worded_as_a_LIMIT_even_though_it_raises():
    """The transport for a refused WRITE is an error and cannot be anything else: an ordinary
    text return from a mutating tool comes back as `ToolResult(ok=True, side_effect=True)`,
    which the host's `committed_this_turn` counts as a write that never happened. So the
    wording carries the limit."""
    with pytest.raises(CompanyError) as exc:
        _peopled().update("acme", name="X", identity_id="lead-1", role="GUEST")
    text = str(exc.value).lower()
    assert "só posso" in text and "cadastrou" in text
    assert "erro" not in text and "falha" not in text


@pytest.mark.parametrize("role", ["EMPLOYEE", "SUPERVISOR", "ADMIN"])
def test_staff_may_update_a_company_they_did_not_register(role):
    svc = _peopled()
    assert svc.update("acme", segment="varejo", identity_id="staff-1", role=role).segment == "varejo"


def test_update_applies_only_what_was_GIVEN():
    """A partial update that read "" as "clear this field" would erase the brand guidelines of
    every company whose name a caller merely corrected."""
    svc = _svc()
    svc.register("Acme", cnpj=_CNPJ_OK, visual_identity="azul", guidelines="tom formal",
                 identity_id="u1")
    row = svc.update("acme", segment="varejo", identity_id="u1", role="GUEST")
    assert row.cnpj == "11222333000181"
    assert row.visual_identity == {"visual_identity": "azul", "guidelines": "tom formal"}
    assert row.name == "Acme" and row.segment == "varejo"


def test_a_rename_keeps_the_KEY_and_the_history():
    """Re-keying on a rename would mean an insert plus an orphan — the same company twice."""
    svc = _svc()
    svc.register("Acme", identity_id="u1")
    row = svc.update("acme", name="Acme Tecnologia", identity_id="u1", role="GUEST")
    assert row.company_id == "acme" and row.name == "Acme Tecnologia"
    assert len(svc.list_companies()) == 1


def test_update_refuses_a_bad_cnpj_and_changes_nothing():
    svc = _svc()
    svc.register("Acme", cnpj=_CNPJ_OK, identity_id="u1")
    with pytest.raises(CompanyError, match="cnpj"):
        svc.update("acme", cnpj=_CNPJ_BAD, identity_id="u1", role="GUEST")
    assert svc.get("acme").cnpj == "11222333000181"


def test_update_of_an_unknown_company_says_to_search_first():
    with pytest.raises(CompanyError, match="[Bb]usque"):
        _svc().update("nao-existe", name="X", identity_id="u1", role="ADMIN")


# ── delete: two steps, and the first one commits nothing ────────────────────────────────
def test_delete_without_the_confirmation_reads_and_proposes():
    svc = _peopled()
    out = svc.delete("acme", identity_id="staff-1", role="ADMIN")
    assert out.removed is None
    assert out.proposal is not None and out.proposal.company.name == "Acme"
    assert out.proposal.confirm_company_id == "acme"
    assert svc.get("acme") is not None


def test_delete_with_the_WRONG_confirmation_still_commits_nothing():
    svc = _peopled()
    assert svc.delete("acme", identity_id="staff-1", role="ADMIN",
                      confirm_company_id="initech").removed is None
    assert svc.get("acme") is not None and svc.get("initech") is not None


def test_delete_with_the_id_it_named_removes_exactly_that_company():
    svc = _peopled()
    out = svc.delete("acme", identity_id="staff-1", role="ADMIN")
    gone = svc.delete("acme", identity_id="staff-1", role="ADMIN",
                      confirm_company_id=out.proposal.confirm_company_id).removed
    assert gone is not None and gone.company_id == "acme"
    assert {c.company_id for c in svc.list_companies()} == {"padaria-sol-nascente", "initech"}


# ── a store failure on the two later writes is REPORTED, never swallowed ─────────────────
class _BreaksOnWrite(InMemoryCompanyStore):
    """Registers fine, then fails — so the row exists to be updated/deleted when it breaks."""

    fail = False

    def upsert(self, company):
        if self.fail:
            raise RuntimeError("connection to 10.0.0.1 as role 'admin' failed")
        return super().upsert(company)

    def delete(self, company_id):
        if self.fail:
            raise RuntimeError("connection to 10.0.0.1 as role 'admin' failed")
        return super().delete(company_id)


def test_a_store_failure_on_UPDATE_is_refused_and_leaks_no_infrastructure():
    store = _BreaksOnWrite()
    svc = CompanyService(store)
    svc.register("Acme", identity_id="u1")
    store.fail = True
    with pytest.raises(CompanyError) as exc:
        svc.update("acme", segment="varejo", identity_id="u1", role="ADMIN")
    assert "RuntimeError" in str(exc.value)
    assert "10.0.0.1" not in str(exc.value) and "admin" not in str(exc.value)


def test_a_store_failure_on_DELETE_is_refused_and_leaks_no_infrastructure():
    store = _BreaksOnWrite()
    svc = CompanyService(store)
    svc.register("Acme", identity_id="u1")
    store.fail = True
    with pytest.raises(CompanyError) as exc:
        svc.delete("acme", identity_id="u1", role="ADMIN", confirm_company_id="acme")
    assert "RuntimeError" in str(exc.value)
    assert "10.0.0.1" not in str(exc.value)


def test_a_confirmed_delete_of_a_row_that_vanished_is_not_reported_as_a_removal():
    """Two callers, one row: the second confirmation must not answer "Removed" for a row that
    was already gone. `ok=False` is the honest answer — the alternative is a turn telling a
    person their company was deleted by THEM when it was not."""
    class _Vanishing(InMemoryCompanyStore):
        def delete(self, company_id):
            return False

    svc = CompanyService(_Vanishing())
    svc.register("Acme", identity_id="u1")
    with pytest.raises(CompanyError, match="já não estava"):
        svc.delete("acme", identity_id="u1", role="ADMIN", confirm_company_id="acme")


def test_update_replaces_one_brand_field_and_leaves_its_twin_alone():
    """The two brand strings share one jsonb, so a partial update has to MERGE into it rather
    than replace it — writing the dict wholesale would drop the field the caller did not
    mention, which is the same erasure the "only what was GIVEN" rule exists to stop."""
    svc = _svc()
    svc.register("Acme", visual_identity="azul", guidelines="tom formal", identity_id="u1")
    row = svc.update("acme", visual_identity="verde", identity_id="u1", role="ADMIN")
    assert row.visual_identity == {"visual_identity": "verde", "guidelines": "tom formal"}
    row = svc.update("acme", guidelines="tom informal", identity_id="u1", role="ADMIN")
    assert row.visual_identity == {"visual_identity": "verde", "guidelines": "tom informal"}
