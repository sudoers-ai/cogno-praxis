"""The shared renderer: the four properties a vertical is allowed to rely on.

Written as gémeos — each property has the case that must hold and, where the property is a
REFUSAL, the case that must not. The PII one is the reason this file exists: ``_line`` iterates
over the CHOSEN specs and never over the record, so "every column that is not empty" cannot be
written by accident, and :func:`test_a_field_that_was_not_chosen_is_not_shown` is what makes
that a fact rather than a comment.
"""

from __future__ import annotations

import pytest

from cogno_praxis.render import (
    CHANNEL_ENV,
    CHANNEL_MARKDOWN,
    CHANNEL_PLAIN,
    CHANNEL_TELEGRAM,
    CHANNEL_WEB,
    CHANNEL_WHATSAPP,
    DEFAULT_CHANNEL,
    Field,
    bold,
    render_block,
    resolve_channel,
)

#: A record carrying MORE than any caller chooses — the shape every listing really has.
_ROWS = [
    {"day": "08/09", "group": "DE_09", "subject": "NoSQL", "status": "Confirmado",
     "teacher": "A_TEACHER_NOBODY_ASKED_FOR", "room": "SALA_404"},
    {"day": "30/09", "group": "DE_09", "subject": "Abertura", "status": "Remarcada",
     "teacher": "A_TEACHER_NOBODY_ASKED_FOR", "room": "SALA_404"},
]

_CHOSEN = ("day", "group", "subject")


@pytest.fixture(autouse=True)
def _no_ambient_channel(monkeypatch):
    """No test here inherits the box's channel — the default is a property under test."""
    monkeypatch.delenv(CHANNEL_ENV, raising=False)


# ── GÉMEO 1: empty data is a SENTENCE, never an empty block ───────────────────────────
def test_no_records_renders_the_caller_s_sentence_and_not_an_empty_string():
    out = render_block([], fields=_CHOSEN, empty="Não há aulas nesse período.")
    assert out == "Não há aulas nesse período."


def test_a_blank_empty_sentence_still_does_not_render_nothing():
    """The one shape this module exists to forbid, defended past the caller.

    A vertical that passes ``""`` — a config that resolved to nothing, an f-string over a
    missing value — would otherwise return the empty string, and an empty tool result reads
    downstream as "the tool had nothing to say", not as "there is nothing there"."""
    assert render_block([], fields=_CHOSEN, empty="   ").strip() != ""


def test_records_that_carry_none_of_the_chosen_fields_are_counted_not_hidden():
    out = render_block([{"room": "SALA_404"}, {"room": "SALA_404"}],
                       fields=_CHOSEN, empty="nothing")
    assert "2 record(s)" in out and "left out" in out
    assert "SALA_404" not in out       # counted, never quoted


# ── GÉMEO 2: one line gets no header of its own — and loses nothing ───────────────────
def test_a_single_record_has_no_header_line_and_no_bullet():
    out = render_block(_ROWS[:1], fields=_CHOSEN, empty="nothing",
                       group_by=lambda r: "Setembro de 2026", channel=CHANNEL_WHATSAPP)
    assert "\n" not in out
    assert not out.startswith("-")
    assert out == "*Setembro de 2026* · 08/09 · DE_09 · NoSQL"


def test_a_single_record_keeps_the_group_it_belongs_to():
    """The tempting reading of "no extra header" is to DROP it, and it is wrong.

    A listing grouped by day whose lines carry only a time would answer "when is my
    appointment?" with an hour and no date — an omission the contact cannot see."""
    out = render_block([{"time": "09:00"}], fields=("time",), empty="nothing",
                       group_by=lambda r: "quarta-feira, 9 de setembro")
    assert "quarta-feira, 9 de setembro" in out


def test_two_records_do_get_a_header_and_bullets():
    out = render_block(_ROWS, fields=_CHOSEN, empty="nothing",
                       group_by=lambda r: "Setembro de 2026", channel=CHANNEL_WHATSAPP)
    assert out == ("*Setembro de 2026*\n"
                   "- 08/09 · DE_09 · NoSQL\n"
                   "- 30/09 · DE_09 · Abertura")


# ── GÉMEO 3: an unknown channel degrades to plain text and never raises ───────────────
def test_an_unknown_channel_falls_to_plain_text():
    out = render_block(_ROWS, fields=_CHOSEN, empty="nothing",
                       group_by=lambda r: "Setembro", channel="carrier-pigeon")
    assert "*" not in out
    assert "Setembro" in out


def test_resolve_channel_separates_nobody_said_from_i_do_not_know_that_one():
    """Two different questions with two different answers, and collapsing them is a bug.

    An EMPTY channel is "nobody told me" and takes the deployment default; an unrecognised one
    is "somebody told me something new", which must render but must not guess a markup."""
    assert resolve_channel("") == DEFAULT_CHANNEL
    assert resolve_channel("carrier-pigeon") == CHANNEL_PLAIN


def test_the_environment_answers_when_the_caller_cannot(monkeypatch):
    """The only channel source that exists today — see the module docstring."""
    monkeypatch.setenv(CHANNEL_ENV, "markdown")
    assert resolve_channel("") == CHANNEL_MARKDOWN
    assert bold("x", "") == "**x**"
    monkeypatch.setenv(CHANNEL_ENV, "whatsapp")
    assert bold("x", "") == "*x*"


def test_the_argument_beats_the_environment(monkeypatch):
    monkeypatch.setenv(CHANNEL_ENV, "markdown")
    assert bold("x", CHANNEL_WHATSAPP) == "*x*"


def test_bold_per_channel_is_one_table():
    assert bold("Setembro", CHANNEL_WHATSAPP) == "*Setembro*"
    assert bold("Setembro", CHANNEL_MARKDOWN) == "**Setembro**"
    # No parse_mode is set by the gateway for Telegram, and the web widget renders no markdown:
    # any mark would arrive as visible asterisks. A fact about THIS deployment, in one place.
    assert bold("Setembro", CHANNEL_TELEGRAM) == "Setembro"
    assert bold("Setembro", CHANNEL_WEB) == "Setembro"
    assert bold("Setembro", CHANNEL_PLAIN) == "Setembro"


def test_bold_of_nothing_is_nothing_and_not_a_pair_of_asterisks():
    assert bold("", CHANNEL_WHATSAPP) == ""
    assert bold("   ", CHANNEL_WHATSAPP) == ""


# ── GÉMEO 4 (PII): a field the caller did not choose has NO path to the output ────────
def test_a_field_that_was_not_chosen_is_not_shown():
    """The negative twin, and the one the mutation targets.

    This ecosystem has already measured a formatter that emitted "every column that is not
    empty" putting a teacher's name and room number in front of a contact every day. The
    defence is not a filter — it is that ``_line`` loops over the chosen specs, so the dump
    cannot be expressed. Change that loop to ``record.items()`` and this test dies."""
    out = render_block(_ROWS, fields=_CHOSEN, empty="nothing",
                       group_by=lambda r: "Setembro")
    assert "A_TEACHER_NOBODY_ASKED_FOR" not in out
    assert "SALA_404" not in out
    assert "NoSQL" in out and "Abertura" in out


def test_the_same_records_with_the_field_chosen_do_show_it():
    """The other half: the absence above is the CHOICE, not an inability to render the key."""
    out = render_block(_ROWS, fields=(*_CHOSEN, "teacher"), empty="nothing",
                       group_by=lambda r: "Setembro")
    assert "A_TEACHER_NOBODY_ASKED_FOR" in out


def test_the_field_list_has_no_default_so_a_caller_cannot_forget_to_choose():
    with pytest.raises(TypeError):
        render_block(_ROWS, empty="nothing")      # type: ignore[call-arg]


# ── the exception-only field, #112's compression ─────────────────────────────────────
def test_an_ordinary_value_is_silent_and_an_unusual_one_is_not():
    spec = Field("status", ordinary=("Confirmado",))
    out = render_block(_ROWS, fields=("day", spec), empty="nothing")
    assert "Confirmado" not in out
    assert "Remarcada" in out


def test_ordinary_is_compared_without_case_or_padding():
    spec = Field("status", ordinary=("  confirmado ",))
    assert "Confirmado" not in render_block(_ROWS[:1], fields=("day", spec), empty="nothing")


def test_a_value_the_tenant_never_declared_counts_as_unusual():
    """The direction a mistake must take: an unknown status is SHOWN, not swallowed."""
    rows = [{"day": "08/09", "status": "Cancelada pelo professor"}]
    out = render_block(rows, fields=("day", Field("status", ordinary=("Confirmado",))),
                       empty="nothing")
    assert "Cancelada pelo professor" in out


# ── labels, emphasis, order and the rows nothing can place ───────────────────────────
def test_a_label_is_opt_in_and_absent_by_default():
    out = render_block([{"cnpj": "11.222.333/0001-81"}], fields=("cnpj",), empty="nothing")
    assert out == "11.222.333/0001-81"
    out = render_block([{"cnpj": "11.222.333/0001-81"}], fields=(Field("cnpj", label="CNPJ"),),
                       empty="nothing")
    assert out == "CNPJ 11.222.333/0001-81"


def test_emphasis_bolds_the_value_for_a_listing_that_has_no_header():
    out = render_block([{"name": "Padaria Sintética"}, {"name": "Clínica Sintética"}],
                       fields=(Field("name", emphasis=True),), empty="nothing",
                       channel=CHANNEL_WHATSAPP)
    assert out == "- *Padaria Sintética*\n- *Clínica Sintética*"


def test_the_caller_s_order_is_kept_and_a_repeated_group_repeats_its_header():
    rows = [{"d": "1", "g": "A"}, {"d": "2", "g": "B"}, {"d": "3", "g": "A"}]
    out = render_block(rows, fields=("d",), empty="nothing",
                       group_by=lambda r: r["g"], channel=CHANNEL_PLAIN)
    assert out.splitlines() == ["A", "- 1", "", "B", "- 2", "", "A", "- 3"]


def test_a_record_the_grouper_cannot_place_goes_last_and_is_never_swallowed():
    rows = [{"d": "1", "g": ""}, {"d": "2", "g": "B"}]
    out = render_block(rows, fields=("d",), empty="nothing",
                       group_by=lambda r: r["g"], channel=CHANNEL_PLAIN)
    assert out.splitlines() == ["B", "- 2", "- 1"]


def test_notes_ride_after_a_blank_line_untouched():
    out = render_block(_ROWS, fields=_CHOSEN, empty="nothing",
                       notes=("(This list covers the next 30 days.)", "   ", ""))
    assert out.endswith("\n\n(This list covers the next 30 days.)")
