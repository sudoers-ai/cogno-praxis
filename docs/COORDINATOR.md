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
