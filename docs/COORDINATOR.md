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
