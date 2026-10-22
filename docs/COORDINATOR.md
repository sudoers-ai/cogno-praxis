# The `coordinator` vertical

The **coordinator** is a Cogno business vertical, a standalone FastMCP server the host
orchestrates via `cogno-mcp`. It backs the **COORDINATOR** persona: an academic coordinator
assistant that reads class schedules across a tenant's course spreadsheets and manages swaps. Its
tools and the calendar export are described in the [README](../README.md#verticals). This file
holds the notes about its prompts that the README does not.

## Deadlines: the ones OPEN now, and the RULES a teacher must follow

`prompts/system.txt` gives the executor a hard tool mapping. Two different questions both say
"deadline":

- **which deadlines are OPEN now** (which disciplines are inside the grade/attendance window
  today) is a read of the institution's records. It goes to `check_deadlines(professor?)`.
- **the deadline RULES a teacher must follow** (what is due, by when, after each class) is not a
  record. When the institution publishes those rules, the host offers its documents to the
  persona through `consult_documents(query)`, and the mapping sends the question there, «when it
  is among this turn's tools».

The mapping used to have one line for both, «Grade/attendance deadlines →
check_deadlines(professor?)». Asked «what deadlines does the teacher have to meet?», the executor
called `check_deadlines` 5/5 on a rehearsal tenant, with `consult_documents` on the table and the
host's generic documents duty in the prompt. A generic duty did not move it (still
`check_deadlines` 5/5 in an offline A/B). The two mapping lines did (`consult_documents` 5/5),
and a records control («which disciplines have a grade deadline expiring this week?») stayed on
`check_deadlines` 5/5. A duty written for every persona does not beat a mapping written for this
one, so the fix belongs here, in the persona's own mapping.

The two lines are the replay's bytes. They are not padded to the arrow column the neighbouring
lines use, and aligning them would make them a byte string nobody measured. The question as asked
is ambiguous (the rules, or the deadlines open now); this mapping sends it to the rules, and
reading both was not measured.

**The condition closes the RULES line.** `consult_documents` is the HOST's tool, and the host
offers it only on a turn whose reader has a published document to read. This is the first prompt
in this repo that names it, and without the condition the mapping would send the question to a
tool that is not on that turn's table. The condition sits at the END of the line, after the
arrow: that version measured the same as the first cut (the question 5/5 on `consult_documents`,
the records control 5/5 on `check_deadlines`, on turns that had the tool on the table), and a
version with the condition BEFORE the arrow scored 4/5 and was discarded.

**The judge reads the reply with `prompts/limits.txt` as it is.** That file lists the tools a
schedule fact, deadlines included, may come from, and `consult_documents` is not in that list.
Measured with it unchanged, the judge APPROVED the correct reply 5/5 and REJECTED 5/5 a control
reply that invents a deadline. So `limits.txt` does not change.

`tests/unit/test_coordinator_deadline_rules_read_the_documents.py` pins that the two lines are in
the mapping in the old line's place, that the old line is gone, that the RULES line ends with its
condition, that the file with the old line put back is `main`'s byte for byte, and that every
other prompt of every vertical is unchanged.

## A `discipline` that names nothing is dropped and said (M6-c, 2026-09-30)

`get_professor_schedule(discipline=…)` filters by subject, typo-tolerant
(`service._fuzzy_match_discipline`). An executor that fills it with the name of a PROGRAMME
(«MBA em …») instead of a discipline matched no row, and the tool answered «No classes found.» — a
false sentence about a professor who has classes next week (the trace-2056 shape).

It now follows the `unmatched_turma` precedent. When the argument matches no subject in the
caller's scoped read (judged BEFORE the month filter, so a discipline that exists in another month
is not a miss), `ReadReport.unmatched_discipline` records it, `ReadReport.known_disciplines` holds
the subjects that read DOES contain (at most `_KNOWN_DISCIPLINES_MAX`, free slots left out, only
what the caller may see), and the list is the upcoming classes WITHOUT the filter, under the
default window. The tool's text OPENS with a `NO SUCH DISCIPLINE` line (above the classes, not
under them — 2026-10-06): it says the name matches no discipline, asks for that as the reply's
first sentence, names the disciplines and tells the executor to call again with one of them. As a
footer under the listing it was dropped from the reply 3 times in 5 on a real read
(`tests/unit/test_the_miss_opens_the_listing.py`). Unlike an unmatched `turma` (which returns nothing — a
guessed group sends a professor to the wrong room), a dropped discipline filter still answers the
question «what are my classes?». A caller that passes no `report` keeps the empty list: an
unfiltered list nobody marks as unfiltered would be a wrong answer.
`tests/unit/test_coordinator_unmatched_discipline.py`.

**The list is a CLOSED alphabet, with one writer and one reader (2026-10-06, VQD-2(a)).** The host
reads the footer back to ask the contact «Não encontrei X. Você quis dizer: A / B?» with names
COPIED from it, so every name is written as a JSON string literal (`"Bancos NoSQL", "Redes"`) by
`footers.unmatched_discipline_line` and read back only by `footers.parse_unmatched_discipline`
(both exported from `cogno_praxis.coordinator`). The list used to be joined with `", "`, and a
discipline whose own name carries a comma came back as several names that are on no sheet. For a
plain name the asked value keeps its bytes; only the list gained its quotes.
`tests/unit/test_footers.py`.

**Each discipline is listed ONCE, by its base name (2026-10-06).** A secretary appends a status
note to a discipline instead of replacing it, so one discipline can sit on the sheet as «Redes»,
«Redes - Aula adiada» and «Redes - reposição do dia 22/09». The list held all three cells, and the
host's «Você quis dizer» offered the same discipline three times. `_known_disciplines` now cuts the
note (`service._discipline`, the last spaced dash) when the WHOLE note is a STATUS note
(`CoordinatorService._is_status_note`), and keeps the first spelling per fold, sorted under the
fold as before. The closed list of status notes:

- the tenant's `POSTPONED_LABELS`, read by `_is_postponed_note`, the same comparison
  `_is_postponed` makes for the pay;
- the make-up note («Reposição», «reposição do dia 22/09») and the cancelled note («Cancelada»,
  «Aula cancelada»), in `service._FOOTER_STATUS_NOTE`. They are used for the list only, and change
  nothing for pay or for free slots.

Any other dash is part of the name: «Laboratório - Redes» stays whole, and so does «Oficina -
Reposição de Conteúdos». The asked value and the rest of the footer are unchanged.
`tests/unit/test_known_disciplines_base_name.py`.

## A free slot written as a sentence that carries its label is still a free slot (2026-10-01)

`FREE_SLOT_LABELS` (e.g. «Livre, Reposição») used to be compared against the WHOLE subject cell.
A professor's sheet that marks an open slot «Espaço Reservado para Reposição (se necessário)»
therefore had no open slots at all, and `find_replacement_slot` answered «No open slots in the
next 21 days» to a contact asking which days were free to move a class (an owner's incident on
the coordinator persona).

The owner's rule, which adds nothing to the tenant's configuration (`service._is_free_by_word`):
a cell that is not a label on its own is FREE when (a) it carries a `FREE_SLOT_LABELS` label as a
WHOLE word under the module's `_norm` fold («Livreto» does not carry «livre»), and (b) the row is
NOT a class — nobody in the professor column, no discipline the read knows, and no configured
class group in the cell. The known disciplines (`_known_class_names`) are the `_discipline` of
every row of the WHOLE read (every spreadsheet) except skip rows, whole-cell labels and the rows
(a) could make free. A whole-cell label is free as before, whoever is in the professor column.

(b) is what keeps the turn-105 guard of the pay estimate: «Redes - Reposição» is the make-up OF a
class (it has a professor, and «Redes» is a known discipline) and is paid; «<discipline> - Aula
adiada» stays a postponed class; a discipline whose name contains «reposição» is a known name.
The same entries feed `confirm_swap` (a slot the read offers is one the swap accepts) and the pay
estimate.

`ReadReport.free_by_word` counts how many of the slots `find_replacement_slot` RETURNED were read
this way, and the footer says so («N of the open slots above are written on the sheet as a
sentence that carries the free-slot label…»). It is a count of rows ON the list — not of anything
left out, which is why it is not a bit like the window lines — so the trace shows the rule working.
`tests/unit/test_coordinator_free_slot_by_word.py`.

## A holiday written with its name is skipped, by its base name (2026-10-21)

`SKIP_LABELS` marks the rows that are not classes («Recesso», «Feriado», «Férias»…). The comparison
read the WHOLE subject cell. A secretary writes a holiday the way she writes every exception: she
appends its name to the label, «Feriado - Independência do Brasil». That whole cell is no label, so
the row was a class named after the holiday. It showed up in five places:
- in the professor's agenda;
- in the discipline list of the «você quis dizer…?» footer;
- in the pay estimate, as one class (`PayLine.classes=1`);
- in the supervisor's faculty-pay block, as «1 aula» with no professor, when the row has none;
- in the swap refusal, which said the date «already has a class scheduled».

`CoordinatorService._is_skip` now skips a row when the whole cell is a label, or its BASE name is
a label or BEGINS with one as a whole word. The base name is `service._discipline` (the text before
the last spaced dash), the same reader the status notes of the discipline list use above. A whole
word is `service._has_phrase` with `at_start=True`: the label, then the end, a space or any
character that is not part of a word. It is the module's one definition of a whole word, the one
the free-slot labels are read with.

The labels still decide what a holiday is:
- «Feriado» alone is skipped, as before.
- «Feriado Nacional - Tiradentes» has the base name «Feriado Nacional», which begins with the word
  «Feriado». It is skipped under a tenant that declares only «Feriado» (the real one does) and
  under the defaults, which hold «Feriado Nacional» itself. «Feriado Nacional», «Feriado-Ponte» and
  «Feriado: Tiradentes» are skipped the same way.
- «Laboratório - Redes» and «Redes - Feriado» are classes. Their base names are «Laboratório» and
  «Redes», and a label word after the dash is not the base name.
- «Feriados Escolares» and «Feriados e Festas» are classes: «Feriados» is a longer word. So is
  «Fisica» under a label «Fis».
- «Gestão de Férias» is a class: the label «Férias» is a word of it, but not the first.

The widening does not take an OPEN slot. A cell that carries a `FREE_SLOT_LABELS` label as a whole
word keeps the verdict it had: it is skipped only when it, or its base name, IS a label. «Reservado
para Reposição» with nobody in the professor column begins with the default label «Reservado», and
it stays the free slot the owner's rule made it (see «A free slot written as a sentence» above), so
`find_replacement_slot` still offers it.

`aggregate(include_skip=True)` still returns the row. `tests/unit/test_coordinator_skip_reads_the_base_name.py`.

## `confirm_swap`: an empty `professor` is the caller (2026-10-14)

The service has always read `professor=""` as the caller's own classes for anyone who is not the
coordination (`CoordinatorService._visible`), like the schedule reads. The signature did not say
so: `professor: str` had no default, so the published schema put it in `required`. A host that
decides from `required` whether a held write is a complete proposal would ask a professor «which
professor?» about their own class. `professor` now defaults to `""` and the description says empty
is the caller; `original_date` and `new_date` stay required (keyword-only, so `professor` keeps
its place as the first property). `tests/unit/test_confirm_swap_professor_is_optional.py`.

For the COORDINATION an empty `professor` is refused, recoverably («Which professor's class?
Nothing was swapped…»): an oversight caller (`_OVERSIGHT_ROLES`, the predicate `_visible` reads)
sees the whole master schedule, and the swap used to take the FIRST class found on
`original_date`, whoever taught it. Naming the professor swaps that class, as before.

## The e-mail context: the classes and the pay of one month, from ONE read (E1, 2026-10-06)

`CoordinatorService.email_context(professor=…, role=…, identity_label=…, period="YYYY-MM")` is
what a templated e-mail about one professor's month is filled from (`cogno_praxis.email_fields`,
README «Templated e-mail fields»). It reads the schedule ONCE and returns the month's PAYABLE
classes and the `PayEstimate` built from those same rows: the pay window (`_pay_window`, the month
in full) filtered by `_payable`, the rows `estimate_professor_pay` prices. So the classes an e-mail
lists are the classes it pays — `len(classes) × HOURS_PER_CLASS × rate == estimate.base` — and the
past days of the month are in it. The listing (`get_professor_schedule`) hides them by default,
and that is exactly the read an e-mail about a month must not use.

The doors are `estimate_professor_pay`'s (the two now share `_named_pay_rows`/`_own_pay_rows`, the
same three calls in the same order): an empty `professor` or the caller's own name is the caller,
another name is answered for an oversight role and refused to everyone else. It raises only
for a caller with no identity (the rule of every door); otherwise an access refusal or a sheet that failed becomes `schedule_error`, an undeclared rate `pay_error`,
each in the vertical's own sentence — because a failed read must stop the e-mail by NAMING what
is missing, never send one with part of the classes. Read-only.
`tests/unit/test_email_fields.py`.

**Which markers this read answers for (E3).** The five markers filled from this context —
`[disciplinas]`, `[aulas]`, `[valor_por_aula]`, `[valores_por_bonus]`, `[total]` — are the
coordinator's own: `cogno_praxis.email_fields.FIELD_PROVIDERS["COORDINATOR"]` declares them.
They are valid in the COORDINATOR's template only (2026-10-22, the owner's rule: the default
markers are the eight that serve every persona, a persona's own are added to its template): a
template of another persona that cites one is refused at the save, naming the coordination
(«[aulas] é uma tag da coordenação (COORDINATOR): …»), and only the coordinator can FILL them
(`fields_for`). They also stay reserved as company-tag names in every persona. (From 2026-10-21
until 2026-10-22 any persona's template could use them, and the send asked instead of sending.)
The declaration reads nothing; a host calls `email_context` only when
`provider_fields(template_fields(…))` names `coordinator`, so a template of generic markers
(`[nome]`, `[empresa]`, `[data]`, …) is composed without this read, in any persona.
`tests/unit/test_email_field_providers.py`.

**The same five, as tables (2026-10-22).** An e-mail whose body uses one of them also has an HTML
form, `render_email_html` (README «Templated e-mail fields»):
- `[aulas]` is one table per class group, under its «Turma X» title, in code order. The columns
  are Mês · Dia · Data · Horário (when the group has one) · Disciplina, and each discipline has
  one colour across the e-mail;
- `[valores_por_bonus]` is a two-column table (the determined band carries its mark);
- `[disciplinas]` is a list;
- `[total]` and `[valor_por_aula]` are bold.

Nothing here draws «the classes». The coordinator PRODUCES a list of records (`_aulas_records`:
`mês`, `dia`, `data`, `horário`, `disciplina`, `turma`), and the GENERIC renderer
(`records_html`/`records_text`, README) draws it like any other list. That generic renderer is
what a new persona's tags will use. It reads the classes and the estimate of this SAME context,
through the same builders as the text (`_aulas_records`, `_subjects`, `_bonus_rows`). A table is drawn only when its rows rebuild
the very text the e-mail carries, so the table and the text cannot disagree. The TEXT of `[aulas]`
follows the same shape: a «Turma X» block per class group, each line with the weekday. That is the
one change to the text, and it is declared. `tests/unit/test_email_html.py`.

## A rehearsal tenant's classes, from a FILE (2026-10-21)

Without a Google token the coordinator's subprocess serves an EMPTY in-memory store, so a
rehearsal tenant — which has no Google grant — had no classes and nothing on this path could be
rehearsed. `COGNO_COORDINATOR_SEED_FILE` names a JSON file with the grids of the tenant's
spreadsheets (`coordinator/seed.py`; the shape is in `docs/HOST_INTEGRATION.md`). The file carries
the tenant it belongs to, and **that is the guard**: the subprocess inherits the box's
environment, so the file is applied only when `COGNO_COORDINATOR_TENANT` — the tenant the host
names for the turn — is EXACTLY the file's. Never over a Google token, only the spreadsheet ids
the tenant's rules name, and a file that cannot be read whole seeds nothing (a WARNING with the
kind of the problem, never the path or the content). The seed is not durable: a write over a
seeded sheet lives as long as the subprocess. Until a host passes `COGNO_COORDINATOR_TENANT` the
seed is never applied.
