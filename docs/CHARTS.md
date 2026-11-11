# Charts — `cogno_praxis.charts`

The reusable visual layer for a read tool's STRUCTURED result: tables, comparisons, trends and
distributions, in the text a channel can show. It ships first inside the host's
`token_cost_analytics` (`visual=…`) for the bookkeeper's AI cost (request 777e9b69), and any
vertical can call it.

## The contract

`visualize(Dataset(title, points, time_ordered), kind="auto", channel="") -> Visual(text, kind, channel, limitations)`

- A `Point` is `(label, value, shown)`. The bar is drawn from `value`; the number written is `shown`,
  the CALLER's own rendering, kept verbatim. That keeps the tool's precision and its pt-BR format.
- **No invented value.** Nothing is computed for display: no percentage, average or variation. A
  distribution shows each part's bar, not its share, and a bar's length is never written as a
  number.
- `kind`: `auto` (a `trend` for a time-ordered set, otherwise a `comparison`), `table`,
  `comparison`, `trend`, `distribution`. An unknown kind is `auto`, and an unknown channel is
  `plain`. The function never raises on either.

## When to visualise (`worth_a_chart`)

At least two points, and at least one positive value. Anything less goes out as text, with the
line «not enough to compare».

## What each channel shows (`CHANNEL_CAPS`)

| channel | aligned chart | table | what is sent |
|---|---|---|---|
| `whatsapp` | yes (a ```` ``` ```` monospace block) | no | bars + values in a monospace block; a `table` request → the text version |
| `markdown` | yes | yes | bars in a code block; a real Markdown table |
| `telegram` | no (sent with no `parse_mode`) | no | the text version |
| `web` | no (plain `pre-wrap` widget) | no | the text version |
| `plain` | no | no | the text version |

These are facts about this deployment and come from `cogno_praxis.render`. A channel that starts
rendering more is changed here, in one table.

## The accessible text version, and limitations said

When a channel cannot show the chart, the output is one line per point (`- label: value`), followed
by the reason. Every limitation becomes a line in brackets, and the same lines are listed in
`Visual.limitations`:
- the cap (`MAX_POINTS` = 12; a trend keeps the most recent points);
- negative values, which have no bar;
- a chart replaced by text, and why.

Nothing is dropped in silence.
