"""Tables, comparisons, trends and distributions in the text a channel can show.

This is the reusable visual layer for a read tool's STRUCTURED result, and it ships first with the
bookkeeper's AI-cost report (request 777e9b69). A chart is a picture of a read, and it is held to
three rules, which are the request's own:

1. **No invented value.** The module draws only what the caller hands it. The number written
   beside a bar is the caller's ``shown`` string, verbatim: the tool's own precision and pt-BR
   format, which this module never re-formats or rounds. A bar's LENGTH is a picture of
   ``value`` and is never written as a number. There are no derived figures: no percentage, no
   average, no variation. A distribution shows each part's bar, not its share.
2. **The channel decides the format** (:data:`CHANNEL_CAPS`). On a channel that cannot align the
   columns of a chart, the module does not draw one. The ACCESSIBLE TEXT version — one line per
   point, label and value — goes out instead, with a sentence that says why.
3. **A limitation is said, never hidden.** Points left out by the cap, values a bar cannot draw
   (negative ones) and a chart replaced by text each become a line of :attr:`Visual.limitations`
   and appear in the text.

**The channels** are ``cogno_praxis.render``'s, and the facts about them are the ones that module
records. Nothing on the way out converts markup. WhatsApp renders a ```` ``` ```` monospace block,
so columns align there. Telegram is sent with no ``parse_mode`` and the web widget is plain
``pre-wrap``, so neither aligns nor renders a table: both get the text version. ``markdown`` gets a
real table. ``plain`` gets text.

**When to visualise** (:func:`worth_a_chart`): at least two points, and at least one positive value
a bar can draw. One point, or nothing to compare, is a sentence, not a chart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from cogno_praxis.render import (CHANNEL_MARKDOWN, CHANNEL_PLAIN, CHANNEL_TELEGRAM, CHANNEL_WEB,
                                 CHANNEL_WHATSAPP, resolve_channel)

#: The kinds a caller may ask for. ``auto`` picks: a time-ordered set is a ``trend``, any other
#: set a ``comparison``.
KINDS: "tuple[str, ...]" = ("auto", "table", "comparison", "trend", "distribution")

#: What each channel can SHOW, from what reaches it byte for byte (see the module docstring):
#: ``aligned`` is a monospace block in which columns line up; ``table`` is a rendered table.
CHANNEL_CAPS: "dict[str, dict[str, bool]]" = {
    CHANNEL_MARKDOWN: {"aligned": True, "table": True},
    CHANNEL_WHATSAPP: {"aligned": True, "table": False},
    CHANNEL_TELEGRAM: {"aligned": False, "table": False},
    CHANNEL_WEB: {"aligned": False, "table": False},
    CHANNEL_PLAIN: {"aligned": False, "table": False},
}

#: The widest bar, in blocks. The scale is the largest value shown.
BAR_WIDTH = 20
#: At most this many points are drawn. The rest are counted in a limitation line, never dropped
#: in silence.
MAX_POINTS = 12
_BLOCK = "█"
_PARTIAL = "▏▎▍▌▋▊▉"


@dataclass(frozen=True)
class Point:
    """One point: ``label``, the ``value`` a bar is drawn from, and ``shown``, the caller's own
    rendering of that value (the tool's precision and format), which is written as it is."""

    label: str
    value: float
    shown: str


@dataclass(frozen=True)
class Dataset:
    """What a tool hands this module. ``time_ordered`` means the points are in TIME order, oldest
    first. ``title`` is the caller's string, in the caller's language."""

    title: str
    points: "tuple[Point, ...]"
    time_ordered: bool = False


@dataclass(frozen=True)
class Visual:
    """What was rendered: the ``text``, the ``kind`` actually drawn (``text`` when no chart was
    drawn), the channel it was drawn for, and every limitation, said."""

    text: str
    kind: str
    channel: str
    limitations: "tuple[str, ...]" = field(default_factory=tuple)


def worth_a_chart(ds: Dataset) -> bool:
    """At least two points and something a bar can draw. Anything less is a sentence."""
    return len(ds.points) >= 2 and any(p.value > 0 for p in ds.points)


def _bar(value: float, top: float) -> str:
    if value <= 0 or top <= 0:
        return ""
    eighths = round(value / top * BAR_WIDTH * 8)
    full, part = divmod(max(1, eighths), 8)
    return _BLOCK * full + (_PARTIAL[part - 1] if part else "")


def _text_version(ds: Dataset, points: "Sequence[Point]") -> "list[str]":
    """The accessible version: one line per point, label and value, nothing else."""
    return [f"- {p.label}: {p.shown}" for p in points]


def visualize(ds: Dataset, *, kind: str = "auto", channel: str = "",
              max_points: int = MAX_POINTS) -> Visual:
    """``ds`` drawn as ``kind`` for ``channel``, or as its text version, with the reason, when
    that channel cannot show the chart. Never raises on a kind or a channel it does not know: an
    unknown kind is ``auto``, an unknown channel is ``plain`` (``render.resolve_channel``)."""
    chan = resolve_channel(channel)
    caps = CHANNEL_CAPS.get(chan, CHANNEL_CAPS[CHANNEL_PLAIN])
    asked = kind if kind in KINDS else "auto"
    drawn = asked if asked != "auto" else ("trend" if ds.time_ordered else "comparison")
    points = list(ds.points)
    limits: "list[str]" = []
    if drawn == "comparison" or drawn == "distribution":
        points.sort(key=lambda p: -p.value)        # largest first; the order is the picture
    cap = max(1, int(max_points))
    if len(points) > cap:
        hidden = len(points) - cap
        if drawn == "trend":
            points = points[-cap:]                 # a trend keeps the most recent
            limits.append(f"showing the last {cap} of {len(ds.points)} points "
                          f"({hidden} earlier not drawn)")
        else:
            points = points[:cap]
            limits.append(f"showing {cap} of {len(ds.points)} points ({hidden} not drawn)")
    title = ds.title.strip()
    head = [title] if title else []
    if not worth_a_chart(Dataset(ds.title, tuple(points), ds.time_ordered)):
        limits.append("not enough to compare: no chart, the values as text")
        return Visual("\n".join(head + _text_version(ds, points) + _said(limits)), "text",
                      chan, tuple(limits))
    if drawn == "table":
        if caps["table"]:
            rows = ["| item | value |", "|---|---|"]
            rows += [f"| {p.label} | {p.shown} |" for p in points]
            return Visual("\n".join(head + rows + _said(limits)), "table", chan, tuple(limits))
        limits.append(f"this channel ({chan}) shows no table: the text version")
        return Visual("\n".join(head + _text_version(ds, points) + _said(limits)), "text",
                      chan, tuple(limits))
    if not caps["aligned"]:
        limits.append(f"this channel ({chan}) cannot align a chart: the text version")
        return Visual("\n".join(head + _text_version(ds, points) + _said(limits)), "text",
                      chan, tuple(limits))
    negatives = [p for p in points if p.value < 0]
    if negatives:
        limits.append(f"{len(negatives)} negative value(s) have no bar; their value is written")
    top = max(p.value for p in points)
    width = max(len(p.label) for p in points)
    lines = [f"{p.label.ljust(width)}  {_bar(p.value, top).ljust(BAR_WIDTH + 1)} {p.shown}"
             for p in points]
    body = ["```"] + lines + ["```"]               # aligned = a monospace block
    return Visual("\n".join(head + body + _said(limits)), drawn, chan, tuple(limits))


def _said(limits: "Sequence[str]") -> "list[str]":
    return [f"({note})" for note in limits]


__all__ = ["BAR_WIDTH", "CHANNEL_CAPS", "KINDS", "MAX_POINTS", "Dataset", "Point", "Visual",
           "visualize", "worth_a_chart"]
