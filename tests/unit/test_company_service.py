"""The ``company`` vertical's domain rules — a refused write never lands, a re-registration updates.

Ported with the code from the host's ``company_registration`` skill (2026-09-06). The rules are
asserted here rather than re-derived: an empty name and an unacceptable CNPJ are refusals BEFORE
the store is touched, and the row's key is derived from the accent-folded name so registering
the same company twice UPDATES one row.
"""

from __future__ import annotations

import pytest

from cogno_praxis.company import (
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
    from cogno_praxis.company import cnpj_valid

    assert cnpj_valid(value) is expected
