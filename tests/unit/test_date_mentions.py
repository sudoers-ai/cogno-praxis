"""``date_mentions`` — the reader of EVERY date named in a free sentence.

`resolve_date` reads the ONE expression a model hands a tool; `date_mentions` reads the
contact's whole sentence, for the host to check a held write's date against the one the contact
asked for (`cogno_host.asked_clock`). They are two doors over ONE set of rules: each mention is
resolved the SAME way `resolve_date` resolves it, so the pair can never disagree about a single
expression. The difference is the READING — `date_mentions` is whole-word and returns every
date, where `resolve_date` reads by sub-string and takes the first match.

These pin:
* the two doors agree form by form (the "one definition, two ports" property);
* the whole-word reading and the pt collision guard, which is exactly what a free sentence
  needs and the single-expression reader cannot give;
* each FORM the reader knows, on synthetic sentences invented for the test: every date read,
  no trap misread into a false date.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.scheduler import SchedulerError, SchedulerService, date_mentions
from cogno_praxis.scheduler.store import InMemoryAppointmentStore


def _svc(today: date) -> SchedulerService:
    return SchedulerService(InMemoryAppointmentStore(), today=lambda: today)


# ── one definition, two ports ────────────────────────────────────────────────────────────
#: Every form `resolve_date` resolves, each read in isolation. `date_mentions` must return
#: EXACTLY the one date `resolve_date` gives — the guarantee that the free-text door and the
#: single-expression door never disagree about what an expression means.
_TWO_PORT_FORMS = [
    "hoje", "amanhã", "amanha", "depois de amanhã", "today", "tomorrow",
    "day after tomorrow", "segunda", "terça", "quarta", "quinta", "sexta",
    "sábado", "domingo", "monday", "friday", "sexta que vem", "próxima sexta",
    "09/07", "9/7", "11/07", "9-7-26", "04/09/2026", "2026-07-11",
    "9 de julho", "11 de julho", "9 July 2026", "July 7",
]


@pytest.mark.parametrize("form", _TWO_PORT_FORMS)
def test_each_form_reads_the_same_date_as_resolve_date(form):
    today = date(2026, 7, 6)              # a Monday
    svc = _svc(today)
    resolved = date.fromisoformat(svc.resolve_date(form))
    assert date_mentions(form, today) == [resolved], (
        f"{form!r}: the two doors over one parser disagree")


def test_the_two_doors_read_a_free_sentence_differently_on_purpose():
    """`resolve_date` reads by sub-string the one expression a model passes it, so "a segunda
    opção" is Monday to it — right for a tool argument, wrong for a sentence. `date_mentions`
    reads by whole word and guards the pt ordinal, so the sentence yields no false day."""
    today = date(2026, 7, 6)
    assert _svc(today).resolve_date("a segunda opção") == "2026-07-13"   # sub-string: Monday
    assert date_mentions("a segunda opção às 10h", today) == []         # whole word + guard


# ── the pt collision guard and the ranges of "dia N" ─────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "quero a segunda opção, às 10h",      # ordinal, not Monday
    "é a terceira vez que peço",          # 'terceira' is not 'terça' at all
    "a segunda via do boleto",            # ordinal
    "pode ser a quinta parte?",           # ordinal
    "dia 45",                             # day-of-month out of range
    "dia 0 não existe",                   # idem
    "sabadão combinado",                  # not 'sábado' — whole word only
    "traga os últimos 30 dias",           # '30 dias' is a span, never 'dia 30'
])
def test_a_trap_yields_no_date(sentence):
    assert date_mentions(sentence, date(2026, 7, 6)) == []


def test_a_weekday_that_is_not_an_ordinal_still_reads():
    today = date(2026, 11, 13)            # a Friday
    assert date_mentions("hoje não dá, marca para sexta", today) == [
        date(2026, 11, 13), date(2026, 11, 20)]      # reads hoje AND next sexta (host splits them)
    assert date_mentions("segunda-feira às 15h", today) == [date(2026, 11, 16)]


def test_dia_n_is_the_next_day_of_month_today_or_later():
    assert date_mentions("marca pro dia 23", date(2026, 11, 4)) == [date(2026, 11, 23)]
    assert date_mentions("o dia 3 serve", date(2026, 11, 4)) == [date(2026, 12, 3)]  # rolled
    # "dia 30/09" is the slash date, read once — never also "dia 30"
    assert date_mentions("dia 30/09", date(2026, 9, 5)) == [date(2026, 9, 30)]
    # "dia 9 de julho" is the written form, read once — never also "dia 9"
    assert date_mentions("dia 9 de julho", date(2026, 7, 1)) == [date(2026, 7, 9)]


def test_dia_n_rolls_across_the_month_and_year_boundaries():
    # Nov has 30 days, so "dia 31" skips to December (the impossible Nov 31 is passed over).
    assert date_mentions("dia 31", date(2026, 11, 4)) == [date(2026, 12, 31)]
    # A day already past this month, late in December, rolls into next YEAR.
    assert date_mentions("dia 3", date(2026, 12, 10)) == [date(2027, 1, 3)]


def test_an_impossible_calendar_date_is_no_date():
    # An ISO shape with an out-of-range month/day, and an explicit-year dd/mm that cannot exist,
    # are both dropped rather than raising.
    assert date_mentions("na data 2026-13-40 nada", date(2026, 7, 6)) == []
    assert date_mentions("31/02/2026 não existe", date(2026, 7, 6)) == []


def test_depois_de_amanha_is_not_counted_as_amanha_too():
    today = date(2026, 7, 6)
    assert date_mentions("depois de amanhã", today) == [date(2026, 7, 8)]


def test_an_empty_sentence_names_no_date():
    assert date_mentions("", date(2026, 7, 6)) == []
    assert date_mentions("bom dia, tudo bem?", date(2026, 7, 6)) == []


# ── every FORM, on synthetic sentences invented for the test ─────────────────────────────
#: One sentence per class the reader handles, written from scratch for this test (neutral,
#: generic — not derived from any real message), each asserting the WHOLE set of dates the
#: sentence names. ``today`` is a Monday, 2026-06-01. The expected dates follow `resolve_date`'s
#: rules: the next weekday strictly after today; a bare day/month rolled to today-or-later.
_ISO = date.fromisoformat
_BY_CLASS = [
    # (class, sentence, {iso dates})
    ("relativa", "pode ser amanhã?", {_ISO("2026-06-02")}),
    ("depois de amanhã", "fica para depois de amanhã então", {_ISO("2026-06-03")}),
    ("hoje + dd/mm (duas datas)", "hoje não, troque para 18/06",
     {_ISO("2026-06-01"), _ISO("2026-06-18")}),
    ("dia N sem mês", "encerra no dia 23", {_ISO("2026-06-23")}),
    ("dia N, outro", "o dia 9 fica bom", {_ISO("2026-06-09")}),
    ("dia da semana", "combinamos na quinta", {_ISO("2026-06-04")}),
    ("N de <mês>", "a entrega é 9 de julho", {_ISO("2026-07-09")}),
    ("ISO", "o prazo é 2026-08-15", {_ISO("2026-08-15")}),
    ("duas dd/mm numa frase", "de 10/06 para 12/06",
     {_ISO("2026-06-10"), _ISO("2026-06-12")}),
    ("mês por extenso só", "qualquer dia de agosto", set()),      # a span, no single day
    ("intervalo", "na próxima semana", set()),
    ("armadilha: contagem", "nos últimos 30 dias", set()),       # '30 dias' is not 'dia 30'
    ("armadilha: dia fora de 1–31", "o dia 45 não existe", set()),
]


@pytest.mark.parametrize("cls,sentence,expected", _BY_CLASS, ids=[c[0] for c in _BY_CLASS])
def test_each_form_reads_its_dates_and_misreads_none(cls, sentence, expected):
    assert set(date_mentions(sentence, date(2026, 6, 1))) == expected, cls


def test_resolve_date_really_rejects_the_spans_that_name_no_day():
    """A guard on the guard: `resolve_date` must actually REJECT a vague week or a month — so the
    empty cases above are proving the shared rules, not a reader that simply reads nothing."""
    svc = _svc(date(2026, 9, 6))
    for span in ("próxima semana", "setembro", "esse mês"):
        with pytest.raises(SchedulerError):
            svc.resolve_date(span)
