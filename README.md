# cogno-praxis

**The Cogno business verticals, as standalone MCP servers.**

πρᾶξις = *action / practice* — the **applied layer**: ready-made, open-source
business verticals on top of the Cogno substrate. Each vertical is an **independent FastMCP server** the host orchestrates
via [`cogno-mcp`](https://github.com/sudoers-ai/cogno-mcp). Verticals own their
domain logic + data (behind their own store ports); the host stays the thin
**assembler** — persona, pipeline, dispatcher composition, RBAC, orchestration rules.

```
vertical (FastMCP server) ──(stdio/HTTP)──▶ cogno-mcp MCPDispatcher ──▶ EGO / cogno-soma
   owns: domain logic + data                                              owns: orchestration
```

The architecture follows MCP's grain: verticals are **separate processes**, decoupled
by protocol, deployable/scalable/ownable independently (even by external partners).
Two layers of "business rules" stay separate: **orchestration** rules live in the host;
**domain** rules live in the vertical.

## Verticals

| Vertical | What it is | Tools |
|---|---|---|
| **scheduler** | the agenda capability — ships the **SECRETARY** persona, the universal reception/scheduling front door for any client | `list_schedulable_hosts`, `resolve_date`, `check_availability`, `book_appointment`, `block_schedule`, `list_appointments`, `reschedule_appointment`, `confirm_appointment`, `complete_appointment`, `cancel_appointment`, `get_schedule_settings`, `set_schedule_settings`, `set_auto_confirm` |
| **bookkeeper** | the financial capability — ships the **BOOKKEEPER** persona (parent SaaS ANALYST): records income/expenses, tracks clients, produces summaries. See [`docs/BOOKKEEPER.md`](docs/BOOKKEEPER.md) | `add_income`, `add_outcome`, `get_summary`, `list_clients`, `search`, `remove_by_search`, `get_usage`, `math`, `help` |
| **coordinator** | the academic capability — ships the **COORDINATOR** persona: reads class schedules across a tenant's course spreadsheets, checks grade/attendance deadlines, estimates a professor's OWN pay from tenant-declared figures (a coordinator/supervisor: any professor's, or every professor's one block each), finds open slots, swaps a class, and mails a professor their classes as a calendar. See [`docs/COORDINATOR.md`](docs/COORDINATOR.md) | `get_professor_schedule`, `get_professor_info`, `check_deadlines`, `get_weekly_briefing`, `check_ibope_status`, `daily_checks`, `estimate_professor_pay`, `find_replacement_slot`, `confirm_swap`, `preview_schedule_to_calendar`, `send_schedule_to_calendar`, `record_class_response` |
| **companies** | the brand-registration capability — **transversal**: it belongs to no persona's domain, and a front-desk persona carries it beside its own vertical. Rows are keyed by the accent-folded company name (a frozen key fold, deliberately not the ecosystem's `casefold`: changing it needs a key migration), so registering one again UPDATES it — and a field a registration or an update is not given is left exactly as it was. Scoped by identity: staff see the business's companies, anyone else sees the ones they registered | `company_registration`, `company_search`, `list_companies`, `company_update`, `company_delete` |

The tool lists are the `@mcp.tool` functions of each vertical's `server.py`, in the order the
server registers them; a host's RBAC decides which of them a given reader is offered.

Two behaviours worth knowing before reading further, each written up in its own document:

- **A discipline that names nothing is said, not guessed.** `get_professor_schedule` asked for a
  `discipline` that matches no subject answers with the unfiltered upcoming classes and OPENS
  with a `NO SUCH DISCIPLINE` line naming the disciplines the sheet knows — a line a host may
  read back ([`docs/COORDINATOR.md`](docs/COORDINATOR.md),
  [`docs/HOST_INTEGRATION.md` §6.2](docs/HOST_INTEGRATION.md)).
- **AI cost is not a ledger figure.** The BOOKKEEPER's `get_usage` returns no number: it says
  where AI usage is metered. Its prompts send a question about AI cost by cut (message, day,
  conversation, persona, user, month) to the host's `token_cost_analytics` when that tool is on
  the table ([`docs/BOOKKEEPER.md`](docs/BOOKKEEPER.md)).

More verticals (restaurant, veterinary, …) follow the same shape.

### The calendar export (`send_schedule_to_calendar`)

The coordinator's second write, and the only one that leaves the house: it reads the
professor's upcoming classes — through the very same `get_professor_schedule` and therefore the
same role scoping — and e-mails them as **one** `.ics` with **one `VEVENT` per class**. One
message with every class in it, because that is what a calendar imports in a single action.

Three things about it are worth knowing before you wire it:

- **The `UID` is derived from CONTENT** — class group + discipline + date (+ hour when the sheet
  has one), normalized and digested — never from the spreadsheet ROW. A row index is a
  *position*: insert one class at the top of the sheet and every index below it shifts, so
  row-derived identifiers would make the next send duplicate the professor's whole term instead
  of updating it. Send it again after a room change and the entries update in place.
- **Delivery is a port, and the mailbox belongs to ONE tenant.** `CalendarSender`
  (`coordinator/ics.py`) is injected into `build_server(service, sender=…)` when the host has
  already resolved it, or `build_server(service, sender_for=…)` — a callable asked **on every
  calendar tool call**, which is what a process serving more than one tenant needs.
  `coordinator/mailer.py` is the SMTP adapter over
  [`cogno-herald`](https://github.com/sudoers-ai/cogno-herald) — an **optional** dependency
  (install it from git; it is not on PyPI yet, so it is not declarable as an extra). The mailbox
  is **only ever what THIS tenant declared** (`COGNO_COORDINATOR_SMTP`, or whatever `sender_for`
  answers): nothing declared → **no sender**, and the tool refuses honestly and sends
  **nothing**. It deliberately does **not** fall back to the deployment's `SMTP_*` — a booking
  invite does, because every tenant's confirmations should leave, but a class calendar is an
  institution writing to its own faculty and a tenant that declared no mailbox has not asked to
  write to anybody. It never swallows a message either.
- **Every path that did not send RAISES**, so the MCP bridge reports `ok=False` /
  `side_effect=False` and the turn is never recorded as a write that did not happen. The one
  non-error answer starts with `SENT:`.
- **The question is asked by a READ, not by the gate.** `preview_schedule_to_calendar` is the
  read-only half: same arguments, same rows, same refusals — it answers with the exact count,
  the period the filter actually applied and the recipient the send would resolve, prefixed
  `NOT SENT`, and mails nothing. It exists because a confirmation gate stops the send by NAME
  *before* it can read, so the skill never learns what it would be sending and the only thing
  left for any layer downstream to show a professor is the raw argument. Measured live on
  2026-09-06: the contact was asked *"Confirmo: esta ação — 2026-09. Posso seguir?"*. A gate
  cannot ask the skill's question for it; a read that runs can. Same relationship
  `find_replacement_slot` has with `confirm_swap`. The period clause is **conditional** — a
  request that filtered by no month claims none, because echoing the caller's own string back
  is how a listing spanning two months gets proposed as one of them.

Zones: an hour travels with the tenant's `TZID` (`COGNO_COORDINATOR_TZ`, stamped by the host
from its own `tenant_tz`). No hour column, or no declared zone → an **all-day** event. Never a
floating time, never raw UTC.

### Templated e-mail fields (`cogno_praxis.email_fields`)

A tenant writes an e-mail template — a subject and a body — with markers, and the host sends it
when a request asks for it. This module is the **closed list of markers** and the pure code that
fills them; the host owns the send, the confirmation and the audit. The model writes the free
text of the request (`[conteudo]`) and the values of the tenant's FREE tags, copied from the
conversation, the persona's rules or a tool it read this turn; every other value is filled in code.

**The markers are the eight that serve every persona; a persona's own values are the TENANT's
tags (R-T13, 2026-10-22).** The owner's rule: «preciso de algo genérico. Quando entrar uma persona
nova, faço via tags personalizadas, senão teria que fazer via código». `GENERIC_FIELDS` are THE
list — `known_markers(persona)` answers it for every persona — and come from the tenant's records,
the tenant, the request or the clock, so every persona's template may use them and every persona
fills them:

| generic marker | value |
|---|---|
| `[nome]`, `[email]` | the recipient's name and address, from the tenant's records (the address stops the send when empty, even if the body never quotes it) |
| `[empresa]` | the tenant's name |
| `[mes]` | the month of the request, `YYYY-MM` → «outubro/2026» |
| `[data]` | today in the tenant's zone, in words: «7 de outubro de 2026» |
| `[assinatura]` | the display name of the persona that sends |
| `[solicitante]` | the name of the person who asked for the e-mail |
| `[conteudo]` | the free text, at most once per template, never in the subject |

**No persona has markers of its own.** `FIELD_PROVIDERS` is EMPTY, and a test pins it so: a new
persona is served by the tenant's tags, never by code. Until R-T13 the `COORDINATOR` had five,
filled by a field provider from one read of its schedule; they are now the tenant's FREE tags
(below), and the coordination fills them by COPYING what its tools print — the arithmetic stays in
the tools (`docs/COORDINATOR.md`, «The tools PRINT every value a templated e-mail copies»):

| the coordination's tag (the tenant's, FREE) | what the persona passes, copied from |
|---|---|
| `[aulas]` | records `mês · dia · data · horário · disciplina · turma`, one per class, from `get_professor_schedule` (`dia` and `mês` are derivations of `data`, checked by code) |
| `[disciplinas]` | records `{disciplina}`, the disciplines of those classes |
| `[valor_por_aula]` | text: the `Valor por aula` line of `estimate_professor_pay` |
| `[valores_por_bonus]` | records `{faixa, valor}`: the `*Valores por faixa de bônus*` section |
| `[total]` | text: the line under `*Total*` (or the base, when the rules declare no band) |

`EMAIL_FIELDS` is the eight. The provider machinery stays, generic, over the empty registry: a
`FieldProvider` would **declare** fields and read nothing (this module imports no service);
`provider_fields(fields)` answers `{}` for every template, and `template_needs_month(fields)`
whether it needs the month at all (it says `[mes]`) — a template that needs none must never make
anybody invent one.

`[cpf_cnpj]` was removed by the owner's decision (no personal data beyond the recipient's own
name and address) and `[contrato]` arrives with the attachment in phase E3; a template using
either is refused, for every persona. So is any `[` that does not open a known marker — that is
what catches `[nmoe]`. There is no marker for the sender's mailbox: `[assinatura]` is the
persona and `[solicitante]` the person who asked, and no marker quotes a third person's data.

**The tenant's own markers — company tags with a FIXED value (2026-10-21).** Beside the
markers above, a tenant may declare tags of its own, `{name: value}`, valid in EVERY persona's
template: `[horario_atendimento]` → «de segunda a sexta, das 8h às 18h». The name is
`CUSTOM_TAG_NAME` (`[a-z][a-z0-9_]{1,30}`: lowercase, no accent, no space) and is never a marker
of `EMAIL_FIELDS` nor a reserved name (`[cpf_cnpj]`, `[contrato]`); the coordination's five are
ordinary names since R-T13. The value is plain text, one line
or several (line breaks and tabs are the only control characters), at most
`MAX_CUSTOM_TAG_CHARS` (500) characters, and a tenant holds at most `MAX_CUSTOM_TAGS` (50). It is
the business's DATA and never an instruction: a host that lets it into a prompt fences it like
any other text of the tenant.

- `normalise_custom_tags(raw)` → `(stored, refusals)`, the SAVE door: every refusal named, and
  nothing stored on any refusal. `parse_custom_tags(raw)` is the TURN door: what the save would
  keep, the rest dropped, never a refusal. `custom_tag_problems(name, value)` is the one rule
  both apply.
- `validate_template(…, custom_tags=…)` accepts the tenant's tags (a mapping, or just the names)
  beside the persona's markers, in any persona; with the values, a tag that spans lines is refused in the
  subject. A name that cannot be a tag is ignored, so it unlocks nothing. With no `custom_tags`
  the verdict is the one of before, byte for byte. `removed_tags=` is the turn's reading: the
  names of tags the tenant REMOVED, so a template whose tag was removed after it was saved still
  exists; a name never declared (a typo) is refused at both doors.
- `fill_email_fields` fills a company tag from `EmailContext.custom_tags`, before any provider and
  in any persona — the value is the tenant's, not a persona's read. A tag the context no longer
  carries is `missing` with «tag personalizada removida» (its source:
  «as tags personalizadas da empresa»), so the send asks the requester instead of sending.
- Tags filled by code, tags of one persona only and HTML values are not here: a FIXED tag's
  value is plain text, and the HTML form of an e-mail shows it escaped (its own `http(s)://` URLs
  as links, like the template's text; a FREE tag's value is what the conversation said, never
  linked).

**FREE company tags — no fixed value, filled from the conversation (2026-10-22).** The owner:
«preciso q seja flexivel e chamada pelo usuario»; «o template terá tags que devem ser preenchidas
conforme as mensagens com o agente». A company tag whose value is EMPTY is FREE: it is stored in
the SAME map as `{name: ""}` (so every non-empty string stored before still reads as the fixed tag
it was), and `free_tags(tags)` names the free ones. Everything else is the company tag's: the
name grammar, the reservation of the standard markers and of the reserved names, the removed
path.

- The value comes from the conversation: `EmailContext.free_tag_values` (`{name: value}`, the
  host takes it from the executor's call). `fill_email_fields` fills a free tag from it as ONE
  line of plain text (`free_value`: every run of blanks and line breaks one space, so it never
  breaks a subject), at most `MAX_CUSTOM_TAG_CHARS` characters and with no control character
  (`free_value_problems`). A value given for a fixed tag, a standard marker or a name that is no
  tag is never read: a fixed tag stays fixed.
- **Or a LIST OF RECORDS (R-T13)** — the rows a tool printed: `[{key: value}, …]`, at most
  `MAX_RECORDS`, each record at most `MAX_RECORD_KEYS` (12) keys of at most `MAX_RECORD_KEY_CHARS`
  (40) characters, each cell ONE line of plain text of at most `MAX_CUSTOM_TAG_CHARS` (a number as
  written, `None` as empty; a yes/no, a list or an object is refused). `free_records_problems` is
  the rule and `free_records` the reading; a list the rule refuses is `missing` with that
  sentence, an empty list is a value nobody said. Its text is `records_text`, its HTML a TABLE
  (below). A list for a tag the SUBJECT cites is `missing` — pass `in_subject=` (the subject's
  markers); without it `render_email` refuses the multi-line subject.
- **Where a cell came from.** `record_cells_unverified(records, month=…, is_literal=…)` →
  `((index, key), …)` of every non-empty cell that is neither LITERAL — the host's
  `is_literal(cell)`: written in a successful read of this turn, under the host's fold — nor a
  DERIVATION checked here, generic for any record with a `data` cell: `dia` must be the weekday of
  that date and `mês` its month, the year from the cell or else from `month` (the send's). A wrong
  derivation is unverified like a cell nobody read; a record with no `data` holds `dia`/`mês` to
  the literal rule. A `data` cell carrying a year passes only as its literal `dd/mm` with the year
  of the send's month (a wrong year is unverified); in the HTML, a `data` cell `dd/mm` of the
  send's month is shown `dd/mm/aa` (`records_html(…, month=…)`), never in the text. Only keys come
  back, never a cell. The host asks it before handing a list to
  the fill, and asks the requester instead of composing when anything comes back.
- Not said → `missing`, with «o pedido não disse o que pôr nesta tag» (its source:
  «o que o solicitante disser na conversa»), so the send ASKS. With the tenant's hint the reason ends
  with it: «… nesta tag: a disciplina da aula remarcada».
- The hint is optional, for a free tag only, the tenant's plain text on ONE line, at most
  `MAX_CUSTOM_TAG_HINT_CHARS` (120) characters: `custom_tag_hint_problems(name, hint, tags)` is
  the rule, `normalise_custom_tag_hints(raw, tags)` the SAVE door (every refusal named, nothing
  stored on any refusal) and `parse_custom_tag_hints(raw, tags)` the TURN door;
  `EmailContext.custom_tag_hints` carries them to the fill. A host that puts a hint in a prompt
  shapes and fences it like any other text of the tenant.

- `validate_template(subject, body, persona=…)` → the refusals in words, `()` when valid. A
  template may use `known_markers(persona)` — the eight — and the tenant's tags; the verdict is
  the same for every persona (R-T13: a template of the front desk that says `[aulas]` is saved
  when the tenant declared that tag, and refused as an unknown marker when it did not — exactly as
  the coordination's). From 2026-10-22 until R-T13 the coordination's five were valid in its
  template only; from 2026-10-21 until 2026-10-22, in every persona.
- `known_markers(persona=None)` → the eight, as a person reads them. Every refusal that lists the
  markers lists exactly these.
- `fields_for(persona)` → the markers that persona can FILL: the eight (no persona has a
  provider). `CoordinatorService.email_context` is gone with the provider (R-T13): nothing reads a
  persona's data into an e-mail but the persona itself, through its tools.
- `fill_email_fields(fields, context, persona=…, in_subject=…)` → `(values, missing)`; a
  non-empty `missing` names each field, its source and the reason, and the send asks instead of
  sending. The answer is the same for every `persona=`. The generic markers are filled from
  `EmailContext` (`recipient_name`, `recipient_email`, `tenant_name`, `month`, `conteudo`,
  `today`, `persona_name`, `requester_name`); a marker the template does not use is never asked
  for.
- `render_email(subject, body, values)` → one-pass substitution (a marker inside a value stays
  text); `email_digest(subject, body)` is what a proposal records and a confirmation compares.
- `render_email_forms(subject, body, values, context, appearance=…)` → `(subject, text, html)`,
  the ONE place the two forms of an e-mail are joined (2026-10-22). `text` is what the requester
  is shown and confirms and what `email_digest` covers. `html` is `""` unless the BODY carries a
  FREE tag whose value is a list of records (R-T13; until then, a provider's marker); every other
  e-mail stays plain text, byte for byte `render_email`'s — a figure alone included.
- **Tables are GENERIC: a list of records in, tables out** (the owner's rule: «preciso de algo
  genérico» — a new persona's e-mail is made with tags, not with code).
  - **The records.** `as_records(value)` reads a list of records: each `{key: text}`, at most
    `MAX_RECORDS`.
  - **The tables.** `records_html(records, colors=…)` draws one column per key, in order, and
    leaves out a column nobody filled.
  - **The text.** `records_text(records)` writes one line per record.
  - **Three keys have a meaning,** compared folded:
    - `turma` splits the records into one table (and one text block) per value, titled «Turma
      <value>», in the order of the code;
    - `disciplina` colours each distinct value with ONE colour across the e-mail
      (`record_colors`: by first appearance, the tenant's accent first, `DEFAULT_PALETTE`
      cycled);
    - a record whose keys are only `mes`/`dia`/`data`/`horario`/`disciplina`/`turma` is the
      dated line «06/10 (ter) 19:00 — Disciplina».
  - **Any other record is one line by how many keys it shows** (the group key aside, R-T13): ONE
    key → its value (a list of values: «Redes»); TWO filled keys → «first: second» («Sem bônus:
    R$ 2.880,00»); more → «chave: valor · …». In HTML, records of one key are a LIST, not a
    one-column table.
- `render_email_html(…)` → the HTML document, after the owner's model e-mail:
  - A free tag whose value is a list of records, ALONE on a line of the template, is its tables
    (`records_html`), the colours counted over every list of the e-mail. The coordination's
    `[aulas]` is one table per class group, Mês · Dia · Data · Horário (when the group has one) ·
    Disciplina, the discipline coloured; its `[valores_por_bonus]` a two-column table (Faixa ·
    Valor); its `[disciplinas]` a list. No value is bold by its NAME (until R-T13 `[total]` and
    `[valor_por_aula]` were): emphasis is the template's.
  - **The tenant's text is simple rich text — four rules, nothing else of Markdown.** A blank
    line separates paragraphs. A line opened by «•» or «·» is a list item, and a line opened by
    «-» stays a line with its dash. A line that ends with «:» and is at most
    `MAX_HEADING_CHARS` (40) characters is a bold title. An `http(s)://` URL in the tenant's own
    text (or a FIXED company tag's value) is a link. A value the model, a read or the
    conversation wrote is never linked, and that includes a FREE tag's.
  - **Header and signature.** A header carries the sender's name: the appearance's, else the
    tenant's. When the tenant configured a signature, a block follows: the logo on the left with
    a thin rule, then the persona's name in bold, department, phone, e-mail and site, and below
    them up to four social links (each its icon when one is configured, else its name).
  - **Safe by construction.** Every value and the template's own text are escaped, and the
    styles are inline. The only images are the logo and the icons the appearance configured
    (`http`/`https`, with `alt`). No style sheet, no script, no tracking pixel.
  - **The same e-mail.** One pass, like the text. A table is drawn only from rows whose text IS
    the value the text part carries.
- **The text of a list of records.** The coordination's `[aulas]` is a «Turma X» block per class
  group, each line «06/10 (ter) 19:00 — Disciplina» with the weekday — byte for byte what its
  provider wrote before R-T13, from the records its tools print (pinned over a corpus,
  `tests/unit/test_the_coordination_by_the_generic_path.py`). When the e-mail goes out as HTML and
  the tenant configured a signature, its lines follow the body after a blank line
  (`email_signature_text`).
- **The tenant's appearance** (`EmailAppearance`): sender name, accent colour (`#RRGGBB`), logo
  URL, department, e-mail, phone, site, and up to four social links (`{label, url, icon_url}`).
  `normalise_email_appearance(raw)` → `(stored, refusals)` is the SAVE door: every refusal is
  named and nothing is stored on any. A URL is `http://` or `https://` with a host; `javascript:`,
  `data:` and every other scheme are refused, and so are blanks and quotes. There is no free HTML.
  `parse_email_appearance(raw)` is the TURN door: it drops what the save would refuse, field by
  field and link by link.

**Prompt-only personas.** Two personas ship here with **no tools of their own** — just the
four prompt slots (`system`, `voice`, `scope`, `limits`) as package data, loaded by the host's
`PersonaSpec`: **`closer/`** (a commercial diagnostic that runs the tenant's declared
checklist) and **`interviewer/`** (interviews, forms and checklists, one question per turn,
a consolidated summary at the end). They get the host's *system* skills like every persona
(the date anchor and `resolve_date`, staff notify/directory) and nothing else. The persona's
display name is never in these files — `system.txt` says `{identity_label}`/`{tenant_name}`
and the host overlays the tenant's `display_name` — so one prompt serves every tenant's
"Carol" or "Tony". The CONTACT's name can also travel by reference instead of in line:
`cogno_praxis.contact_wording.by_reference(vertical, slot, text)` swaps every sentence that
carries `{identity_label}` for a wording that points at the name through `{contact_reference}`,
which the host fills (see `docs/HOST_INTEGRATION.md`); the files themselves do not change. Any domain script (a content calendar, a campaign table) belongs in the
tenant's `custom_rules`, not in the base prompt: a base prompt that carries a domain script
competes with the tenant's own and the model obeys both (measured on the CLOSER, 2026-09-05).

**Capability vs persona.** `scheduler` is the *capability* (the agenda machine); the
**SECRETARY** is the default *persona* that ships with it (prompt slots in
`scheduler/prompts/`) — the out-of-the-box front door that works for any company with
zero config. A company that needs a richer receptionist adds its **own** persona
host-side (via cogno-persona), targeting this same `scheduler` capability and composing
extra tool sources with `CompositeDispatcher` — **without** touching the scheduler.

## Quickstart — a complete agent in 15 minutes

The fastest way to *feel* the whole stack: `examples/secretary_demo.py` runs the
full cognitive pipeline (cogno-soma over the cogno-anima stages) against local
Ollama, with this repo's scheduler vertical served as a real MCP subprocess and
the bundled SECRETARY persona doing the talking:

```bash
# 1. local models (the download dominates the 15 minutes)
ollama pull qwen3:8b && ollama pull nomic-embed-text

# 2. the Cogno chain (PyPI soon — from git for now, one command)
pip install "git+https://github.com/sudoers-ai/cogno-homeo" \
            "git+https://github.com/sudoers-ai/cogno-synapse" \
            "git+https://github.com/sudoers-ai/cogno-anima" \
            "git+https://github.com/sudoers-ai/cogno-soma" \
            "cogno-mcp[mcp] @ git+https://github.com/sudoers-ai/cogno-mcp"

# 3. this repo + the demo
git clone https://github.com/sudoers-ai/cogno-praxis && cd cogno-praxis
pip install -e .
python examples/secretary_demo.py --trace     # --trace shows the cognition live
```

Then just talk, in any language:

```
você> oi, queria marcar uma consulta com o dr silva amanhã às 9 da manhã
  [NOUMENO]  "Hello, I would like to schedule an appointment with Dr. Silva tomorrow at 9…"  (pt → en)
  [NER]      ACTION_REQUEST · NEUTRAL · domains=['HEALTH'] · pii_risk=NONE
  [ID]       route=EGO · goal=NEW · turn=1
  [EGO]      resolve_date(expression=tomorrow) ✓
  [EGO]      check_availability(host_id=dr_silva, date=2026-07-11) ✗   ← Saturday: rejected
  [EGO]      book_appointment(host_id=dr_silva, date=2026-07-13, time=09:00, …) ✓
  [JUDGE]    approved=True
SECRETARY> Oi, Ana! 😊 Amanhã, 11/07, não tem expediente aos sábados, então sua
           consulta com o Dr. Silva foi marcada para o próximo dia útil, 13/07, às 9h. ✅
```

That weekend recovery is the pipeline working as designed: the vertical's
working-day rule rejected the tool call, the EGO self-corrected, the judge
approved, and the voice explained — all on a free 8B local model.

## Run a vertical

```bash
pip install -e .                    # from a clone of this repo; pulls the mcp SDK
python -m cogno_praxis.scheduler.server      # serves the demo over stdio
```

The host connects to it with cogno-mcp:

```python
import sys
from cogno_mcp import MCPDispatcher, stdio_session

async with stdio_session(sys.executable, args=["-m", "cogno_praxis.scheduler.server"]) as s:
    dispatcher = await MCPDispatcher.create(s)
    # bind to the SECRETARY persona + run the pipeline:
    await pipe.run_turn(ctx, cfg, dispatcher=dispatcher)     # cogno-soma
```

Tool **annotations** (`readOnlyHint` / `destructiveHint`) flow through cogno-mcp into
the EGO's read-only mask + confirmation gate — e.g. `cancel_appointment` is destructive,
so the EGO holds it for confirmation.

## Anatomy of a vertical (`scheduler`)

- `store.py` — domain types (`Host`, `Appointment`) + an `AppointmentStore` **port**
  (Protocol) with an in-memory default. Appointments are structured domain data, not
  conversation memory, so the vertical owns its store (host plugs a real DB adapter);
  `cogno-engram` stays for episodic/KG memory.
- `service.py` — pure scheduling logic (book / cancel / availability / status
  lifecycle + the "from tomorrow on" rule) over the store.
- `server.py` — the thin FastMCP wrapper exposing the service as annotated tools.
  `build_server(service)` is the only injection seam (see `examples/run_with_db.py`).
- `prompts/` — the bundled **SECRETARY** persona slots (system / scope / limits / voice),
  loaded by the host via `cogno-persona`. The capability is persona-agnostic; SECRETARY
  is simply its default face.

A vertical's tool **wins the name** over a host builtin (the dispatcher is first-wins and
module sources come first) — if a vertical ships a tool, it is because that tool matters to
the domain. The flip side: a model then sees *your* shell, so improvements to the host's
builtin never reach personas using your module. Put the behaviour in `service.py` and keep
both shells thin — `resolve_date` exports its parser **and** its spoken-form renderer, which
the host's builtin imports rather than copying. See
[`docs/HOST_INTEGRATION.md` §6.1](docs/HOST_INTEGRATION.md).

## The Cogno ecosystem

`cogno-praxis` is one organ of **[Cogno](https://github.com/sudoers-ai)** — a family of
small, composable, Apache-2.0 libraries that together form a complete
conversational-agent platform. Each library owns a single concern and stays
infra-agnostic; a **host** assembles them into a running agent:

![The Cogno ecosystem](docs/assets/cogno-ecosystem.svg)

The open-source libraries are the organs; the **host is the body** that joins
them. Our reference host — `cogno-host`, with its `cogno-ui` dashboard — is the
private product layer, but it holds no special powers: everything it does rides
on the public seams documented in each library's `docs/HOST_INTEGRATION.md`, so
you can assemble a body of your own.

## Development

```bash
pip install -e ".[dev]"
pytest tests/unit -q            # service + server (in-process), no network
pytest tests/integration -q     # scheduler server over stdio via cogno-mcp (the real loop)
                                # + the Postgres store, against `cogno_praxis_test` on the
                                # local server — taken from COGNO_PG_DSN if the shell exports
                                # one, else libpq's PGHOST/PGPORT/PGUSER/PGPASSWORD (whose
                                # defaults are what CI's postgres service serves). Auto-skips
                                # if nothing is listening. Those tests DROP TABLE, so the
                                # database NAME is never taken from any of them: it is always
                                # `cogno_praxis_test`. COGNO_TEST_PG_DSN overrides, and a name
                                # without "test" in it is refused at collection.
ruff check cogno_praxis tests examples && mypy cogno_praxis      # as CI runs them
python examples/host_min.py     # spawn the server + run a reception flow
```

CI runs the two suites together under a coverage gate
(`pytest tests -q --cov=cogno_praxis --cov-fail-under=90`).

## Documentation

Every `.md` of this repository.

- [`docs/HOST_INTEGRATION.md`](docs/HOST_INTEGRATION.md) — how a host connects a vertical: the
  boundary, connect + bind, the personas and their prompt slots, persistence, the tool policy the
  EGO's gates read, adding a vertical, and §8, the environment each vertical's server reads.
- [`docs/BOOKKEEPER.md`](docs/BOOKKEEPER.md) — the financial vertical: its tools, why
  `remove_by_search` asks a second question, and what counts as a source for a figure.
- [`docs/COORDINATOR.md`](docs/COORDINATOR.md) — the academic vertical: deadlines, the discipline
  that names nothing, the free slot, the e-mail context.
- [`docs/BOOKKEEPER_PLAN.md`](docs/BOOKKEEPER_PLAN.md) — **historical.** The approved plan that
  ported the bookkeeper, in three phases across this repository and the host. It names files in
  other repositories and a count of tools that has since grown; `docs/BOOKKEEPER.md` is the
  vertical as built.
- [`LOGGING.md`](LOGGING.md) — every log event the library emits, the class of every value a line carries, and what is never logged (no name, no id, no text of the tenant's).
- [`CHANGELOG.md`](CHANGELOG.md) — every change, newest first.

Apache-2.0.
