"""The class table of an e-mail DERIVES its Mês and Dia from the date, and the discipline's colour
paints the Data cell too (R-T18, 2026-10-22).

The owner sent the e-mail he expects: one table per class group, the columns Mês · Dia · Data ·
Disciplina, and the discipline's colour on the Data cell as well. The renderer drew Mês and Dia only
when the RECORDS carried them, and the records are what the executor copies from a read that
prints «dd/mm · turma · disciplina». Asking the model for the two columns made it drop the class
key — no class key, no table per class — so they are derived HERE, in code, from the date:

* a timetable (a table whose columns are only the dated keys, with a ``data`` and a
  ``disciplina``) leads with Mês · Dia · Data, whatever order the records bring the keys in;
* a record WITHOUT ``mês``/``dia`` gets them from the date the Data column SHOWS: «out.-26»,
  «ter.» — the module's own month and weekday tables, pt-BR like every word the renderer writes;
* a record that BRINGS them shows its own: they are the sheet's data;
* a date that does not read — or one shown without a year, so with no weekday — leaves both cells
  empty, and the row goes on; a column empty in every row is left out, like an hour nobody has;
* the Data cell takes the colour of its row's discipline; Mês and Dia stay white;
* the TEXT part does not move a byte: it is what the proposal shows and what the «sim» compares
  (``email_digest``), pinned here by digests taken on the base (praxis ``081a0614``).

Everything here is invented: the class codes, the disciplines, the professor, the school.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import date, timedelta

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.email_fields import (
    DEFAULT_PALETTE,
    EmailAppearance,
    EmailContext,
    record_colors,
    records_html,
    records_text,
    render_email_forms,
)

MONTH = "2026-10"

#: The shape the executor handed ``send_email`` in the send that PASSED: Turma, Data, Disciplina —
#: the keys capitalised as it wrote them, ``dd/mm`` as the read prints them. Two of them carry a
#: year, one is of another month and carries none.
SENT = [
    {"Turma": "QZ_07", "Data": "07/10", "Disciplina": "Zoologia Aplicada"},
    {"Turma": "QZ_07", "Data": "19/10", "Disciplina": "Zoologia Aplicada"},
    {"Turma": "QZ_07", "Data": "11/11", "Disciplina": "Cálculo Numérico"},
    {"Turma": "QZ_07", "Data": "02/12/26", "Disciplina": "Cálculo Numérico"},
    {"Turma": "XA_01", "Data": "06/10", "Disciplina": "Redes de Computadores"},
    {"Turma": "XA_01", "Data": "08/10", "Disciplina": "Redes de Computadores"},
    {"Turma": "XA_01", "Data": "22/10", "Disciplina": "Cálculo Numérico"},
    {"Turma": "XA_01", "Data": "27/10", "Disciplina": "Redes de Computadores"},
    {"Turma": "XA_01", "Data": "03/11/2026", "Disciplina": "Cálculo Numérico"},
]
#: The shape the model wrote when it was asked for the two columns: its own key order (Dia, Data,
#: Mês, Turma, Disciplina), the month by name and the «Dia» as the day of the month.
MODEL_ORDER = [
    {"Dia": "06", "Data": "06/10", "Mês": "outubro", "Turma": "XA_01",
     "Disciplina": "Redes de Computadores"},
    {"Dia": "22", "Data": "22/10", "Mês": "outubro", "Turma": "XA_01",
     "Disciplina": "Cálculo Numérico"},
]
#: The shape of the owner's model: every column carried, the year on the date.
CARRIED = [
    {"turma": "XA_01", "mes": "out.-26", "dia": "ter.", "data": "06/10/26",
     "disciplina": "Redes de Computadores"},
    {"turma": "XA_01", "mes": "out.-26", "dia": "qui.", "data": "22/10/26",
     "disciplina": "Cálculo Numérico"},
    {"turma": "QZ_07", "mes": "nov.-26", "dia": "qua.", "data": "11/11/26",
     "disciplina": "Zoologia Aplicada"},
]


def _tables(doc: str) -> "list[str]":
    return re.findall(r"<table\b.*?</table>", doc, flags=re.S)


def _head(table: str) -> "list[str]":
    return [html.unescape(re.sub(r"<[^>]+>", "", c))
            for c in re.findall(r"<th\b[^>]*>(.*?)</th>", table, flags=re.S)]


def _cells(table: str) -> "list[list[tuple[str, str]]]":
    """Each body row as ``[(text, style)]``."""
    body = re.search(r"<tbody>(.*)</tbody>", table, flags=re.S).group(1)
    return [[(html.unescape(text), style)
             for style, text in re.findall(r'<td style="([^"]*)">(.*?)</td>', row, flags=re.S)]
            for row in re.findall(r"<tr>(.*?)</tr>", body, flags=re.S)]


def _rows(table: str) -> "list[list[str]]":
    return [[text for text, _ in row] for row in _cells(table)]


def _background(style: str) -> str:
    return re.search(r"background:(#[0-9a-fA-F]{6})", style).group(1)


def _html(records, month=MONTH):
    return records_html(records, colors=record_colors([records]), month=month)


# ── the twin: a record without Mês and Dia ──────────────────────────────────────────────────

def test_a_record_without_mes_and_dia_gets_them_from_its_date():
    qz, xa = _tables(_html(SENT))
    assert _head(qz) == _head(xa) == ["Mês", "Dia", "Data", "Disciplina"]
    assert _rows(xa) == [["out.-26", "ter.", "06/10/26", "Redes de Computadores"],
                         ["out.-26", "qui.", "08/10/26", "Redes de Computadores"],
                         ["out.-26", "qui.", "22/10/26", "Cálculo Numérico"],
                         ["out.-26", "ter.", "27/10/26", "Redes de Computadores"],
                         ["nov.-26", "ter.", "03/11/2026", "Cálculo Numérico"]]
    # «11/11» is of another month and is shown WITHOUT a year: it has no weekday — both empty.
    assert _rows(qz) == [["out.-26", "qua.", "07/10/26", "Zoologia Aplicada"],
                         ["out.-26", "seg.", "19/10/26", "Zoologia Aplicada"],
                         ["", "", "11/11", "Cálculo Numérico"],
                         ["dez.-26", "qua.", "02/12/26", "Cálculo Numérico"]]


def test_the_derivation_is_the_html_s_and_never_the_text_s():
    """The text line takes the weekday from the RECORD only — the derived one never reaches it."""
    assert records_text(SENT).splitlines()[:3] == ["Turma QZ_07", "07/10 — Zoologia Aplicada",
                                                   "19/10 — Zoologia Aplicada"]
    assert "(" not in records_text(SENT)                       # no «(qua.)» was added
    assert "07/10 (qua.) — Zoologia Aplicada" in records_text(  # control: a record that brings it
        [{**SENT[0], "Dia": "qua."}])


def test_a_timetable_leads_with_mes_dia_data_whatever_order_the_record_brings():
    (table,) = _tables(_html(MODEL_ORDER))
    assert [k for k in MODEL_ORDER[0]][:3] == ["Dia", "Data", "Mês"]      # the order brought
    assert _head(table) == ["Mês", "Dia", "Data", "Disciplina"]
    # with an hour: it keeps its place after the date, before the discipline
    hour = [{"data": "06/10", "disciplina": "Redes de Computadores", "horário": "19:00"}]
    (table,) = _tables(_html(hour))
    assert _head(table) == ["Mês", "Dia", "Data", "Disciplina", "Horário"]
    hour = [{"horário": "19:00", "data": "06/10", "disciplina": "Redes de Computadores"}]
    (table,) = _tables(_html(hour))
    assert _head(table) == ["Mês", "Dia", "Data", "Horário", "Disciplina"]


# ── the twin: a record that brings Mês and Dia ──────────────────────────────────────────────

def test_a_record_that_brings_mes_and_dia_shows_its_own_not_the_derived():
    own = [{"turma": "XA_01", "mês": "outubro", "dia": "terça", "data": "06/10",
            "disciplina": "Redes de Computadores"}]
    (table,) = _tables(_html(own))
    assert _rows(table) == [["outubro", "terça", "06/10/26", "Redes de Computadores"]]
    # control: the same record without them gets the derived ones — the two DIFFER
    bare = [{k: v for k, v in own[0].items() if k not in ("mês", "dia")}]
    (table,) = _tables(_html(bare))
    assert _rows(table) == [["out.-26", "ter.", "06/10/26", "Redes de Computadores"]]
    # the model's «Dia» was the day of the month: it is what the record brings, and it is shown
    (table,) = _tables(_html(MODEL_ORDER))
    assert _rows(table) == [["outubro", "06", "06/10/26", "Redes de Computadores"],
                            ["outubro", "22", "22/10/26", "Cálculo Numérico"]]


def test_a_record_that_brings_an_empty_cell_gets_the_derived_one_for_that_cell_only():
    mixed = [{"mês": "outubro", "dia": "", "data": "06/10", "disciplina": "Redes de Computadores"},
             {"mês": "", "dia": "quinta", "data": "08/10", "disciplina": "Redes de Computadores"}]
    (table,) = _tables(_html(mixed))
    assert _head(table) == ["Mês", "Dia", "Data", "Disciplina"]
    assert _rows(table) == [["outubro", "ter.", "06/10/26", "Redes de Computadores"],
                            ["out.-26", "quinta", "08/10/26", "Redes de Computadores"]]


# ── the twin: a date that does not read ─────────────────────────────────────────────────────

@pytest.mark.parametrize("unread", ["dia cinco", "2026-10-06", "31/02/26", "06/13", "11/11", ""])
def test_a_date_that_does_not_read_leaves_both_cells_empty_and_the_row_goes_on(unread):
    records = [{"data": unread, "disciplina": "Zoologia Aplicada"},
               {"data": "06/10", "disciplina": "Redes de Computadores"}]   # control: it reads
    (table,) = _tables(_html(records))
    assert _head(table) == ["Mês", "Dia", "Data", "Disciplina"]
    rows = _rows(table)
    assert len(rows) == 2 and rows[0][:2] == ["", ""] and rows[0][3] == "Zoologia Aplicada"
    assert rows[1] == ["out.-26", "ter.", "06/10/26", "Redes de Computadores"]


def test_with_no_date_that_reads_the_two_columns_are_not_drawn():
    """A column empty in every row is left out — the rule an hour nobody has already follows."""
    records = [{"data": "06/10", "disciplina": "Redes de Computadores"}]
    (table,) = _tables(_html(records, month=""))           # dd/mm and no month: no year
    assert _head(table) == ["Data", "Disciplina"]
    assert _rows(table) == [["06/10", "Redes de Computadores"]]
    (table,) = _tables(_html(records))                      # control: with the send's month
    assert _head(table) == ["Mês", "Dia", "Data", "Disciplina"]


def test_every_weekday_and_every_month_is_the_module_s_own_word():
    """pt-BR, from the tables the module already had — the language of every word it writes."""
    week = [date(2026, 10, 5) + timedelta(days=i) for i in range(7)]
    rows = _rows(_tables(_html([{"data": d.strftime("%d/%m/%y"), "disciplina": "R"}
                                for d in week]))[0])
    assert [r[1] for r in rows] == ["seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom."]
    assert [r[1] for r in rows] == [f"{w}." for w in ef._WEEKDAYS]
    months = [date(2027, m, 1) for m in range(1, 13)]
    rows = _rows(_tables(_html([{"data": d.strftime("%d/%m/%Y"), "disciplina": "R"}
                                for d in months]))[0])
    assert [r[0] for r in rows] == ["jan.-27", "fev.-27", "mar.-27", "abr.-27", "mai.-27",
                                    "jun.-27", "jul.-27", "ago.-27", "set.-27", "out.-27",
                                    "nov.-27", "dez.-27"]
    assert [r[0] for r in rows] == [f"{ef._PT_MONTHS[m][:3]}.-27" for m in range(1, 13)]


# ── adverse: a table that is not a timetable is not touched ─────────────────────────────────

@pytest.mark.parametrize("records", [
    [{"data": "06/10", "disciplina": "Redes de Computadores", "sala": "Azul"}],   # a key outside
    [{"data": "06/10", "valor": "R$ 120,00"}],                                    # a ledger
    [{"data": "06/10", "horário": "19:00"}],                                      # no discipline
    [{"disciplina": "Redes de Computadores", "horário": "19:00"}],                # no date
])
def test_a_table_that_is_not_a_timetable_gets_no_derived_column(records):
    (table,) = _tables(_html(records))
    assert "Mês" not in _head(table) and "Dia" not in _head(table)
    assert _head(table)[0] == ef._header(next(iter(records[0])))   # the record's own order


# ── the twin: the colour of the Data cell ───────────────────────────────────────────────────

@pytest.mark.parametrize("records", [SENT, CARRIED, MODEL_ORDER])
def test_the_data_cell_has_the_colour_of_its_row_s_discipline(records):
    doc = _html(records)
    seen = set()
    for table in _tables(doc):
        head = [ef._fold_key(h) for h in _head(table)]   # a brought «mes» is headed «Mes»
        at = {name: head.index(name) for name in ("mes", "dia", "data", "disciplina")}
        for row in _cells(table):
            painted = _background(row[at["disciplina"]][1])
            assert _background(row[at["data"]][1]) == painted
            assert _background(row[at["mes"]][1]) == _background(row[at["dia"]][1]) == "#ffffff"
            seen.add(painted)
    # control: the rows have different colours, so «equal to its row's» is not «one colour»
    assert len(seen) >= 2 and "#ffffff" not in seen
    assert seen <= set(DEFAULT_PALETTE)


def test_the_data_cell_takes_the_tenant_s_accent_when_its_discipline_has_it():
    accent = "#123456"
    records = [{"data": "06/10", "disciplina": "Redes de Computadores"},
               {"data": "08/10", "disciplina": "Cálculo Numérico"}]
    colors = record_colors([records], EmailAppearance(accent_color=accent))
    (table,) = _tables(records_html(records, colors=colors, month=MONTH))
    first, second = _cells(table)
    assert _background(first[2][1]) == _background(first[3][1]) == accent
    assert _background(second[2][1]) == _background(second[3][1]) == DEFAULT_PALETTE[0]


def test_with_no_discipline_the_data_cell_is_not_painted():
    (table,) = _tables(_html([{"data": "06/10", "valor": "R$ 120,00"}]))
    assert all("background" not in style for row in _cells(table) for _, style in row)


# ── the text part does not move a byte ──────────────────────────────────────────────────────

SUBJECT = "Proposta de cronograma — [empresa]"
BODY = ("Boa tarde, Prof. [nome]!\nEspero que esteja bem.\n\n[aulas]\n\nSobre as aulas:\n"
        "• As aulas são online;\n• Qualquer alteração, você será comunicado;\n\nAtenciosamente,")
APPEARANCE = EmailAppearance(accent_color="#cfe8ff", department="Secretaria Acadêmica",
                             phone="55 11 0000-0000", email="secretaria@escola.exemplo.test")

#: sha256 of the text part, taken on the base (praxis ``081a0614``) — the text the proposal shows
#: and the «sim» compares. A change here is a change to what the requester confirms.
TEXT_DIGESTS = {
    "sent": "819a1e623d2b0de7e5a2981e7254269aec6ee319978bf98897cfc364ef3362ed",
    "model_order": "49b9f5ae7690ebf7c738ba16382b04679f87c13d23222f802d3dc53a74ea1f51",
    "carried": "6fc1489a59edc149dfa02697a656aebf2c8269ccee2bf293ff21a98c57b6390a",
}


def _forms(records):
    ctx = EmailContext(recipient_name="Teobaldo", tenant_name="Escola Exemplo", month=MONTH,
                       today=date(2026, 10, 22), persona_name="Secretaria",
                       custom_tags={"aulas": ""}, free_tag_values={"aulas": records})
    values = {"empresa": "Escola Exemplo", "nome": "Teobaldo", "aulas": records_text(records)}
    return render_email_forms(SUBJECT, BODY, values, ctx, appearance=APPEARANCE)


@pytest.mark.parametrize("name,records", [("sent", SENT), ("model_order", MODEL_ORDER),
                                          ("carried", CARRIED)])
def test_the_text_part_is_the_base_s_byte_for_byte(name, records):
    subject, text, doc = _forms(records)
    assert doc and "<table" in doc                          # an HTML e-mail: the path is taken
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == TEXT_DIGESTS[name]
    assert ef.email_digest(subject, text) == ef.email_digest(subject, text)


def test_the_text_digest_sees_one_byte():
    """Control: the pin is not blind — one cell changed, the digest moves."""
    _, text, _ = _forms(SENT)
    _, other, _ = _forms([{**SENT[0], "Disciplina": "Zoologia Aplicadb"}] + SENT[1:])
    assert hashlib.sha256(other.encode()).hexdigest() != hashlib.sha256(text.encode()).hexdigest()
    assert hashlib.sha256(text.encode()).hexdigest() == TEXT_DIGESTS["sent"]
