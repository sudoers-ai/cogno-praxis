"""``cogno_praxis.charts`` draws only what it is handed, as the channel can show it (request 777e9b69).

The rules pinned: no invented value (every number written is a ``shown`` string handed in, and
nothing else that looks like a figure appears), the channel decides the format, the accessible
text version whenever a chart cannot render, and every limitation said. Values and labels are
invented.
"""
from __future__ import annotations

import re

import pytest

from cogno_praxis.charts import (BAR_WIDTH, CHANNEL_CAPS, MAX_POINTS, Dataset, Point, visualize,
                                 worth_a_chart)
from cogno_praxis.render import (CHANNEL_MARKDOWN, CHANNEL_PLAIN, CHANNEL_TELEGRAM, CHANNEL_WEB,
                                 CHANNEL_WHATSAPP)

WEEKS = Dataset("AI cost by week", (Point("2026-W43", 0.0, "R$ 0,0000"),
                                    Point("2026-W44", 1.0, "R$ 1,0000"),
                                    Point("2026-W45", 0.531, "R$ 0,5310")), time_ordered=True)
MODELS = Dataset("AI cost by model", (Point("openai:gpt-5-nano", 0.035, "R$ 0,0350"),
                                      Point("openai:gpt-4o-mini", 1.5, "R$ 1,5000")))

_FIGURE = re.compile(r"\d[\d.,]*")


def _figures(text: str) -> "set[str]":
    return set(_FIGURE.findall(text))


@pytest.mark.parametrize("channel", sorted(CHANNEL_CAPS))
@pytest.mark.parametrize("ds", [WEEKS, MODELS], ids=["weeks", "models"])
def test_every_figure_written_is_one_the_caller_handed_in(ds, channel):
    """No invented value: the figures in the output are the labels' and the ``shown`` strings',
    on every channel, chart or text."""
    out = visualize(ds, channel=channel).text
    handed = set().union(*(_figures(p.label) | _figures(p.shown) for p in ds.points))
    handed |= _figures(ds.title)
    assert _figures(out) <= handed | {str(MAX_POINTS)}, out
    for p in ds.points:
        assert p.shown in out                       # the tool's precision, verbatim


def test_whatsapp_gets_an_aligned_chart_in_a_monospace_block():
    v = visualize(MODELS, channel=CHANNEL_WHATSAPP)
    assert v.kind == "comparison" and v.text.splitlines()[1] == "```"
    rows = v.text.splitlines()[2:4]
    assert rows[0].startswith("openai:gpt-4o-mini") and rows[0].endswith("R$ 1,5000")
    assert rows[0].count("█") == BAR_WIDTH         # the largest value is the full bar
    assert rows[1].count("█") < rows[0].count("█")  # largest first


def test_a_time_ordered_set_is_a_trend_in_time_order():
    v = visualize(WEEKS, channel=CHANNEL_WHATSAPP)
    assert v.kind == "trend"
    labels = [ln.split()[0] for ln in v.text.splitlines()[2:5]]
    assert labels == ["2026-W43", "2026-W44", "2026-W45"]
    assert "R$ 0,0000" in v.text.splitlines()[2]   # a zero is a line, with no bar


@pytest.mark.parametrize("channel", [CHANNEL_TELEGRAM, CHANNEL_WEB, CHANNEL_PLAIN])
def test_a_channel_that_cannot_align_gets_the_text_version_and_is_told_why(channel):
    v = visualize(MODELS, channel=channel)
    assert v.kind == "text"
    assert "- openai:gpt-4o-mini: R$ 1,5000" in v.text and "█" not in v.text
    assert f"(this channel ({channel}) cannot align a chart: the text version)" in v.text


def test_markdown_gets_a_real_table_and_whatsapp_the_text_for_a_table():
    t = visualize(MODELS, kind="table", channel=CHANNEL_MARKDOWN)
    assert t.kind == "table" and "| openai:gpt-4o-mini | R$ 1,5000 |" in t.text
    w = visualize(MODELS, kind="table", channel=CHANNEL_WHATSAPP)
    assert w.kind == "text" and "shows no table" in w.text


def test_the_cap_is_said_never_silent():
    many = Dataset("t", tuple(Point(f"d{i:02d}", float(i + 1), f"R$ {i + 1},00")
                              for i in range(MAX_POINTS + 3)), time_ordered=True)
    v = visualize(many, channel=CHANNEL_WHATSAPP)
    assert f"(showing the last {MAX_POINTS} of {MAX_POINTS + 3} points (3 earlier not drawn))" \
        in v.text
    assert "d00" not in v.text and f"d{MAX_POINTS + 2:02d}" in v.text


def test_a_negative_value_has_no_bar_and_is_said():
    ds = Dataset("t", (Point("a", 2.0, "R$ 2,00"), Point("b", -1.0, "-R$ 1,00")))
    v = visualize(ds, channel=CHANNEL_WHATSAPP)
    assert "(1 negative value(s) have no bar; their value is written)" in v.text
    line_b = next(ln for ln in v.text.splitlines() if ln.startswith("b "))
    assert "█" not in line_b and line_b.endswith("-R$ 1,00")


@pytest.mark.parametrize("ds", [Dataset("t", (Point("só um", 3.0, "R$ 3,00"),)),
                                Dataset("t", (Point("a", 0.0, "R$ 0,00"),
                                              Point("b", 0.0, "R$ 0,00")))])
def test_nothing_to_compare_is_text_not_a_chart(ds):
    assert not worth_a_chart(ds)
    v = visualize(ds, channel=CHANNEL_WHATSAPP)
    assert v.kind == "text" and "not enough to compare" in v.text and "█" not in v.text


def test_CONTROL_an_unknown_kind_or_channel_never_raises():
    assert visualize(MODELS, kind="pizza", channel=CHANNEL_WHATSAPP).kind == "comparison"
    assert visualize(MODELS, channel="fax").channel == CHANNEL_PLAIN
