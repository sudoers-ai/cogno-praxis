"""GENERIC markers and per-persona FIELD PROVIDERS (``cogno_praxis.email_fields``, E3).

A template belongs to a persona. Everything here is synthetic — invented names, an invented
school, an invented persona id. What is pinned, one line each:

* the list has two halves and the union is DERIVED: no marker in both, none lost, and a registry
  that could answer two ways is refused when it is built;
* every marker in use before E3 still validates and fills in the persona it was used in (one
  test per marker), and the three template SHAPES in use render byte for byte;
* a marker another persona supplies is REFUSED for this one, with both personas named — and the
  same template is valid for the persona that supplies it (the twin), and with no persona given;
* the new generic markers — ``[data]``, ``[assinatura]``, ``[solicitante]`` — fill from the
  host's half of the context alone, and each is a named ``Missing`` when that half is empty;
* a template of generic markers alone needs NO provider and NO month;
* the adversarial spellings: a specific marker in another case or spelling, another persona's
  id in another case, a persona with no provider, a marker that was deliberately not created.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
from datetime import date, datetime

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.email_fields import (
    EMAIL_FIELDS,
    FIELD_PROVIDERS,
    GENERIC_FIELDS,
    REFUSED_FIELDS,
    SUBJECT_FORBIDDEN,
    EmailContext,
    FieldProvider,
    FieldSpec,
    date_words,
    email_digest,
    fields_for,
    fill_email_fields,
    known_markers,
    provider_fields,
    provider_for,
    provider_of,
    render_email,
    template_fields,
    template_needs_month,
    validate_template,
)

ME = "Prof Alfa"                   # invented
SCHOOL = "Escola Exemplo"          # invented
ADDRESS = "alfa@captura.local"     # invented, under a capture domain
SIGNER = "Assistente Vexa"         # invented — a persona's display name
ASKER = "Coord Gama"               # invented — the person who asked
TODAY = date(2026, 10, 7)

COORD = "COORDINATOR"
#: Personas with no provider of their own: two the host ships and one nobody ships.
OTHERS = ("SECRETARY", "BOOKKEEPER", "ARCHIVIST")

#: The markers in use before E3, by the half they fall in. Typed HERE on purpose: this is the
#: regression list (what existed must go on existing), so it is not derived from the code.
LEGACY_GENERIC = ("nome", "email", "empresa", "mes", "conteudo")
LEGACY_COORDINATOR = ("disciplinas", "aulas", "valor_por_aula", "valores_por_bonus", "total")
NEW_GENERIC = ("data", "assinatura", "solicitante")

#: The three template SHAPES in use (text invented): a class schedule, the invoice notice, and
#: a general notice — the last one of generic markers alone.
T_SCHEDULE = ("Cronograma de aulas — [mes]",
              "Olá, [nome],\n\nSegue o seu cronograma de aulas de [mes] na [empresa]:\n\n"
              "[aulas]\n\nDisciplinas do mês:\n[disciplinas]\n\n[conteudo]\n\n"
              "Atenciosamente,\nCoordenação — [empresa]")
T_INVOICE = ("Emissão de nota fiscal — [mes] — [empresa]",
             "Olá, [nome],\n\nPara a sua nota fiscal de [mes] na [empresa]: valor por aula "
             "[valor_por_aula]; por nível de bônus:\n[valores_por_bonus]\n\nTotal: [total]\n\n"
             "Aulas consideradas:\n[aulas]")
T_NOTICE = ("Aviso — [mes]", "Olá, [nome],\n\n[conteudo]\n\nAtenciosamente,\n[empresa]")
#: A template only E3 can express: no month, no persona read, signed and dated.
T_GENERIC = ("Recado de [solicitante]",
             "[data]\n\nOlá, [nome],\n\n[conteudo]\n\nAtenciosamente,\n[assinatura]\n[empresa]")


def _host_half(**kw) -> EmailContext:
    """The context a host builds with NO persona read: nothing of the coordinator's in it."""
    base = dict(recipient_name=ME, recipient_email=ADDRESS, tenant_name=SCHOOL, month="2026-10",
                conteudo="Reunião na sexta.", today=TODAY, persona_name=SIGNER,
                requester_name=ASKER)
    base.update(kw)
    return EmailContext(**base)


# ── the two halves, and the union derived ────────────────────────────────────────────────────

def test_the_union_is_the_two_halves_and_no_marker_is_in_both():
    specific = [f.name for p in FIELD_PROVIDERS.values() for f in p.fields]
    assert len(specific) == len(set(specific))
    assert set(GENERIC_FIELDS).isdisjoint(specific)
    assert list(EMAIL_FIELDS) == list(GENERIC_FIELDS) + specific
    assert set(EMAIL_FIELDS).isdisjoint(REFUSED_FIELDS)
    # each provider is filed under its own persona, and names its fields as specs
    for persona, p in FIELD_PROVIDERS.items():
        assert p.persona == persona and p.name and p.label
        assert all(EMAIL_FIELDS[f.name] is f for f in p.fields)


def test_the_halves_are_exactly_the_ones_decided():
    assert tuple(GENERIC_FIELDS) == ("nome", "email", "empresa", "mes", "data", "assinatura",
                                     "solicitante", "conteudo")
    assert set(FIELD_PROVIDERS) == {COORD}
    assert FIELD_PROVIDERS[COORD].field_names == frozenset(LEGACY_COORDINATOR)
    assert FIELD_PROVIDERS[COORD].name == "coordinator"
    assert set(LEGACY_GENERIC) | set(NEW_GENERIC) == set(GENERIC_FIELDS)


def test_no_two_markers_differ_only_by_spelling():
    """``[valor_por_aula]`` and a would-be ``[valorporaula]`` are one name to a person."""
    def folded(name: str) -> str:
        return name.replace("_", "").casefold()
    names = list(EMAIL_FIELDS) + list(REFUSED_FIELDS)
    assert len({folded(n) for n in names}) == len(names)


def test_every_multiline_marker_is_kept_out_of_the_subject():
    assert {n for n, f in EMAIL_FIELDS.items() if f.multiline} <= SUBJECT_FORBIDDEN
    assert SUBJECT_FORBIDDEN <= set(EMAIL_FIELDS)
    assert ef._PAY_FIELDS <= ef._SCHEDULE_FIELDS and ef._NEEDS_CLASSES <= ef._SCHEDULE_FIELDS
    assert ef._SCHEDULE_FIELDS == FIELD_PROVIDERS[COORD].field_names


@pytest.mark.parametrize("clash, words", [
    (FieldProvider("ARCHIVIST", "archive", "arquivo", (FieldSpec("nome", "x"),)), "[nome]"),
    (FieldProvider("ARCHIVIST", "archive", "arquivo", (FieldSpec("cpf_cnpj", "x"),)), "[cpf_cnpj]"),
    (FieldProvider("ARCHIVIST", "archive", "arquivo", (FieldSpec("aulas", "x"),)), "[aulas]"),
    (FieldProvider("COORDINATOR", "archive", "arquivo", (FieldSpec("pasta", "x"),)), "twice"),
    (FieldProvider(" ", "archive", "arquivo", (FieldSpec("pasta", "x"),)), "blank"),
])
def test_a_registry_that_could_answer_two_ways_is_refused_when_built(clash, words):
    shipped = tuple(FIELD_PROVIDERS.values())
    with pytest.raises(ValueError) as err:
        ef._registry(GENERIC_FIELDS, shipped + (clash,))
    assert words in str(err.value)
    # CONTROL — the same builder accepts a provider that clashes with nothing.
    ok = FieldProvider("ARCHIVIST", "archive", "arquivo", (FieldSpec("pasta", "x"),))
    by_persona, fields = ef._registry(GENERIC_FIELDS, shipped + (ok,))
    assert set(by_persona) == {COORD, "ARCHIVIST"} and "pasta" in fields


# ── regression: what was in use still validates and fills where it was used ──────────────────

@pytest.mark.parametrize("marker", LEGACY_GENERIC + LEGACY_COORDINATOR)
def test_each_marker_in_use_before_E3_is_still_valid_for_the_coordinator(marker):
    assert marker in fields_for(COORD)
    assert validate_template("Aviso", f"Texto: [{marker}]", persona=COORD) == ()
    # …and for a caller that gives no persona (the reading from before E3)
    assert validate_template("Aviso", f"Texto: [{marker}]") == ()


@pytest.mark.parametrize("template", [T_SCHEDULE, T_INVOICE, T_NOTICE])
def test_the_three_template_shapes_in_use_are_valid_for_the_coordinator(template):
    assert validate_template(*template, persona=COORD) == ()
    assert validate_template(*template) == ()


@pytest.mark.parametrize("marker", LEGACY_GENERIC + NEW_GENERIC)
@pytest.mark.parametrize("persona", (COORD,) + OTHERS)
def test_each_generic_marker_is_valid_for_every_persona(marker, persona):
    assert validate_template("Aviso", f"Texto: [{marker}]", persona=persona) == ()


def test_the_generic_notice_renders_byte_for_byte_from_the_hosts_half_alone():
    """The shape already in use that has no persona-specific marker: it is composed from a
    context NO provider read anything into (no classes, no estimate), and needs none."""
    fields = template_fields(*T_NOTICE)
    assert provider_fields(fields) == {}
    ctx = _host_half()
    assert ctx.classes == () and ctx.estimate is None
    values, missing = fill_email_fields(fields, ctx)
    assert missing == ()
    out = render_email(*T_NOTICE, values)
    assert out == ("Aviso — outubro/2026",
                   "Olá, Prof Alfa,\n\nReunião na sexta.\n\nAtenciosamente,\nEscola Exemplo")
    assert email_digest(*out) == email_digest(*render_email(*T_NOTICE, values))


# ── the persona decides: another persona's marker is refused, by name ────────────────────────

@pytest.mark.parametrize("marker", LEGACY_COORDINATOR)
@pytest.mark.parametrize("persona", OTHERS)
def test_a_coordinator_marker_is_refused_for_another_persona_naming_both(marker, persona):
    (reason,) = validate_template("Aviso", f"Texto: [{marker}]", persona=persona)
    assert f"[{marker}] é um marcador da persona COORDINATOR (coordenação)" in reason
    assert f"a persona {persona} não o tem" in reason
    # the list it offers is THIS persona's: the generic markers, and no specific one
    offered = reason.split("os marcadores desta persona são ", 1)[1]
    assert offered == ", ".join(f"[{n}]" for n in GENERIC_FIELDS)
    # TWIN — the same template, the persona that supplies the marker.
    assert validate_template("Aviso", f"Texto: [{marker}]", persona=COORD) == ()


def test_the_schedule_template_is_refused_at_the_front_desk_and_saved_by_the_coordinator():
    reasons = validate_template(*T_SCHEDULE, persona="SECRETARY")
    assert [r.split(" é um marcador")[0] for r in reasons] == ["no corpo, [aulas]",
                                                               "no corpo, [disciplinas]"]
    assert all("a persona SECRETARY não o tem" in r for r in reasons)
    assert validate_template(*T_SCHEDULE, persona=COORD) == ()


def test_the_subject_names_the_other_personas_marker_too():
    reasons = validate_template("Total: [total]", "corpo", persona="BOOKKEEPER")
    assert reasons == (
        "no assunto, [total] é um marcador da persona COORDINATOR (coordenação); a persona "
        "BOOKKEEPER não o tem — os marcadores desta persona são "
        + ", ".join(known_markers("BOOKKEEPER")),)


@pytest.mark.parametrize("persona", (COORD,) + OTHERS + (None,))
def test_a_removed_marker_stays_refused_for_every_persona(persona):
    (cpf,) = validate_template("NF", "CPF: [cpf_cnpj]", persona=persona)
    assert "decisão do dono" in cpf
    (contract,) = validate_template("Contrato", "[contrato]", persona=persona)
    assert "fase E3" in contract
    # CONTROL — the same call with a marker that exists is valid.
    assert validate_template("NF", "Nome: [nome]", persona=persona) == ()


@pytest.mark.parametrize("persona", (COORD,) + OTHERS + (None,))
def test_an_unknown_marker_stays_refused_for_every_persona_listing_its_markers(persona):
    (reason,) = validate_template("Aviso", "Olá [nmoe]", persona=persona)
    assert "[nmoe] não é um marcador; os marcadores são " in reason
    assert reason.endswith(", ".join(known_markers(persona)))


# ── adversarial: spellings and ids that are NOT the case ─────────────────────────────────────

@pytest.mark.parametrize("body, words", [
    ("[Aulas]", "abre um «[» que não é marcador"),          # another case
    ("[AULAS]", "abre um «[» que não é marcador"),
    ("[ aulas ]", "abre um «[» que não é marcador"),        # padded
    ("[aula]", "[aula] não é um marcador"),                 # the singular
    ("[valorporaula]", "[valorporaula] não é um marcador"),  # no underscores
    ("[valor por aula]", "abre um «[» que não é marcador"),
    ("[datas]", "[datas] não é um marcador"),               # a generic one, misspelt
    ("[assinaturas]", "[assinaturas] não é um marcador"),
    ("[remetente]", "[remetente] não é um marcador"),       # deliberately NOT created
    ("[persona]", "[persona] não é um marcador"),
])
@pytest.mark.parametrize("persona", (COORD, "SECRETARY", None))
def test_a_near_miss_of_a_marker_is_not_that_marker(body, words, persona):
    reasons = validate_template("Aviso", body, persona=persona)
    assert len(reasons) == 1 and words in reasons[0], reasons
    assert "é um marcador da persona" not in reasons[0]


@pytest.mark.parametrize("persona", ["coordinator", "Coordinator", "COORDINATORS", "COORD",
                                     "COORDINATOR ", "", "   ", "ARCHIVIST"])
def test_a_persona_id_is_compared_as_written(persona):
    """An id that merely resembles the coordinator's does not inherit its markers — except for
    surrounding blanks, which are not part of an id."""
    exact = persona.strip() == COORD
    assert (provider_for(persona) is FIELD_PROVIDERS[COORD]) is exact
    assert ("aulas" in fields_for(persona)) is exact
    reasons = validate_template("Aviso", "[aulas]", persona=persona)
    assert (reasons == ()) is exact
    if not exact:
        who = f"a persona {persona.strip()}" if persona.strip() else "esta persona"
        assert f"{who} não o tem" in reasons[0]
    # every one of them has the generic markers
    assert validate_template("Aviso", "[nome] [data]", persona=persona) == ()


def test_only_None_is_the_reading_with_no_persona():
    assert fields_for(None) is EMAIL_FIELDS
    assert known_markers() == tuple(f"[{n}]" for n in EMAIL_FIELDS)
    assert set(fields_for("")) == set(GENERIC_FIELDS)
    assert provider_for(None) is None and provider_for(7) is None  # type: ignore[arg-type]
    assert provider_of("aulas") is FIELD_PROVIDERS[COORD]
    assert provider_of("nome") is None and provider_of("nmoe") is None


# ── the new generic markers ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("day, words", [
    (date(2026, 10, 7), "7 de outubro de 2026"),
    (date(2026, 10, 1), "1º de outubro de 2026"),
    (date(2026, 3, 11), "11 de março de 2026"),
    (date(2027, 12, 31), "31 de dezembro de 2027"),
    (datetime(2026, 1, 21, 23, 59), "21 de janeiro de 2026"),
])
def test_data_is_today_in_words(day, words):
    assert date_words(day) == words
    values, missing = fill_email_fields(("data",), _host_half(today=day, conteudo=""))
    assert values == {"data": words} and missing == ()


def test_the_generic_template_fills_from_the_hosts_half_and_renders_whole():
    assert validate_template(*T_GENERIC, persona="SECRETARY") == ()
    fields = template_fields(*T_GENERIC)
    assert provider_fields(fields) == {} and not template_needs_month(fields)
    values, missing = fill_email_fields(fields, _host_half(month=""))     # NO month given
    assert missing == ()
    assert render_email(*T_GENERIC, values) == (
        "Recado de Coord Gama",
        "7 de outubro de 2026\n\nOlá, Prof Alfa,\n\nReunião na sexta.\n\nAtenciosamente,\n"
        "Assistente Vexa\nEscola Exemplo")


@pytest.mark.parametrize("change, field, words", [
    ({"today": None}, "data", "não informou a data de hoje"),
    ({"today": "2026-10-07"}, "data", "não informou a data de hoje"),     # a string is no date
    ({"persona_name": "  "}, "assinatura", "não tem nome de exibição"),
    ({"requester_name": ""}, "solicitante", "não tem nome no cadastro"),
])
def test_each_new_marker_with_no_value_is_a_named_missing(change, field, words):
    fields = template_fields(*T_GENERIC)
    _, missing = fill_email_fields(fields, _host_half(**change))
    assert [m.field for m in missing] == [field], missing
    assert words in missing[0].reason
    assert missing[0].source == GENERIC_FIELDS[field].source
    # CONTROL — the complete context has none.
    assert fill_email_fields(fields, _host_half())[1] == ()


def test_the_signature_is_the_persona_and_the_requester_is_the_person_who_asked():
    values, missing = fill_email_fields(("assinatura", "solicitante", "nome"),
                                        _host_half(conteudo=""))
    assert missing == () and values == {"assinatura": SIGNER, "solicitante": ASKER, "nome": ME}


def test_a_marker_the_template_does_not_use_is_never_asked_for():
    """An empty clock, persona name or requester stops ONLY a template that quotes it."""
    bare = _host_half(today=None, persona_name="", requester_name="", month="")
    assert fill_email_fields(("nome", "empresa", "conteudo"), bare)[1] == ()


# ── the month, and which provider a template needs ───────────────────────────────────────────

@pytest.mark.parametrize("fields, needs", [
    (("nome", "empresa", "conteudo"), False),
    (("data", "assinatura", "solicitante", "email"), False),
    ((), False),
    (("mes",), True),
    (("nome", "mes"), True),
    (("aulas",), True),
    (("total",), True),
    (("nome", "valor_por_aula"), True),
])
def test_a_template_needs_a_month_only_when_it_says_one_or_uses_a_monthly_figure(fields, needs):
    assert template_needs_month(fields) is needs


@pytest.mark.parametrize("marker", LEGACY_COORDINATOR)
def test_every_coordinator_figure_is_about_one_month(marker):
    assert template_needs_month((marker,))
    _, missing = fill_email_fields((marker,), _host_half(month="", conteudo=""))
    assert [m.field for m in missing] == [marker]
    assert "sem um mês AAAA-MM" in missing[0].reason


def test_a_template_with_no_month_marker_never_asks_for_a_month():
    fields = ("nome", "data", "conteudo")
    assert fill_email_fields(fields, _host_half(month=""))[1] == ()
    # TWIN — the same request, a template that SAYS the month: now it is asked for.
    _, missing = fill_email_fields(fields + ("mes",), _host_half(month=""))
    assert [m.field for m in missing] == ["mes"]
    assert "não diz de que mês" in missing[0].reason


@pytest.mark.parametrize("template, wanted", [
    (T_NOTICE, {}),
    (T_GENERIC, {}),
    (T_SCHEDULE, {"coordinator": ("aulas", "disciplinas")}),
    (T_INVOICE, {"coordinator": ("valor_por_aula", "valores_por_bonus", "total", "aulas")}),
])
def test_provider_fields_names_the_reads_a_template_needs(template, wanted):
    assert provider_fields(template_fields(*template)) == wanted


def test_provider_fields_ignores_what_is_not_a_marker():
    assert provider_fields(("nome", "nmoe", "cpf_cnpj", "aulas", "aulas")) == {
        "coordinator": ("aulas",)}


def test_a_coordinator_marker_on_a_context_nobody_read_is_missing_never_blank():
    """The floor under the host's wiring: a specific marker filled from the host's half alone
    stops the send with a question — it never renders as an empty list."""
    _, missing = fill_email_fields(("nome", "aulas"), _host_half(conteudo=""))
    assert [m.field for m in missing] == ["aulas"]
    assert f"não encontro aulas de {ME} em 10/2026" in missing[0].reason
    with pytest.raises(ValueError):
        render_email("Aviso", "[aulas]", {"nome": ME})


# ── structure: a provider declares, it does not read ─────────────────────────────────────────

def test_the_module_imports_no_service():
    """``email_fields`` declares what a persona supplies; reading it is the host's wiring. Its
    only import inside the package is the coordinator's PURE pay formatting."""
    tree = ast.parse(pathlib.Path(ef.__file__).read_text(encoding="utf-8"))
    inside = sorted({n.module for n in ast.walk(tree)
                     if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("cogno_")}
                    | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                       for a in n.names if a.name.startswith("cogno_")})
    assert inside == ["cogno_praxis.coordinator.pay"]


def test_the_readme_documents_both_halves_and_the_new_markers():
    root = pathlib.Path(ef.__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8").split(
        "### Templated e-mail fields", 1)[1].split("\n**Prompt-only personas.**", 1)[0]
    for marker in known_markers():
        assert marker in readme, marker
    for name in ("GENERIC_FIELDS", "FIELD_PROVIDERS", "provider_fields", "template_needs_month",
                 "persona="):
        assert name in readme, name


def test_EmailContext_keeps_its_defaults_so_a_pre_E3_caller_still_builds_one():
    ctx = EmailContext(month="2026-10")
    assert (ctx.today, ctx.persona_name, ctx.requester_name) == (None, "", "")
    assert dataclasses.replace(ctx, today=TODAY).today == TODAY
