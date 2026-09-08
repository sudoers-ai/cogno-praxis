"""The block a contact reads — ONE renderer, called by every vertical.

Every READ tool in this repo answers with text, and that text is not consumed by a machine: it
is handed to the SUPEREGO's voicer as ``# Data gathered by the executor``, and the voicer is
told to keep figures intact. So whatever a read tool writes is, in practice, what a person on
WhatsApp reads. Four verticals were each inventing that layout alone.

## This is EXTRACTED, not invented

``coordinator`` #112 did it once, for one tool, and measured it: the same class listing went
from 34 lines / 3838 characters to 4 lines / 506, by doing five things. Those five things are
this module, and nothing else is:

1. records GROUPED under a bold header, in the order the caller sorted them;
2. one record = ONE line, fields joined by ``·``, and **no labels** — the header and the
   column order carry the meaning that ``Turma: X | Data: Y`` was spending width on;
3. only the fields the caller CHOSE, one at a time;
4. a field that is only worth showing when it is UNUSUAL (a status that is not the ordinary
   one) is silent otherwise;
5. empty is a SENTENCE, never an empty block.

**What did not generalise, said rather than forced.** #112 renders a row it could not date with
the OLD labelled form — every column of it — on the reasoning that a row which failed parsing is
the one whose every column is worth showing. That is a defensible carve-out for a spreadsheet
importer and it is exactly the shape rule 3 exists to forbid, so it is NOT here: a record this
module cannot place still renders its CHOSEN fields, and goes last. A caller that wants the old
dump has to write it itself, in its own file, where a reviewer can see it.

## What this module does NOT do — the list matters more than the list of what it does

* **It does not choose the fields.** ``fields=`` is required and has no default. Which columns
  of a record may be seen is the vertical's business and a person's exposure; a shared renderer
  guessing it is how "every non-empty column" ships. There is deliberately NO way to say
  "everything": the parameter is a list of keys, so the dump cannot be expressed.
* **It does not redact.** It cannot: masking needs PROVENANCE (whose datum is this, and did the
  reader supply it), which lives in ``cogno_anima``'s outgoing-PII backstop over the VOICED
  reply. This module reduces what is offered; the backstop decides what may leave.
* **It does not know the channel.** ``channel=`` is a parameter with an environment fallback,
  and the fallback is not a convenience — it is the only source there is. See below.
* **It does not localise.** Group headers, labels and the ``empty`` sentence are the caller's
  strings, in the caller's language. Only :func:`money_brl` is opinionated, and only about
  pt-BR grouping.
* **It does not escape.** A value containing ``*`` reaches the channel as-is. Escaping is
  per-channel and lossy (Telegram's MarkdownV2 escapes fifteen characters), and a renderer that
  silently rewrites a person's data is worse than one that shows an odd asterisk.
* **It does not split, truncate or count characters.** Message limits are the sender's.
* **It is not for a machine-readable answer.** ``companies.company_search`` returns a ``repr``
  the host parses with ``ast.literal_eval``; a tool whose output is PARSED must not come
  through here.

## Why the channel is a PARAMETER nobody can pass yet, and what that costs

Read out of the gateway and the bridge on 2026-09-08, because the shape of this module depends
on it:

* **Nothing converts markup on the way out.** ``cogno_gateway`` hands ``OutboundMessage.text``
  to the provider byte for byte (``evolution.py``, ``cloud.py``, ``telegram.py``, ``web.py``),
  and ``cogno_host.channels._send`` "não decide nada nem altera o resultado". There is no
  ``**`` → ``*`` rewrite anywhere in nineteen repos. So whatever a tool writes is what the
  provider is asked to render.
* **Telegram is posted with no ``parse_mode``**, which means Telegram renders NOTHING —
  ``*x*`` and ``**x**`` both arrive as visible asterisks. That is why :data:`CHANNEL_TELEGRAM`
  maps to no markup here. It is a fact about today's gateway, not about Telegram; the day the
  gateway sets ``parse_mode`` this table gains one character, in one place.
* **The channel does not reach an MCP skill.** ``cogno_mcp`` has no tool context at all — only
  the model's own arguments cross the wire — and ``cogno_cortex.ToolContext`` carries
  ``backend``/``trace_id``/``metadata`` with no channel in any host adapter's metadata. The
  ONLY host→server side channel is the subprocess environment the assembler builds
  (``COGNO_SCHEDULER_*``, ``COGNO_BOOKKEEPER_*``, …), which is why :data:`CHANNEL_ENV` exists.
  **State the cost plainly: that environment is per SERVER PROCESS, so a tenant reachable on
  WhatsApp and on the web gets one answer for both.** This module makes the choice explicit and
  overridable; it does not create the per-turn signal, and pretending otherwise would be worse
  than the ``**`` literal it replaces.

## The 600 characters nobody mentions

``cogno_gateway.chunker`` splits every outbound message at **600 characters, 6 chunks**, and
past that it truncates at a sentence and appends ``" (…)"``. Both defaults are hard-wired in
production (``ChannelConfig.max_chars`` is never passed by the host). #112's own numbers land
either side of that line: the flat block was 3838 characters — six chunks and a truncation — and
the grouped one is 506, a single message. Compression here is not typography; it is whether the
last class in the list reaches the contact at all. This module does not enforce the limit (see
above), but a caller choosing how many fields to show should know where the cliff is.

## The ids that look like decoration

A line may carry what reads as noise — an 8-hex ``appointment_id``. It is not decoration and it
may not be tidied away: ``cogno_anima.tools.IdProvenanceDispatcher`` refuses a write whose id did
not appear, as a SUBSTRING, in a successful read earlier in the same turn (``wanted in r``).
Drop the id from a listing and every follow-up write on this vertical is refused. Same for the
``[STATUS]`` bracket, which ``cogno_praxis.scheduler.grounding`` and the host's booking notifier
both read with a regex. So: put such a field LAST, where the eye arrives after the facts — never
remove it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Union

__all__ = [
    "CHANNEL_ENV",
    "CHANNEL_MARKDOWN",
    "CHANNEL_PLAIN",
    "CHANNEL_TELEGRAM",
    "CHANNEL_WEB",
    "CHANNEL_WHATSAPP",
    "DEFAULT_CHANNEL",
    "Field",
    "SEP",
    "bold",
    "money_brl",
    "render_block",
    "resolve_channel",
]

#: The four channels this repo has a rendering for. A value outside them is not an error —
#: see :func:`resolve_channel`.
#: The literals are ``cogno_gateway``'s own (``InboundMessage.channel`` is
#: ``"telegram" | "whatsapp" | "web"``), so a host that ever gains the per-turn signal can pass
#: it through untranslated.
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_TELEGRAM = "telegram"
CHANNEL_WEB = "web"
CHANNEL_MARKDOWN = "markdown"
CHANNEL_PLAIN = "plain"

#: Where a deployment says which channel it serves, when the caller cannot.
CHANNEL_ENV = "COGNO_RENDER_CHANNEL"

#: The bold delimiter per channel — the one table this module exists to own.
#:
#: WhatsApp takes a SINGLE asterisk. The doubled form is Markdown's, and it is what #112
#: shipped, on a stated premise ("WhatsApp and Telegram both render ``**text**``") that the
#: gateway contradicts: nothing converts, so `**x**` reaches WhatsApp with its asterisks
#: showing. Telegram and the web widget render no markup at all today — Telegram because the
#: gateway sets no ``parse_mode``, the widget because it is ``whitespace-pre-wrap`` with no
#: markdown renderer — so both take the empty mark, which is a statement about THIS deployment
#: and changes here, in one place, when either of those does.
_BOLD = {
    CHANNEL_WHATSAPP: "*",
    CHANNEL_TELEGRAM: "",
    CHANNEL_WEB: "",
    CHANNEL_MARKDOWN: "**",
    CHANNEL_PLAIN: "",
}

#: What an unconfigured deployment gets. NOT ``plain``: a shared renderer whose default is "no
#: formatting" ships inert, and inert is indistinguishable from working until someone looks at a
#: phone. This box serves WhatsApp, and no caller can pass the channel yet (see the module
#: docstring), so this constant IS the production answer until the environment says otherwise.
DEFAULT_CHANNEL = CHANNEL_WHATSAPP

#: Between fields of one record. A middle dot, not a pipe: it is quieter than the data.
SEP = " · "

#: When a caller's ``empty`` is itself blank. A block that says nothing is the one shape this
#: module exists to make impossible, so the last line of defence is a constant, not a caller.
_NOTHING = "(nothing to show)"


def resolve_channel(channel: str = "") -> str:
    """The channel to render for: the argument, else the environment, else the default.

    An UNRECOGNISED channel falls to :data:`CHANNEL_PLAIN` — plain text is readable everywhere,
    and a tool that raises because a new transport arrived would take the answer down with it.
    An EMPTY channel is a different case and takes :data:`DEFAULT_CHANNEL`: "nobody said" is not
    "somebody said something I do not know"."""
    named = (channel or os.environ.get(CHANNEL_ENV, "") or "").strip().lower()
    if not named:
        return DEFAULT_CHANNEL
    return named if named in _BOLD else CHANNEL_PLAIN


def bold(text: str, channel: str = "") -> str:
    """``Setembro`` → ``*Setembro*`` on WhatsApp, ``**Setembro**`` on Markdown, bare on plain.

    Empty in, empty out — never a pair of naked asterisks."""
    body = str(text or "").strip()
    if not body:
        return ""
    mark = _BOLD.get(resolve_channel(channel), "")
    return f"{mark}{body}{mark}"


#: en-US grouping onto pt-BR grouping in ONE pass — ``str.translate`` maps from the ORIGINAL
#: string, so the separators swap instead of chasing each other.
_TO_PT_BR = str.maketrans({",": ".", ".": ","})


def money_brl(value: float) -> str:
    """``1250.0`` → ``"R$ 1.250,00"``. pt-BR grouping: '.' thousands, ',' decimal.

    The rule and its cost were established by ``bookkeeper`` #116, which found the two halves of
    one conversation speaking two grammars: of the 19 money tokens contacts typed at that
    vertical, 18 carried a comma decimal; of the 160 the tools answered with, 159 carried a dot.
    Nothing downstream reconciles them and the voice prompt forbids trying, so a localising
    voicer is the one that gets flagged by the preserved-term backstop.

    This is the SECOND copy of three lines, and it is a copy on purpose rather than by accident:
    the canonical one is ``cogno_praxis.bookkeeper.server._brl``, whose file belongs to another
    author this turn. ``tests/unit/test_the_money_has_one_grammar.py`` pins the two BYTE FOR BYTE
    over a table that includes the values #116 was written for, so they cannot drift in silence
    — the same treatment this repo already gives the duplicated ``cogno-mcp`` meta keys. Collapse
    them into one the day the same author holds both files; the pin survives the collapse."""
    return f"R$ {value:,.2f}".translate(_TO_PT_BR)


@dataclass(frozen=True)
class Field:
    """One CHOSEN field of a record.

    ``key`` is the mapping key to read. ``label`` is normally EMPTY — a listing gives a bare
    value its meaning, and a label repeated down thirty lines is the width #112 bought its
    compression back from. Spend one only where the line stands alone and the value cannot
    speak for itself (``CNPJ 11.222.333/0001-81``).

    ``ordinary`` is the carve-out that made #112's listing short: values so unremarkable that
    printing them is noise ("Confirmado" on every row). A field whose value is in ``ordinary``
    is silent; anything else — including a status the tenant never declared — is shown, because
    the point is to surface the exception, and an unknown value is exceptional by definition.
    Compared case- and whitespace-insensitively.

    ``emphasis`` bolds the VALUE. It exists for the listing that has no group header to bold —
    a flat roster of companies still needs one thing per line the eye lands on first — and it is
    off by default because a line where everything is bold is a line where nothing is."""

    key: str
    label: str = ""
    ordinary: tuple[str, ...] = ()
    emphasis: bool = False


FieldSpec = Union[Field, str]
Record = Mapping[str, object]


def _spec(f: FieldSpec) -> Field:
    return f if isinstance(f, Field) else Field(str(f))


def _cell(record: Record, field: Field, channel: str) -> str:
    """This record's value for one chosen field, or ``""`` if it is absent or ordinary."""
    raw = record.get(field.key)
    value = "" if raw is None else str(raw).strip()
    if not value:
        return ""
    folded = value.casefold()
    if any(folded == str(o).strip().casefold() for o in field.ordinary):
        return ""
    if field.emphasis:
        value = bold(value, channel)
    return f"{field.label} {value}".strip() if field.label else value


def _line(record: Record, specs: Sequence[Field], channel: str) -> str:
    """One record as one line — and ONLY the chosen fields.

    The loop is over ``specs``, never over ``record``. That is the whole PII discipline of this
    module in one statement: a key the caller did not choose has no path to the output, so the
    "every column that is not empty" listing cannot be written by accident. Turn this into
    ``record.items()`` and ``test_render_block.py::test_a_field_that_was_not_chosen_is_not_shown``
    fails, which is what that test is for."""
    return SEP.join(c for c in (_cell(record, s, channel) for s in specs) if c)


def render_block(
    records: Sequence[Record],
    *,
    fields: Sequence[FieldSpec],
    empty: str,
    channel: str = "",
    group_by: Optional[Callable[[Record], str]] = None,
    notes: Sequence[str] = (),
) -> str:
    """Render records as the block a contact reads. See the module docstring for the rules.

    ``records`` arrive in the order the caller sorted them and leave in it: this function never
    reorders, with one exception it states — a record ``group_by`` cannot place goes to the END,
    so an unplaceable row is never swallowed by the header above it. ``group_by`` returns the
    HEADER TEXT (already in the contact's language); ``""`` means "no group".

    ``notes`` are appended after a blank line, in order — the footer #112 uses to say a window
    was applied. They are the caller's sentences and are not touched.

    **One record does not get a header of its own**, but the header is not DROPPED either: it is
    joined into the single line. Dropping it is the tempting reading of "no extra header" and it
    is wrong in the one case that matters — a listing grouped by DAY whose lines carry only the
    TIME would answer "when is my appointment?" with an hour and no date. An omission the
    contact cannot see is the expensive kind.

    A record with no renderable chosen field is LEFT OUT and SAID: the tail carries a count and
    nothing else — one bit, never a measurement of what was dropped, the same shape as #112's
    window footer."""
    ch = resolve_channel(channel)
    specs = tuple(_spec(f) for f in fields)

    placed: list[tuple[str, str]] = []
    loose: list[str] = []
    skipped = 0
    for record in records:
        line = _line(record, specs, ch)
        if not line:
            skipped += 1
            continue
        head = str(group_by(record) or "").strip() if group_by else ""
        if head:
            placed.append((head, line))
        else:
            loose.append(line)

    rows: list[tuple[str, str]] = placed + [("", ln) for ln in loose]

    if not rows:
        body = str(empty or "").strip() or _NOTHING
    elif len(rows) == 1:
        head, line = rows[0]
        body = f"{bold(head, ch)}{SEP}{line}" if head else line
    else:
        chunks: list[str] = []
        current = ""
        for head, line in rows:
            if head and head != current:
                chunks.append(("\n" if chunks else "") + bold(head, ch))
            current = head
            chunks.append(f"- {line}")
        body = "\n".join(chunks)

    tail = [f"({skipped} record(s) carried none of the fields shown and were left out.)"] if skipped else []
    tail += [n for n in (str(x).strip() for x in notes) if n]
    return f"{body}\n\n" + "\n".join(tail) if tail else body
