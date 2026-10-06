"""Templated e-mail fields (``cogno_praxis.email_fields``) and the ONE read that fills them
(``CoordinatorService.email_context``).

Everything here is synthetic: invented professors, an invented school, invented ids and round
figures chosen so a wrong multiplication shows by eye. What is pinned, one line each:

* the template validator refuses each bad shape, and the SAME template corrected passes;
* the marker list has ONE definition, and the prose that documents it cites nothing outside it;
* every field that cannot be filled is a named ``Missing``, and a complete context has none;
* ``[aulas]`` and the pay figures come off the SAME rows — ``classes × hours × rate == base``,
  past days of the month included (the listing hides them; the e-mail must not);
* ``[valores_por_bonus]`` lists the DECLARED bands in all four bonus worlds, marking a band only
  when the bonus is determined;
* the render is byte-for-byte over the owner's two template shapes, deterministic, and one pass.
"""

from __future__ import annotations

import dataclasses
import pathlib
from datetime import date

import pytest

from cogno_praxis.coordinator import CoordinatorConfig, CoordinatorService, InMemorySpreadsheetStore
from cogno_praxis.email_fields import (
    EMAIL_FIELDS,
    MAX_BODY_CHARS,
    MAX_CONTEUDO_CHARS,
    REFUSED_FIELDS,
    SUBJECT_FORBIDDEN,
    EmailClass,
    EmailContext,
    email_digest,
    fill_email_fields,
    known_markers,
    markers_cited,
    month_words,
    render_email,
    template_fields,
    validate_template,
)

AA = "A" * 24
BB = "B" * 24
ME = "Prof Alfa"                  # invented
OTHER = "Prof Beta"               # invented
SCHOOL = "Escola Exemplo"         # invented
ADDRESS = "alfa@captura.local"    # invented, under a capture domain

_RULES = f"""SPREADSHEETS:
Turma AA_01 = {AA}
Turma BB_02 = {BB}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:F110"
TAB_IBOPE: "Resultados IBOPE"
COLUMN_IBOPE: "Resultado"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
COLUMN_TIME: "Hora"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
"""
_BONUS = "IBOPE_BONUS: 80-89=30; 90+=40\n"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Hora"]
_SCHEDULE_AA = [
    _HEADER,
    ["05/09/2026", "Sab", ME, "Bancos NoSQL", "Verde", "08:00"],
    ["12/09/2026", "Sab", ME, "Bancos NoSQL", "Verde", "08:00"],
    ["19/09/2026", "Sab", OTHER, "Bancos NoSQL", "Verde", "08:00"],
    ["26/09/2026", "Sab", ME, "Estatistica Aplicada", "Verde", ""],
    ["03/10/2026", "Sab", ME, "Estatistica Aplicada", "Verde", "13:30"],
]
_SCHEDULE_BB = [
    _HEADER,
    ["19/09/2026", "Sab", ME, "Bancos NoSQL", "Azul", "13:30"],
]
#: Mid-September: two of the professor's September classes are already in the PAST.
_TODAY = date(2026, 9, 20)


def _svc(*, bonus: bool = True, ibope: "str | None" = None, rules_extra: str = "",
         pay: bool = True) -> CoordinatorService:
    rules = _RULES + (_BONUS if bonus else "") + rules_extra
    if not pay:
        rules = rules.replace("PAY_RATE_PER_HOUR: 120,00\n", "")
    store = InMemorySpreadsheetStore()
    store.put(AA, "Secretaria", _SCHEDULE_AA)
    store.put(BB, "Secretaria", _SCHEDULE_BB)
    rows = [["Professor", "Resultado"]] + ([[ME, ibope]] if ibope is not None else [])
    store.put(AA, "Resultados IBOPE", rows)
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: _TODAY)


def _ctx(svc: "CoordinatorService | None" = None, *, month: str = "2026-09", role: str = "EMPLOYEE",
         professor: str = "", conteudo: str = "", **kw) -> EmailContext:
    svc = svc or _svc()
    c = svc.email_context(professor=professor, role=role, identity_label=ME, period=month)
    return dataclasses.replace(c, recipient_name=ME, recipient_email=ADDRESS,
                               tenant_name=SCHOOL, conteudo=conteudo, **kw)


# The owner's two templates, in their SHAPE (2026-10-06): a class schedule, and the
# informative e-mail for the invoice the professor issues. Text and names invented.
T_SCHEDULE = ("Cronograma de aulas — [mes]",
              "Olá, [nome],\n\nSegue o seu cronograma de aulas de [mes] na [empresa]:\n\n"
              "[aulas]\n\nDisciplinas do mês:\n[disciplinas]\n\n[conteudo]\n\n"
              "Atenciosamente,\nCoordenação — [empresa]")
T_INVOICE = ("Emissão de nota fiscal — [mes]",
             "Olá, [nome],\n\nPara a sua nota fiscal de [mes], estes são os valores estimados por "
             "nível de bônus (valor por aula: [valor_por_aula]):\n\n[valores_por_bonus]\n\n"
             "Aulas consideradas:\n[aulas]\n\nAtenciosamente,\n[empresa]")


# ── validate_template: each refusal, and the same template corrected ─────────────────────────

@pytest.mark.parametrize("bad, fixed, words", [
    (("Aulas", "Olá [nmoe]"), ("Aulas", "Olá [nome]"), "[nmoe] não é um marcador"),
    (("Aulas", "Olá [Nome]"), ("Aulas", "Olá [nome]"), "não é marcador"),
    (("Aulas", "valor [ em aberto"), ("Aulas", "valor em aberto"), "não é marcador"),
    (("Aulas", "[conteudo] e [conteudo]"), ("Aulas", "[conteudo] e mais"), "aparece 2 vezes"),
    (("[conteudo]", "corpo [nome]"), ("Aviso", "corpo [nome] [conteudo]"), "assunto"),
    (("Aulas [aulas]", "corpo"), ("Aulas [mes]", "corpo"), "não pode ir no assunto"),
    (("Contrato", "Anexo: [contrato]"), ("Contrato", "Anexo em breve"), "fase E3"),
    (("NF", "CPF: [cpf_cnpj]"), ("NF", "Nome: [nome]"), "decisão do dono"),
    (("", "corpo"), ("Assunto", "corpo"), "o assunto está vazio"),
    (("Assunto", "   "), ("Assunto", "corpo"), "o corpo está vazio"),
    (("Assunto", "x" * (MAX_BODY_CHARS + 1)), ("Assunto", "x" * MAX_BODY_CHARS), "o máximo é"),
    (("Linha 1\nLinha 2", "corpo"), ("Linha 1", "corpo"), "uma linha só"),
])
def test_each_refusal_and_the_same_template_corrected_passes(bad, fixed, words):
    reasons = validate_template(*bad)
    assert reasons and any(words in r for r in reasons), reasons
    assert validate_template(*fixed) == ()


def test_an_unknown_marker_refusal_lists_the_markers_that_exist():
    (reason,) = validate_template("Aulas", "Olá [nmoe]")
    for marker in known_markers():
        assert marker in reason


def test_the_owners_two_templates_are_valid():
    assert validate_template(*T_SCHEDULE) == ()
    assert validate_template(*T_INVOICE) == ()


def test_contrato_opens_in_E3_and_cpf_never_does():
    assert validate_template("Contrato", "[contrato]", phase="E3") == ()
    assert validate_template("NF", "[cpf_cnpj]", phase="E3")
    with pytest.raises(ValueError):
        validate_template("x", "y", phase="E9")


# ── one definition ───────────────────────────────────────────────────────────────────────────

def test_the_list_is_derived_once_and_the_docs_cite_nothing_outside_it():
    """The molde of ``test_code_domains_match_prompt_domains_exactly``: the doc that explains the
    markers is checked AGAINST the list, so a marker added to the prose and not to the code (or
    the other way round) fails here."""
    import cogno_praxis.email_fields as ef
    # ``[nmoe]`` is the docs' deliberate counter-example — the typo the validator exists to catch.
    allowed = set(EMAIL_FIELDS) | set(REFUSED_FIELDS) | {"nmoe"}
    root = pathlib.Path(ef.__file__).resolve().parents[1]
    whole = (root / "README.md").read_text(encoding="utf-8")
    head = "### Templated e-mail fields"
    assert head in whole, "the README section on templated e-mail is missing"
    readme = whole.split(head, 1)[1].split("\n**Prompt-only personas.**", 1)[0]
    for text in (ef.__doc__ or "", readme):
        stray = [m for m in markers_cited(text) if m not in allowed]
        assert stray == [], stray
    # every listed marker is documented in the README, by name
    for marker in known_markers():
        assert marker in readme, marker
    assert SUBJECT_FORBIDDEN <= set(EMAIL_FIELDS)


def test_template_fields_are_in_order_of_first_use_subject_first():
    assert template_fields("[mes] — [nome]", "[aulas] [nome] [mes] [total]") == (
        "mes", "nome", "aulas", "total")


# ── fill: each Missing, and the complete context ─────────────────────────────────────────────

def _fill(template, ctx):
    return fill_email_fields(template_fields(*template), ctx)


def test_the_complete_context_has_no_missing_field():
    for template in (T_SCHEDULE, T_INVOICE):
        values, missing = _fill(template, _ctx(_svc(ibope="92"), conteudo="Bom mês!"))
        assert missing == () or (template is T_INVOICE and [m.field for m in missing] == ["conteudo"])
    values, missing = _fill(T_INVOICE, _ctx(_svc(ibope="92")))
    assert missing == ()
    assert set(values) == set(template_fields(*T_INVOICE))


@pytest.mark.parametrize("change, field, words", [
    ({"recipient_name": ""}, "nome", "não tem nome no cadastro"),
    ({"recipient_email": ""}, "email", "não tem e-mail no cadastro"),
    ({"tenant_name": ""}, "empresa", "o tenant não tem nome"),
    ({"conteudo": ""}, "conteudo", "não trouxe o texto"),
    ({"conteudo": "x" * (MAX_CONTEUDO_CHARS + 1)}, "conteudo", "o máximo é"),
])
def test_each_missing_field_names_itself_and_its_source(change, field, words):
    ctx = dataclasses.replace(_ctx(conteudo="Bom mês!"), **change)
    _, missing = _fill(T_SCHEDULE, ctx)
    assert [m.field for m in missing] == [field], missing
    assert words in missing[0].reason
    assert missing[0].source == EMAIL_FIELDS[field].source


def test_the_address_STOPS_the_send_even_when_the_body_never_quotes_it():
    ctx = dataclasses.replace(_ctx(conteudo="x"), recipient_email="")
    assert "email" not in template_fields(*T_SCHEDULE)
    _, missing = _fill(T_SCHEDULE, ctx)
    assert [m.field for m in missing] == ["email"]


def test_free_text_for_a_template_with_no_room_for_it_is_refused():
    values, missing = _fill(T_INVOICE, _ctx(_svc(ibope="92"), conteudo="um recado"))
    assert [m.field for m in missing] == ["conteudo"]
    assert "não tem espaço para texto livre" in missing[0].reason


@pytest.mark.parametrize("month, words", [("", "não diz de que mês"),
                                          ("setembro", "não é AAAA-MM"),
                                          ("2026-13", "não é AAAA-MM")])
def test_a_month_that_is_not_YYYY_MM_is_missing_and_reads_nothing(month, words):
    _, missing = _fill(T_SCHEDULE, _ctx(month=month, conteudo="x"))
    by = {m.field: m.reason for m in missing}
    assert words in by["mes"]
    assert "aulas" in by and "disciplinas" in by          # nothing was read for no month


def test_a_month_with_no_classes_asks_instead_of_sending_an_empty_list():
    _, missing = _fill(T_INVOICE, _ctx(_svc(ibope="92"), month="2026-11"))
    by = {m.field: m.reason for m in missing}
    assert set(by) == {"aulas", "valores_por_bonus"}
    assert f"não encontro aulas de {ME} em 11/2026" in by["aulas"]
    # PAIR — the same template, the month that HAS classes, fills.
    assert _fill(T_INVOICE, _ctx(_svc(ibope="92"), month="2026-09"))[1] == ()


def test_undeclared_pay_is_missing_with_the_verticals_own_sentence():
    ctx = _ctx(_svc(pay=False, ibope="92"))
    _, missing = _fill(T_INVOICE, ctx)
    by = {m.field: m.reason for m in missing}
    assert set(by) == {"valor_por_aula", "valores_por_bonus"}
    assert "PAY_RATE_PER_HOUR" in by["valor_por_aula"]
    assert by["valor_por_aula"] == ctx.pay_error            # not wrapped in another sentence
    # the classes were still read — the schedule half does not depend on the pay rules
    assert _fill(T_SCHEDULE, dataclasses.replace(ctx, conteudo="x"))[1] == ()


def test_an_access_refusal_is_missing_with_the_verticals_own_sentence():
    ctx = _ctx(professor=OTHER, role="EMPLOYEE", conteudo="x")
    assert ctx.schedule_error and ctx.classes == ()
    _, missing = _fill(T_SCHEDULE, ctx)
    assert {m.field for m in missing} == {"aulas", "disciplinas"}
    assert all(m.reason == ctx.schedule_error for m in missing)
    # CONTROL — the oversight role may name the other professor and reads HIS classes.
    sup = _svc().email_context(professor=OTHER, role="SUPERVISOR", identity_label=ME,
                               period="2026-09")
    assert sup.schedule_error == "" and [c.when for c in sup.classes] == [date(2026, 9, 19)]


def test_a_sheet_that_failed_to_read_stops_every_schedule_field():
    svc = _svc(ibope="92")

    class _Broken(InMemorySpreadsheetStore):
        def read_range(self, sheet_id, tab, a1_range):  # a store that fails one sheet
            if sheet_id == BB:
                raise RuntimeError("boom")
            return super().read_range(sheet_id, tab, a1_range)

    broken = _Broken()
    broken.put(AA, "Secretaria", _SCHEDULE_AA)
    broken.put(BB, "Secretaria", _SCHEDULE_BB)
    svc = CoordinatorService(broken, svc.cfg, today=lambda: _TODAY)
    ctx = _ctx(svc)
    assert "não puderam ser lidas" in ctx.schedule_error and "Turma BB_02" in ctx.schedule_error
    _, missing = _fill(T_INVOICE, ctx)
    assert {m.field for m in missing} == {"aulas", "valor_por_aula", "valores_por_bonus"}


# ── ONE read: the classes listed are the classes paid ────────────────────────────────────────

def test_M1_the_listed_classes_sum_to_the_estimates_base_past_days_included():
    svc = _svc(ibope="92")
    ctx = _ctx(svc)
    est = ctx.estimate
    assert est is not None
    values, missing = fill_email_fields(("aulas",), ctx)
    lines = values["aulas"].splitlines()
    assert len(lines) == len(ctx.classes) == 4
    assert len(lines) * est.hours_per_class * est.rate == est.base == 1920.0
    # the same professor through the pay tool: the SAME base
    assert svc.estimate_professor_pay(identity_label=ME, period="2026-09").base == est.base
    # PAIR — the listing of the same month hides the two classes already given (today = 20/09),
    # which is exactly the read that must NOT feed an e-mail about the month.
    listed = svc.get_professor_schedule(identity_label=ME, role="EMPLOYEE", month="2026-09")
    assert len(listed) < len(lines)


def test_aulas_are_chronological_and_never_invent_an_hour():
    values, _ = fill_email_fields(("aulas", "disciplinas"), _ctx())
    assert values["aulas"] == ("05/09 08:00 — Bancos NoSQL — Turma AA_01\n"
                               "12/09 08:00 — Bancos NoSQL — Turma AA_01\n"
                               "19/09 13:30 — Bancos NoSQL — Turma BB_02\n"
                               "26/09 — Estatistica Aplicada — Turma AA_01")
    assert values["disciplinas"] == "Bancos NoSQL\nEstatistica Aplicada"


# ── [valores_por_bonus] and [total] in the four bonus worlds ─────────────────────────────────

_LINES = ["Sem bônus: R$ 1.920,00", "IBOPE 80–89%: R$ 2.400,00", "IBOPE 90%+: R$ 2.560,00"]


@pytest.mark.parametrize("ibope, marked, total", [
    ("92", 2, "R$ 2.560,00"),        # applied — the 90+ band
    ("85", 1, "R$ 2.400,00"),        # applied — the 80–89 band
    ("71", 0, "R$ 1.920,00"),        # below — «Sem bônus» is the apurado line
    ("89,5", None, None),            # gap — no line marked, total undetermined
    (None, None, None),              # not found — no line marked, total undetermined
])
def test_the_declared_bands_always_and_a_mark_only_when_determined(ibope, marked, total):
    ctx = _ctx(_svc(ibope=ibope))
    values, missing = fill_email_fields(("valores_por_bonus", "total"), ctx)
    lines = values["valores_por_bonus"].splitlines()
    assert [ln.split(" ← ")[0] for ln in lines] == _LINES
    marks = [i for i, ln in enumerate(lines) if "← apurado" in ln]
    if marked is None:
        assert marks == []
        assert [m.field for m in missing] == ["total"]
        assert "o bônus ainda não está apurado" in missing[0].reason
    else:
        assert marks == [marked]
        assert lines[marked].endswith(f"← apurado (IBOPE {ibope.replace(',', '.')}%)")
        assert values["total"] == total and missing == ()


def test_no_declared_band_is_missing_for_the_bands_and_the_base_is_the_total():
    values, missing = fill_email_fields(("valores_por_bonus", "total"), _ctx(_svc(bonus=False)))
    assert [m.field for m in missing] == ["valores_por_bonus"]
    assert values["total"] == "R$ 1.920,00"


def test_the_response_rate_condition_follows_the_bands():
    ctx = _ctx(_svc(ibope="92", rules_extra="IBOPE_MIN_RESPONSE_PCT: 30\n"))
    values, _ = fill_email_fields(("valores_por_bonus",), ctx)
    assert values["valores_por_bonus"].endswith(
        "Condição das regras: o bônus só é devido se o IBOPE tiver sido respondido por pelo "
        "menos 30% da turma. Este sistema não lê essa taxa — confirme com a secretaria antes de "
        "contar com o adicional.")


# ── render: byte for byte, deterministic, one pass ───────────────────────────────────────────

_EXPECTED_SCHEDULE = (
    "Cronograma de aulas — setembro/2026",
    "Olá, Prof Alfa,\n\nSegue o seu cronograma de aulas de setembro/2026 na Escola Exemplo:\n\n"
    "05/09 08:00 — Bancos NoSQL — Turma AA_01\n12/09 08:00 — Bancos NoSQL — Turma AA_01\n"
    "19/09 13:30 — Bancos NoSQL — Turma BB_02\n26/09 — Estatistica Aplicada — Turma AA_01\n\n"
    "Disciplinas do mês:\nBancos NoSQL\nEstatistica Aplicada\n\n"
    "Lembre de confirmar a sala.\n\nAtenciosamente,\nCoordenação — Escola Exemplo")
_EXPECTED_INVOICE = (
    "Emissão de nota fiscal — setembro/2026",
    "Olá, Prof Alfa,\n\nPara a sua nota fiscal de setembro/2026, estes são os valores estimados "
    "por nível de bônus (valor por aula: R$ 480,00):\n\n"
    "Sem bônus: R$ 1.920,00\nIBOPE 80–89%: R$ 2.400,00\n"
    "IBOPE 90%+: R$ 2.560,00 ← apurado (IBOPE 92%)\n\n"
    "Aulas consideradas:\n05/09 08:00 — Bancos NoSQL — Turma AA_01\n"
    "12/09 08:00 — Bancos NoSQL — Turma AA_01\n19/09 13:30 — Bancos NoSQL — Turma BB_02\n"
    "26/09 — Estatistica Aplicada — Turma AA_01\n\nAtenciosamente,\nEscola Exemplo")


@pytest.mark.parametrize("template, conteudo, expected", [
    (T_SCHEDULE, "Lembre de confirmar a sala.", _EXPECTED_SCHEDULE),
    (T_INVOICE, "", _EXPECTED_INVOICE),
])
def test_render_byte_for_byte_and_deterministic(template, conteudo, expected):
    shas = set()
    for _ in range(2):
        values, missing = _fill(template, _ctx(_svc(ibope="92"), conteudo=conteudo))
        assert missing == ()
        out = render_email(*template, values)
        assert out == expected
        shas.add(email_digest(*out))
    assert len(shas) == 1


def test_render_is_ONE_pass_a_marker_inside_a_value_stays_text():
    out = render_email("Aviso [mes]", "Recado: [conteudo]",
                       {"mes": "setembro/2026", "conteudo": "o [total] e o [nome]"})
    assert out == ("Aviso setembro/2026", "Recado: o [total] e o [nome]")
    # ...and the subject the same way: a NAME that looks like a marker stays the name.
    assert render_email("Para [nome]", "x", {"nome": "o [total]"}) == ("Para o [total]", "x")


def test_render_refuses_a_marker_with_no_value_and_a_multiline_subject():
    with pytest.raises(ValueError):
        render_email("Aviso", "[total]", {})
    with pytest.raises(ValueError):
        render_email("Aviso [mes]", "x", {"mes": "a\nb"})


def test_the_digest_is_of_subject_newline_body():
    import hashlib
    assert email_digest("a", "b") == hashlib.sha256(b"a\nb").hexdigest()
    assert month_words("2026-10") == "outubro/2026" and month_words("10") == ""


def test_a_caller_with_no_identity_is_refused_and_a_named_one_is_not():
    from cogno_praxis.coordinator import CoordinatorAccessError
    with pytest.raises(CoordinatorAccessError):
        _svc().email_context(identity_label="  ", role="SUPERVISOR", period="2026-09")
    assert _svc().email_context(identity_label=ME, role="SUPERVISOR", period="2026-09").classes


def test_EmailClass_is_what_the_context_carries():
    ctx = _ctx()
    assert all(isinstance(c, EmailClass) for c in ctx.classes)
