"""The HTML form of a templated e-mail (``render_email_html``), the tenant's appearance, and the
TEXT form — which moves only where the owner asked.

The owner's order (2026-10-22): an e-mail that carries specific data goes out readable at a
glance — HTML beside a text part that says the same — and, from his model e-mail, the classes in a
table PER CLASS GROUP with the weekday, a colour per discipline, the tenant's text as paragraphs,
lists and section titles, and the tenant's signature block. What is pinned here, one line each:

* R-T13 (2026-10-22): the coordination's values are the tenant's FREE tags, filled from records
  the coordination COPIES from its tools — every context here is built that way (``_ctx``: the
  real tools, then the scripted executor of ``test_the_coordination_by_the_generic_path.py``,
  which also holds the corpus proof that the generic path is the provider's text byte for byte);
  the ``[aulas]`` text (a «Turma X» block per class group, «06/10 (ter) 19:00 — Disciplina») is
  pinned by value;
* ``[aulas]`` is one table per class group under its title, in code order, Mês · Dia · Data ·
  Horário (when the group has an hour) · Disciplina; a discipline's colour is the same everywhere
  in the e-mail, by order of first appearance, the tenant's accent first;
* the body is simple rich text: paragraphs, «•»/«·» lists («-» stays a line), short «…:» titles,
  the tenant's URLs as links — and nothing else becomes markup;
* the appearance's SAVE door refuses every URL that is not ``http``/``https`` (``javascript:``,
  ``data:`` …), with a control; the signature is drawn in the HTML and written in the text alike;
* a template whose body carries no list of records renders NO HTML (``""``): the send stays
  plain text — a figure alone, bold by its name until R-T13, included;
* the document's elements and attributes are a closed alphabet; the only images are the ones the
  appearance configured, and every link is ``http``/``https``/``mailto``.

Everything here is synthetic: invented professors, an invented school, invented ids.
"""

from __future__ import annotations

import dataclasses
import html
import random
import re
from datetime import date
from html.parser import HTMLParser

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.coordinator import CoordinatorConfig, CoordinatorService, InMemorySpreadsheetStore
from tests.unit.test_the_coordination_by_the_generic_path import FIVE, _executor, _reads
from cogno_praxis.email_fields import (
    DEFAULT_PALETTE,
    EmailAppearance,
    EmailContext,
    SocialLink,
    as_records,
    email_signature_text,
    fill_email_fields,
    normalise_email_appearance,
    parse_email_appearance,
    record_colors,
    records_html,
    records_text,
    render_email,
    render_email_forms,
    render_email_html,
    template_fields,
)

SHEET_X = "X" * 24
SHEET_Y = "Y" * 24
PROF = "Prof Quintino"            # invented
COLLEAGUE = "Prof Ubaldo"          # invented
SCHOOL = "Colégio Horizonte"      # invented
ADDRESS = "quintino@captura.local"  # invented, under a capture domain

_RULES = f"""SPREADSHEETS:
Turma XA_01 = {SHEET_X}
Turma YB_02 = {SHEET_Y}

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


def _schedule_x(subject_a: str = "Redes de Computadores", time_last: str = "",
                extra: "tuple[list, ...]" = ()) -> list:
    return [
        _HEADER,
        ["05/09/2026", "Sab", PROF, subject_a, "Verde", "08:00"],
        ["12/09/2026", "Sab", PROF, subject_a, "Verde", "08:00"],
        ["19/09/2026", "Sab", COLLEAGUE, subject_a, "Verde", "08:00"],
        ["26/09/2026", "Sab", PROF, "Cálculo Numérico", "Verde", time_last],
        ["03/10/2026", "Sab", PROF, "Cálculo Numérico", "Verde", "13:30"],
        *extra,
    ]


#: A day with three classes — one with no hour, one listed out of order — and two disciplines whose
#: case-folded order is not their code-point order («banco…» after «Zoologia» by code point).
_SAME_DAY = (["12/09/2026", "Sab", PROF, "banco de dados", "Verde", ""],
             ["12/09/2026", "Sab", PROF, "Zoologia Aplicada", "Verde", "10:00"])

_SCHEDULE_Y = [_HEADER, ["19/09/2026", "Sab", PROF, "Redes de Computadores", "Azul", "13:30"]]
_TODAY = date(2026, 9, 20)


def _svc(*, bonus: bool = True, ibope: "str | None" = None, rules_extra: str = "",
         subject_a: str = "Redes de Computadores", time_last: str = "",
         extra: "tuple[list, ...]" = ()) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(SHEET_X, "Secretaria", _schedule_x(subject_a, time_last, extra))
    store.put(SHEET_Y, "Secretaria", _SCHEDULE_Y)
    rows = [["Professor", "Resultado"]] + ([[PROF, ibope]] if ibope is not None else [])
    store.put(SHEET_X, "Resultados IBOPE", rows)
    rules = _RULES + (_BONUS if bonus else "") + rules_extra
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: _TODAY)


def _ctx(svc: "CoordinatorService | None" = None, *, month: str = "2026-09",
         conteudo: str = "", **kw) -> EmailContext:
    """The context the coordination composes from since R-T13: the tenant declares the five as
    FREE tags, and the values are what the persona COPIED from its two tools this turn. A test's
    own ``custom_tags``/``free_tag_values`` are added to those."""
    svc = svc or _svc()
    sched, pay = _reads(svc, month)
    values = _executor(sched, pay, month)
    tags = {n: "" for n in FIVE}
    tags.update(kw.pop("custom_tags", {}))
    values.update(kw.pop("free_tag_values", {}))
    return EmailContext(recipient_name=PROF, recipient_email=ADDRESS, tenant_name=SCHOOL,
                        month=month, conteudo=conteudo, today=_TODAY, persona_name="Coordenação",
                        requester_name="Prof Ubaldo", custom_tags=tags, free_tag_values=values,
                        **kw)


def _records(ctx: EmailContext, name: str = "aulas") -> "list[dict[str, str]]":
    return list(ctx.free_tag_values[name])  # type: ignore[arg-type]


# The owner's template SHAPES (2026-10-06), text invented: the class schedule, the invoice e-mail;
# and two more — the total alone, and a template of generic markers only.
T_SCHEDULE = ("Cronograma de aulas — [mes]",
              "Olá, [nome],\n\nSegue o seu cronograma de aulas de [mes] na [empresa]:\n\n"
              "[aulas]\n\nDisciplinas do mês:\n[disciplinas]\n\n[conteudo]\n\n"
              "Atenciosamente,\nCoordenação — [empresa]")
T_INVOICE = ("Emissão de nota fiscal — [mes]",
             "Olá, [nome],\n\nPara a sua nota fiscal de [mes], estes são os valores estimados por "
             "nível de bônus (valor por aula: [valor_por_aula]):\n\n[valores_por_bonus]\n\n"
             "Aulas consideradas:\n[aulas]\n\nAtenciosamente,\n[empresa]")
T_TOTAL = ("Total de [mes]", "Olá, [nome].\nO total do mês é [total].\n[assinatura]")
T_GENERIC = ("Aviso da [empresa]", "Olá, [nome],\n\n[conteudo]\n\nEm [data],\n[assinatura]")
#: The SHAPE of the owner's model e-mail (2026-10-22): greeting, context, the contract link, the
#: classes, three sections with lists — one written with dashes — and a closing.
T_MODEL = ("Cronograma — [mes]",
           "Boa noite, [nome]!\nEsperamos que esteja bem.\n\n"
           "Segue o seu cronograma de [mes]. Assine o contrato em "
           "https://assinatura.example/doc/123.\n\n[aulas]\n\n"
           "Sobre as aulas:\n• Chegue 10 minutos antes.\n· Traga o diário de classe.\n\n"
           "Forma de pagamento:\n• Valor por aula: [valor_por_aula]\n\n"
           "O pagamento será realizado:\n- até o dia 10;\n- por transferência.\n\n"
           "Atenciosamente,\n[assinatura]")

APPEARANCE = {
    "sender_name": "Secretaria do Colégio", "accent_color": "#F6D55C",
    "logo_url": "https://colegio.example/logo.png", "department": "Secretaria Acadêmica",
    "email": "secretaria@colegio.example", "phone": "+55 11 4000-0000",
    "site": "https://colegio.example",
    "links": [{"label": "Instagram", "url": "https://instagram.example/colegio",
               "icon_url": "https://colegio.example/ig.png"},
              {"label": "YouTube", "url": "https://youtube.example/colegio"}],
}


def _filled(template, ctx):
    values, missing = fill_email_fields(template_fields(*template), ctx)
    assert missing == (), [m.sentence() for m in missing]
    return values


# ── the TEXT form moves ONLY in [aulas] ─────────────────────────────────────────────────────

def _corpus():
    """``(label, template, context)`` — every bonus world, with and without the response-rate
    condition, a month with classes and one whose single class is in October, a class with no
    hour, a same-day case, and the generic template. Only cases that FILL are rendered."""
    cases = []
    for ibope in ("92", "85", "71", "89,5", None):
        for cond in ("", "IBOPE_MIN_RESPONSE_PCT: 30\n"):
            for bonus in (True, False):
                svc = _svc(bonus=bonus, ibope=ibope, rules_extra=cond)
                tag = f"ibope={ibope}|cond={bool(cond)}|bonus={bonus}"
                for name, tpl in (("schedule", T_SCHEDULE), ("invoice", T_INVOICE),
                                  ("total", T_TOTAL)):
                    free = "Lembre da sala." if "[conteudo]" in tpl[1] else ""
                    for month in ("2026-09", "2026-10"):
                        cases.append((f"{name}|{tag}|{month}", tpl,
                                      _ctx(svc, month=month, conteudo=free)))
    cases.append(("generic", T_GENERIC, _ctx(conteudo="Reunião na sexta.\nTraga o diário.")))
    cases.append(("schedule|hour-everywhere", T_SCHEDULE,
                  _ctx(_svc(time_last="10:00"), conteudo="x")))
    same_day = _svc(ibope="92", extra=_SAME_DAY)
    cases.append(("schedule|same-day", T_SCHEDULE, _ctx(same_day, conteudo="x")))
    cases.append(("invoice|same-day", T_INVOICE, _ctx(same_day)))
    return cases


# The corpus proof that the text did not move — the provider's digests on ``ad935b4`` against the
# generic path over the real tools — is ``test_the_coordination_by_the_generic_path.py`` (R-T13).
# The digests this file held, taken on ``f1fc1e9`` over the PROVIDER's context, went with it.


def test_aulas_text_is_a_block_per_class_group_with_the_weekday():
    values = _filled(("A", "[aulas]"), _ctx(_svc(extra=_SAME_DAY)))
    assert values["aulas"] == ("Turma XA_01\n"
                               "05/09 (sáb) 08:00 — Redes de Computadores\n"
                               "12/09 (sáb) 08:00 — Redes de Computadores\n"
                               "12/09 (sáb) 10:00 — Zoologia Aplicada\n"
                               "12/09 (sáb) — banco de dados\n"
                               "26/09 (sáb) — Cálculo Numérico\n"
                               "\n"
                               "Turma YB_02\n"
                               "19/09 (sáb) 13:30 — Redes de Computadores")


def _free_ctx(records) -> EmailContext:
    return EmailContext(month="2026-09", recipient_email=ADDRESS, recipient_name="N",
                        custom_tags={"aulas": ""}, free_tag_values={"aulas": records})


def test_the_class_groups_follow_their_code_not_their_first_class():
    """«as turmas por ordem do código»: the group that teaches FIRST is not the group listed
    first — the twin of the fixtures, where the two orders happen to coincide."""
    ctx = _free_ctx([{"data": "01/09", "disciplina": "S1", "turma": "Turma ZZ_9"},
                     {"data": "20/09", "disciplina": "S2", "turma": "Turma AA_1"}])
    values, _ = fill_email_fields(("aulas",), ctx)
    assert values["aulas"].split("\n")[0] == "Turma AA_1"
    assert _group_titles(render_email_html("A", "[aulas]", values, ctx)) == ["Turma AA_1",
                                                                            "Turma ZZ_9"]


# ── the GENERIC renderer: a list of records → text and tables ───────────────────────────────

RECORDS = [  # invented, and nothing about classes: a persona that is not the coordinator's
    {"produto": "Caderno", "quantidade": 3, "valor_unit": "R$ 12,00"},
    {"produto": "Lápis <b>", "quantidade": 10, "valor_unit": "R$ 1,50", "obs": "promoção"},
]


def test_records_text_is_one_line_per_record_key_value():
    assert records_text(RECORDS) == ("produto: Caderno · quantidade: 3 · valor_unit: R$ 12,00\n"
                                     "produto: Lápis <b> · quantidade: 10 · valor_unit: R$ 1,50 · "
                                     "obs: promoção")


def test_records_html_is_one_column_per_key_in_order_and_escaped():
    doc = records_html(RECORDS)
    (table,) = _tables(doc)
    assert _head(table) == ["Produto", "Quantidade", "Valor unit", "Obs"]
    assert _rows(table) == [["Caderno", "3", "R$ 12,00", ""],
                            ["Lápis <b>", "10", "R$ 1,50", "promoção"]]
    assert "Lápis &lt;b&gt;" in doc and "<p" not in doc            # no group, no title
    assert "width:1%" not in doc                                    # no disciplina: no narrow


def test_records_are_split_by_turma_titled_and_ordered_and_a_column_nobody_fills_is_dropped():
    records = [{"data": "02/09/26", "turma": "B2", "sala": ""},
               {"data": "01/09/26", "turma": "Turma A1", "sala": "Azul"},
               {"data": "03/09/26", "turma": "B2", "sala": ""}]
    doc = records_html(records)
    assert _group_titles(doc) == ["Turma A1", "Turma B2"]
    a1, b2 = _tables(doc)
    assert _head(a1) == ["Data", "Sala"] and _head(b2) == ["Data"]  # B2 has no sala at all
    assert _rows(b2) == [["02/09/26"], ["03/09/26"]]                 # the order given, kept
    # two shown keys, both filled: «first: second» (R-T13); one of them empty: «chave: valor»
    assert records_text(records) == ("Turma A1\n01/09/26: Azul\n\n"
                                     "Turma B2\ndata: 02/09/26\ndata: 03/09/26")


def test_the_dated_line_needs_the_known_keys_only_and_a_date_and_a_discipline():
    dated = [{"Data": "06/10/2026", "Dia": "ter", "Horário": "19:00", "Disciplina": "Química"}]
    assert records_text(dated) == "06/10 (ter) 19:00 — Química"     # keys folded: case, accent
    extra = [{**dated[0], "sala": "Azul"}]
    assert records_text(extra) == ("Data: 06/10/2026 · Dia: ter · Horário: 19:00 · "
                                   "Disciplina: Química · sala: Azul")
    assert records_text([{"data": "06/10/26", "dia": "ter"}]) == "06/10/26: ter"   # two keys


def test_a_disciplina_column_is_coloured_by_value_and_the_others_are_narrow():
    records = [{"data": "01/09/26", "disciplina": "Física"},
               {"data": "02/09/26", "disciplina": "Arte"},
               {"data": "03/09/26", "disciplina": "Física"}]
    colors = record_colors([records])
    assert colors == {"Física": DEFAULT_PALETTE[0], "Arte": DEFAULT_PALETTE[1]}
    cells = _discipline_cells(records_html(records, colors=colors))
    assert cells == [("Física", DEFAULT_PALETTE[0]), ("Arte", DEFAULT_PALETTE[1]),
                     ("Física", DEFAULT_PALETTE[0])]


def test_the_colours_count_every_list_of_the_email_in_order():
    first = [{"disciplina": "Física", "turma": "Z"}]
    second = [{"disciplina": "Arte", "turma": "A"}, {"disciplina": "Física", "turma": "A"}]
    assert list(record_colors([first, second])) == ["Física", "Arte"]
    assert list(record_colors([second, first])) == ["Arte", "Física"]


@pytest.mark.parametrize("bad", [None, "texto", [], {}, [1, 2], [{"": "x"}], [{1: "x"}],
                                 [{"a": "b"}] * 501])
def test_what_is_not_a_list_of_records_renders_nothing(bad):
    assert as_records(bad) is None and records_text(bad) == "" and records_html(bad) == ""


def test_as_records_writes_every_value_as_text():
    assert as_records([{"n": 3, "x": None, " k ": " v "}]) == [{"n": "3", "x": "", "k": "v"}]


def test_aulas_is_a_list_of_records_drawn_by_the_generic_renderer():
    """[aulas] is the tenant's free tag; its value is the list the coordination COPIED from its
    schedule read: its text and its tables are the generic renderer's — no class-specific
    drawing exists."""
    ctx = _ctx(_svc(ibope="92", extra=_SAME_DAY), conteudo="x")
    records = _records(ctx)
    assert [list(r) for r in records][0] == ["mês", "dia", "data", "horário", "disciplina", "turma"]
    values = _filled(T_SCHEDULE, ctx)
    assert values["aulas"] == records_text(records)
    doc = render_email_html(*T_SCHEDULE, values, ctx)
    colors = record_colors([records])
    assert records_html(records, colors=colors) in doc


# ── [aulas] in HTML: a table per class group ────────────────────────────────────────────────

def _tables(doc: str) -> "list[str]":
    return re.findall(r"<table\b.*?</table>", doc, flags=re.S)


def _rows(table: str) -> "list[list[str]]":
    body = re.search(r"<tbody>(.*)</tbody>", table, flags=re.S).group(1)
    return [[html.unescape(re.sub(r"<[^>]+>", "", c))
             for c in re.findall(r"<td\b[^>]*>(.*?)</td>", r, flags=re.S)]
            for r in re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, flags=re.S)]


def _head(table: str) -> "list[str]":
    return [html.unescape(re.sub(r"<[^>]+>", "", c))
            for c in re.findall(r"<th\b[^>]*>(.*?)</th>", table, flags=re.S)]


def _group_titles(doc: str) -> "list[str]":
    return [html.unescape(t) for t in re.findall(r"<p [^>]*>(Turma [^<]*)</p><table", doc)]


def test_aulas_is_one_table_per_class_group_under_its_title():
    ctx = _ctx(_svc(ibope="92"), conteudo="Lembre da sala.")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert _group_titles(doc) == ["Turma XA_01", "Turma YB_02"]
    xa, yb = _tables(doc)
    assert _head(xa) == ["Mês", "Dia", "Data", "Horário", "Disciplina"]
    # The Data column is dd/mm, as the read prints it (R-T13; the provider wrote dd/mm/aa).
    assert _rows(xa) == [["setembro", "sáb", "05/09", "08:00", "Redes de Computadores"],
                         ["setembro", "sáb", "12/09", "08:00", "Redes de Computadores"],
                         ["setembro", "sáb", "26/09", "", "Cálculo Numérico"]]
    assert _rows(yb) == [["setembro", "sáb", "19/09", "13:30", "Redes de Computadores"]]
    assert sum(len(_rows(t)) for t in (xa, yb)) == len(_records(ctx))
    assert "Turma" not in _head(xa)                       # the table IS the class group's


def test_a_group_title_is_kept_with_a_single_group_and_the_hour_only_when_it_has_one():
    ctx = _ctx(_svc(ibope="92"), month="2026-10", conteudo="x")
    no_hour = dataclasses.replace(ctx, free_tag_values={
        **ctx.free_tag_values, "aulas": [{**r, "horário": ""} for r in _records(ctx)]})
    assert any(r.get("horário") for r in _records(ctx))   # control: October HAS an hour
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, no_hour), no_hour)
    assert _group_titles(doc) == ["Turma XA_01"]
    (table,) = _tables(doc)
    assert _head(table) == ["Mês", "Dia", "Data", "Disciplina"]
    assert _rows(table) == [["outubro", "sáb", "03/10", "Cálculo Numérico"]]


def test_a_label_that_does_not_say_turma_is_titled_turma():
    ctx = _free_ctx([{"data": "05/09", "dia": "sáb", "disciplina": "S", "turma": "QZ_07"}])
    values, _ = fill_email_fields(("aulas",), ctx)
    assert values["aulas"] == "Turma QZ_07\n05/09 (sáb) — S"
    assert _group_titles(render_email_html("A", "[aulas]", values, ctx)) == ["Turma QZ_07"]


# ── the colour of each discipline ───────────────────────────────────────────────────────────

def _discipline_cells(doc: str) -> "list[tuple[str, str]]":
    """``(discipline, background)`` of each table's LAST cell, in document order."""
    out = []
    for table in _tables(doc):
        for row in re.findall(r"<tr>(.*?)</tr>", table.split("<tbody>", 1)[1], flags=re.S):
            last = re.findall(r'<td style="([^"]*)">(.*?)</td>', row, flags=re.S)[-1]
            out.append((html.unescape(last[1]), re.search(r"background:(#[0-9a-f]{6})$",
                                                         last[0]).group(1)))
    return out


def test_each_discipline_has_one_colour_in_the_whole_email_by_first_appearance():
    ctx = _ctx(_svc(ibope="92", extra=_SAME_DAY), conteudo="x")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    cells = _discipline_cells(doc)
    colours = {}
    for subject, colour in cells:
        assert colours.setdefault(subject, colour) == colour      # the same everywhere
    # first appearance: XA_01 (Redes, Zoologia, banco, Cálculo), then YB_02 (Redes again)
    assert list(colours) == ["Redes de Computadores", "Zoologia Aplicada", "banco de dados",
                             "Cálculo Numérico"]
    assert list(colours.values()) == list(DEFAULT_PALETTE[:4])
    # Mês · Dia · Data stay white
    assert all("background:#ffffff" in td for td in re.findall(
        r'<td style="([^"]*width:1%[^"]*)"', doc))


def test_the_colours_do_not_depend_on_the_order_the_class_groups_arrive_in():
    """The groups are taken in the order of their CODE, so the records of one group handed over
    before or after another's give the same colours (inside a group the order is the read's)."""
    ctx = _ctx(_svc(ibope="92", extra=_SAME_DAY), conteudo="x")
    records = _records(ctx)
    expected = record_colors([records])
    groups = {}
    for r in records:
        groups.setdefault(r["turma"], []).append(r)
    for seed in range(5):
        order = list(groups)
        random.Random(seed).shuffle(order)
        assert record_colors([[r for g in order for r in groups[g]]]) == expected


def test_the_tenants_accent_is_the_first_colour_and_the_palette_cycles():
    records = [{"disciplina": f"D{d:02d}", "turma": "T1"} for d in range(1, 10)]
    app = EmailAppearance(accent_color="#123456")
    colours = list(record_colors([records], app).values())
    assert colours[0] == "#123456" and colours[1:7] == list(DEFAULT_PALETTE)
    assert colours[7] == "#123456"                               # 7 colours, cycled
    same = EmailAppearance(accent_color=DEFAULT_PALETTE[2])      # an accent that IS a default
    assert list(record_colors([records], same).values())[:6] == (
        [DEFAULT_PALETTE[2]] + [c for c in DEFAULT_PALETTE if c != DEFAULT_PALETTE[2]])


# ── the other blocks ────────────────────────────────────────────────────────────────────────

def test_valores_por_bonus_is_a_two_column_table_and_the_applied_band_is_marked():
    ctx = _ctx(_svc(ibope="92", rules_extra="IBOPE_MIN_RESPONSE_PCT: 30\n"))
    doc = render_email_html(*T_INVOICE, _filled(T_INVOICE, ctx), ctx)
    bands = _tables(doc)[0]
    assert _head(bands) == ["Faixa", "Valor"]
    assert _rows(bands) == [["Sem bônus", "R$ 1.920,00"], ["IBOPE 80–89%", "R$ 2.400,00"],
                            ["IBOPE 90%+", "R$ 2.560,00 ← apurado (IBOPE 92%)"]]
    # The response-rate condition is not a record (R-T13): the tenant writes it in the template
    # or a fixed tag; the provider used to add it after the table.
    assert "Condição das regras" not in html.unescape(doc)


@pytest.mark.parametrize("ibope", ["89,5", None])
def test_no_band_is_marked_when_the_bonus_is_not_determined(ibope):
    ctx = _ctx(_svc(ibope=ibope))
    values, _ = fill_email_fields(("valores_por_bonus",), ctx)
    doc = render_email_html("Valores", "[valores_por_bonus]", values, ctx)
    assert [r[0] for r in _rows(_tables(doc)[0])] == ["Sem bônus", "IBOPE 80–89%", "IBOPE 90%+"]
    assert "apurado" not in doc


def test_a_figure_is_never_bold_by_its_name_and_alone_makes_no_html():
    """INVERTED by R-T13 (was: «a figure is bold wherever it stands, and makes the e-mail HTML»):
    no value is bold by its NAME, and an e-mail with no list of records goes out as text."""
    ctx = _ctx(_svc(ibope="92"))
    values, _ = fill_email_fields(("total", "valor_por_aula", "aulas"), ctx)
    assert render_email_html("T", "Seu total:\n[total]\n[valor_por_aula]", values, ctx) == ""
    doc = render_email_html("T", "O total é [total] e a aula custa [valor_por_aula].\n[aulas]",
                            values, ctx)
    assert doc and "R$ 2.560,00" in doc and "R$ 480,00" in doc and "<strong>R$" not in doc


def test_disciplinas_is_a_list():
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert re.findall(r"<li>(.*?)</li>", doc) == ["Cálculo Numérico", "Redes de Computadores"]


# ── the body: simple rich text, four rules ──────────────────────────────────────────────────

def _model_doc(appearance=None) -> "tuple[str, str]":
    ctx = _ctx(_svc(ibope="92"), month="2026-09")
    values = _filled(T_MODEL, ctx)
    _subject, text, doc = render_email_forms(*T_MODEL, values, ctx, appearance=appearance)
    return text, doc


def test_paragraphs_lists_titles_and_links():
    _text, doc = _model_doc()
    body = doc.split("<body", 1)[1]
    assert "<p style=\"margin:0 0 12px\">Boa noite, Prof Quintino!<br>\nEsperamos que esteja bem.</p>" in body
    assert ('<a href="https://assinatura.example/doc/123">https://assinatura.example/doc/123</a>.'
            in body)                                       # the full stop stays outside the link
    titles = re.findall(r"<p [^>]*><strong>(.*?)</strong></p>", body)
    assert titles == ["Sobre as aulas:", "Forma de pagamento:", "O pagamento será realizado:"]
    lists = re.findall(r"<ul [^>]*>(.*?)</ul>", body)
    assert lists[0] == "<li>Chegue 10 minutos antes.</li><li>Traga o diário de classe.</li>"
    assert lists[1] == "<li>Valor por aula: R$ 480,00</li>"     # never bold by name (R-T13)
    # «-» stays a line with its dash — never a bullet (the owner's model)
    assert "<p style=\"margin:0 0 12px\">- até o dia 10;<br>\n- por transferência.</p>" in body
    assert len(lists) == 2


def test_a_long_line_ending_with_a_colon_is_not_a_title():
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert "<strong>Disciplinas do mês:</strong>" in doc                  # short: a title
    assert "<strong>Segue o seu cronograma" not in doc                     # 64 chars: a line


def test_only_the_tenants_text_is_linked_never_a_value_the_model_wrote():
    ctx = _ctx(_svc(ibope="92"), conteudo="veja https://outro.example/x")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert "veja https://outro.example/x" in doc and 'href="https://outro.example' not in doc
    tag = _ctx(_svc(ibope="92"), custom_tags={"link_contrato": "https://assinatura.example/c"})
    tpl = ("A", "Contrato: [link_contrato]\n[aulas]")
    doc = render_email_html(*tpl, _filled(tpl, tag), tag)
    assert '<a href="https://assinatura.example/c">' in doc               # the tenant's own value


def test_a_free_tags_value_is_the_conversations_and_is_never_linked():
    """#177: a FREE company tag (stored empty) is filled from what the requester SAID — not the
    tenant's text, so its URL is not a link. CONTROL: the same URL as a FIXED tag's value is."""
    tpl = ("A", "Link: [link_contrato]\n[aulas]")
    free = _ctx(_svc(ibope="92"), custom_tags={"link_contrato": ""},
                free_tag_values={"link_contrato": "https://assinatura.example/c"})
    doc = render_email_html(*tpl, _filled(tpl, free), free)
    assert "https://assinatura.example/c" in doc and "<a " not in doc.split("<body", 1)[1]
    fixed = _ctx(_svc(ibope="92"), custom_tags={"link_contrato": "https://assinatura.example/c"})
    assert '<a href="https://assinatura.example/c">' in render_email_html(*tpl, _filled(tpl, fixed),
                                                                         fixed)


def test_a_url_with_another_scheme_is_never_a_link():
    ctx = _ctx(_svc(ibope="92"))
    tpl = ("A", "Veja javascript:alert(1) e data:text/html,x e ftp://a.example\n[aulas]")
    doc = render_email_html(*tpl, _filled(tpl, ctx), ctx)
    assert "<a " not in doc.split("<body", 1)[1]


# ── the appearance: the SAVE door, the TURN door, the signature ─────────────────────────────

@pytest.mark.parametrize("field, value", [
    ("logo_url", "javascript:alert(1)"),
    ("logo_url", "data:image/png;base64,AAAA"),
    ("logo_url", "ftp://colegio.example/logo.png"),
    ("logo_url", "//colegio.example/logo.png"),
    ("logo_url", "https://colegio.example/a b.png"),
    ("logo_url", 'https://colegio.example/a".png'),
    ("site", "JAVASCRIPT:alert(1)"),
    ("site", "colegio.example"),
    ("accent_color", "amarelo"),
    ("accent_color", "#ff00"),
    ("email", "nao-e-um-email"),
    ("phone", "ligue já"),
    ("department", "linha\noutra"),
    ("sender_name", "x" * 81),
])
def test_the_save_door_refuses_each_bad_field_and_stores_nothing(field, value):
    stored, refusals = normalise_email_appearance({**APPEARANCE, field: value})
    assert stored == {} and refusals
    fixed, ok = normalise_email_appearance(APPEARANCE)
    assert ok == () and fixed                                     # control: the same, valid


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:image/png;base64,AAAA"])
@pytest.mark.parametrize("key", ["url", "icon_url"])
def test_a_social_link_or_its_icon_is_http_or_https_only(key, bad):
    link = {"label": "Rede", "url": "https://rede.example/x", key: bad}
    stored, refusals = normalise_email_appearance({"links": [link]})
    assert stored == {} and any("http:// ou https://" in r for r in refusals)
    good = {**link, key: "https://rede.example/i.png"}
    assert normalise_email_appearance({"links": [good]})[1] == ()     # control: https passes
    assert normalise_email_appearance({"links": [{**good, key: "http://rede.example/i.png"}]})[1] == ()


def test_the_save_door_refuses_unknown_fields_too_many_links_and_a_link_without_a_name():
    assert normalise_email_appearance({"html": "<b>x</b>"})[1]
    five = [{"label": f"R{i}", "url": f"https://r{i}.example"} for i in range(5)]
    assert normalise_email_appearance({"links": five})[1]
    assert normalise_email_appearance({"links": five[:4]})[1] == ()   # control: four pass
    assert normalise_email_appearance({"links": [{"label": " ", "url": "https://r.example"}]})[1]
    assert normalise_email_appearance("não é um objeto")[1]


def test_the_save_door_normalises_what_it_keeps():
    stored, _ = normalise_email_appearance({**APPEARANCE, "phone": "  ", "department": " Sec "})
    assert stored["accent_color"] == "#f6d55c" and stored["department"] == "Sec"
    assert "phone" not in stored                                    # an empty field is not kept


def test_the_turn_door_keeps_what_the_save_would_and_drops_the_rest_one_by_one():
    raw = {**APPEARANCE, "logo_url": "javascript:x",
           "links": APPEARANCE["links"] + [{"label": "Má", "url": "data:x"}]}
    app = parse_email_appearance(raw)
    assert app is not None and app.logo_url == "" and app.site == "https://colegio.example"
    assert [lk.label for lk in app.links] == ["Instagram", "YouTube"]
    assert parse_email_appearance({}) is None and parse_email_appearance(None) is None


def test_the_signature_is_drawn_in_the_html_and_written_in_the_text_alike():
    app = parse_email_appearance(APPEARANCE)
    text, doc = _model_doc(app)
    sig = email_signature_text(app, _ctx())
    assert sig == ("Coordenação\nSecretaria Acadêmica\n+55 11 4000-0000\n"
                   "secretaria@colegio.example\nhttps://colegio.example\n"
                   "Instagram: https://instagram.example/colegio\n"
                   "YouTube: https://youtube.example/colegio")
    assert text.endswith("\n\n" + sig)
    block = _tables(doc)[-1]
    assert '<img src="https://colegio.example/logo.png" alt="Secretaria do Colégio"' in block
    assert "<strong>Coordenação</strong>" in block and "border-left:1px solid" in block
    assert '<a href="mailto:secretaria@colegio.example">' in block
    assert ('<a href="https://instagram.example/colegio"><img src="https://colegio.example/ig.png"'
            ' alt="Instagram"' in block)
    assert '<a href="https://youtube.example/colegio">YouTube</a>' in block   # no icon: its name


def test_no_signature_configured_adds_nothing_and_the_header_is_the_tenants_name():
    plain_text, doc = _model_doc(None)
    ctx = _ctx(_svc(ibope="92"))
    assert plain_text == render_email(*T_MODEL, _filled(T_MODEL, ctx))[1]   # the text, as is
    assert "<img" not in doc and "mailto:" not in doc
    assert re.search(r"<p [^>]*>Colégio Horizonte</p>", doc)
    only_colour = parse_email_appearance({"accent_color": "#123456", "sender_name": "Sec"})
    text2, doc2 = _model_doc(only_colour)
    assert text2 == plain_text and re.search(r"<p [^>]*>Sec</p>", doc2)


def test_a_template_with_no_data_marker_gets_no_html_and_no_signature():
    ctx = _ctx(conteudo="Reunião na sexta.")
    values = _filled(T_GENERIC, ctx)
    app = parse_email_appearance(APPEARANCE)
    assert render_email_forms(*T_GENERIC, values, ctx, appearance=app) == (
        *render_email(*T_GENERIC, values), "")


def test_a_data_marker_only_in_the_subject_or_a_company_tag_alone_renders_no_html():
    ctx = _ctx(_svc(ibope="92"), custom_tags={"horario_atendimento": "Seg a sex\n8h às 17h"})
    tpl = ("Total de [mes]: [total]", "Olá, [nome].\n[horario_atendimento]")
    values = _filled(tpl, ctx)
    assert render_email_html(*tpl, values, ctx) == ""
    assert render_email_html("Total", "Olá. Total: [total].", values, ctx) == ""   # R-T13
    assert render_email_html("Aulas", "Olá.\n[aulas]", _filled(("A", "[aulas]"), ctx),
                             ctx) != ""                                          # control


# ── safe by construction ────────────────────────────────────────────────────────────────────

_TAGS = {"html", "head", "meta", "title", "body", "div", "table", "thead", "tbody", "tr", "th",
         "td", "ul", "li", "p", "br", "strong", "a", "img"}
_ATTRS = {"style", "lang", "charset", "name", "content", "href", "src", "alt", "width", "height",
          "colspan"}
_STYLE_FORBIDDEN = ("url(", "expression", "@import", "javascript", "behavior", "http")


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: "list[tuple[str, list]]" = []
        self.decls: "list[str]" = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_decl(self, decl):
        self.decls.append(decl)


def _assert_inert(doc: str, images: "frozenset[str]" = frozenset()) -> None:
    """The closed alphabet: these elements and attributes only; a link only ``http``/``https``/
    ``mailto``; an image only one of ``images`` (what the appearance configured), with an
    ``alt``; no URL in any style."""
    parser = _Tags()
    parser.feed(doc)
    parser.close()
    assert parser.decls == ["DOCTYPE html"]
    assert parser.tags, "no element parsed — the check would pass on anything"
    for tag, attrs in parser.tags:
        assert tag in _TAGS, tag
        a = dict(attrs)
        for name, value in attrs:
            assert name in _ATTRS, (tag, name)
            if name == "style":
                assert not any(bad in (value or "").lower() for bad in _STYLE_FORBIDDEN), value
        if tag == "a":
            assert re.match(r"(https?://|mailto:)", a.get("href") or "", re.I), a
        if tag == "img":
            assert a.get("src") in images and a.get("alt"), a
        if "src" in a:
            assert tag == "img"
        if "href" in a:
            assert tag == "a"
    metas = [dict(a) for t, a in parser.tags if t == "meta"]
    assert metas == [{"charset": "utf-8"},
                     {"name": "viewport", "content": "width=device-width, initial-scale=1"}]


def test_control_the_inertness_check_refuses_what_it_exists_to_refuse():
    shell = ('<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" '
             'content="width=device-width, initial-scale=1"></head><body>{}</body></html>')
    for bad in ("<script>x</script>", '<img src="https://x.example/a.png" alt="a">',
                '<a href="javascript:x">a</a>', '<a href="data:text/html,x">a</a>',
                '<link rel="stylesheet">', '<div onclick="x">a</div>', "<style>p{}</style>",
                '<div style="background:url(a.png)">a</div>', '<img src="https://ok.example/l.png">'):
        with pytest.raises(AssertionError):
            _assert_inert(shell.format(bad), frozenset({"https://ok.example/l.png"}))
    _assert_inert(shell.format("&lt;script&gt; src= https://x.example"))   # escaped text passes
    _assert_inert(shell.format('<img src="https://ok.example/l.png" alt="Logo">'),
                  frozenset({"https://ok.example/l.png"}))


def test_a_value_with_markup_comes_out_as_text():
    hostile = '<script>alert(1)</script><b>Redes</b> & "aspas"'
    ctx = _ctx(_svc(ibope="92", subject_a=hostile), conteudo="<img src=https://x.example/a.png>")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    _assert_inert(doc)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;&lt;b&gt;Redes&lt;/b&gt; &amp; &quot;aspas&quot;" in doc
    assert hostile in [r[-1] for r in _rows(_tables(doc)[0])]
    assert "&lt;img src=https://x.example/a.png&gt;" in doc


def test_the_tenants_own_template_text_is_escaped_too():
    ctx = _ctx(_svc(ibope="92"))
    tpl = ("Aulas", '<a href="https://x.example">clique</a> <style>p{}</style>\n[aulas]')
    doc = render_email_html(*tpl, _filled(tpl, ctx), ctx)
    _assert_inert(doc)
    assert "&lt;a href=&quot;" in doc and "&lt;style&gt;" in doc


def test_every_rendering_of_the_corpus_is_inert_with_and_without_the_appearance():
    app = parse_email_appearance(APPEARANCE)
    images = frozenset({APPEARANCE["logo_url"], APPEARANCE["links"][0]["icon_url"]})
    n = 0
    for _, tpl, ctx in _corpus():
        values, missing = fill_email_fields(template_fields(*tpl), ctx)
        if missing:
            continue
        for appearance, allowed in ((None, frozenset()), (app, images)):
            doc = render_email_html(*tpl, values, ctx, appearance=appearance)
            if doc:
                n += 1
                _assert_inert(doc, allowed)
                assert doc.startswith("<!DOCTYPE html>") and doc.rstrip().endswith("</html>")
    assert n > 100


def test_a_configured_url_with_a_quote_cannot_break_out_of_its_attribute():
    """The SAVE door refuses quotes in a URL; the render escapes it anyway — an appearance built
    by hand, around the door, still yields one attribute."""
    app = EmailAppearance(logo_url='https://x.example/a.png" onerror="x',
                          links=(SocialLink("R", 'https://r.example/" onclick="y'),))
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx, appearance=app)
    _assert_inert(doc, frozenset({'https://x.example/a.png" onerror="x'}))


# ── the HTML says what the text says ────────────────────────────────────────────────────────

def _visible(doc: str) -> str:
    body = doc.split("<body", 1)[1].split(">", 1)[1]
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


def test_every_figure_class_and_discipline_of_the_text_is_in_the_html():
    ctx = _ctx(_svc(ibope="85", rules_extra="IBOPE_MIN_RESPONSE_PCT: 30\n"))
    values = _filled(T_INVOICE, ctx)
    _, text = render_email(*T_INVOICE, values)
    seen = _visible(render_email_html(*T_INVOICE, values, ctx))
    money = re.compile(r"R\$ [\d.]+,\d{2}")
    assert sorted(money.findall(text)) == sorted(money.findall(seen))
    for r in _records(ctx):
        assert r["data"] in seen and r["disciplina"] in seen
        assert _filled(("t", "[aulas]"), ctx)["aulas"].count(r["disciplina"]) <= \
            seen.count(r["disciplina"])
    assert "Turma XA_01" in seen and "Turma YB_02" in seen


def test_a_value_the_context_does_not_rebuild_is_shown_as_its_text_not_as_a_table():
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    values = _filled(T_SCHEDULE, ctx)
    values["aulas"] = "01/09 — Outra Coisa"
    doc = render_email_html(*T_SCHEDULE, values, ctx)
    assert "Outra Coisa" in doc and "<table" not in doc


@pytest.mark.parametrize("name, tpl, tag", [("disciplinas", T_SCHEDULE, "<ul"),
                                            ("valores_por_bonus", T_INVOICE, "<table")])
def test_every_block_falls_back_to_its_text_when_the_context_does_not_rebuild_it(name, tpl, tag):
    ctx = _ctx(_svc(ibope="92"), conteudo="x" if "[conteudo]" in tpl[1] else "")
    values = _filled(tpl, ctx)
    drawn = render_email_html(*tpl, values, ctx)
    values[name] = "Outra linha\ncom <b>marcação</b>"
    doc = render_email_html(*tpl, values, ctx)
    assert "Outra linha<br>\ncom &lt;b&gt;marcação&lt;/b&gt;" in doc
    assert doc.count(tag) == drawn.count(tag) - 1


def test_one_pass_a_marker_typed_inside_a_value_stays_text():
    ctx = _ctx(_svc(ibope="92"), conteudo="o [total] e o [aulas]")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert "o [total] e o [aulas]" in html.unescape(doc)
    assert doc.count("<table") == 2                       # the two class groups' tables only


def test_render_html_refuses_a_marker_with_no_value_like_the_text_render():
    with pytest.raises(ValueError):
        render_email_html("Aviso", "[aulas]", {}, EmailContext())


def test_it_is_deterministic_and_exported():
    app = parse_email_appearance(APPEARANCE)
    assert _model_doc(app) == _model_doc(app)
    for name in ("render_email_html", "render_email_forms", "EmailAppearance",
                 "normalise_email_appearance", "parse_email_appearance", "email_signature_text",
                 "record_colors", "records_html", "records_text", "as_records"):
        assert name in ef.__all__, name


def test_what_makes_html_is_a_list_in_a_free_tag_never_a_name():
    """R-T13: the markers that made an e-mail HTML were the provider's, by NAME. Now it is the
    VALUE: a free tag holding a list of records — and nothing else, whatever its name."""
    for name in ("aulas", "lista_qualquer"):
        ctx = _free_ctx([{"a": "1", "b": "2", "c": "3"}])
        ctx = dataclasses.replace(ctx, custom_tags={name: ""},
                                  free_tag_values={name: [{"a": "1", "b": "2", "c": "3"}]})
        values, _ = fill_email_fields((name,), ctx)
        assert "<table" in render_email_html("A", f"[{name}]", values, ctx)
        text = dataclasses.replace(ctx, free_tag_values={name: "1 2 3"})
        assert render_email_html("A", f"[{name}]", fill_email_fields((name,), text)[0], text) == ""
    assert not hasattr(ef, "_DATA_MARKERS") and not hasattr(ef, "_BLOCK_FORMS")


def test_the_html_document_is_a_mobile_friendly_shell():
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    doc = render_email_html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert '<meta charset="utf-8">' in doc
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in doc
    assert "max-width:640px" in doc and "border-collapse:collapse" in doc
    assert "<title>Cronograma de aulas — setembro/2026</title>" in doc
