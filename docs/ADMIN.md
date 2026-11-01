# The admin vertical (`cogno_praxis.admin`) — what NEO reads

NEO is an administrator persona. It talks only to the platform administrator, analyses the
business verticals of this package, and proposes improvements to their skills: the prompt slots,
the texts of their tools, and the tools themselves. This vertical is the part of NEO that belongs
here:

- the two READ-ONLY tools NEO reads the verticals with (`server.py`, over `service.py`);
- NEO's persona (`prompts/`);
- two pure rule modules: the size of a proposed change (`impact.py`: does it correct or add,
  what does it touch, how big is it) and its three-layer summary (`summary.py`).

Requesting a change, running it, reviewing it and merging it are not here. Neither is the
orchestration of NEO's turns: they are the host's, whatever it decides about where they live.

## The two tools

Both are annotated `readOnlyHint=True` and neither declares `destructiveHint`. The EGO's read-only
mask never hides them and no confirmation gate holds them (`docs/HOST_INTEGRATION.md` §5).
Neither writes, opens a connection, reads a database or reads the environment.
`tests/unit/test_admin_server.py` checks this on the registered annotations, on the vertical's
reading of itself, and on its source (no I/O import, no sibling vertical, no write call).

| tool | answers (JSON) |
|---|---|
| `list_verticals()` | every vertical of the package: `id`; `is_self` (true only for `admin`); `has_server`; `has_entry_point` (a `python -m` entry); `has_prompts` and `prompt_slots`; and every tool with its `annotations`, plus `read_only` (`readOnlyHint=true`) and `destructive` (`destructiveHint=true`, what the host holds for confirmation) |
| `get_vertical_config(vertical)` | ONE vertical: the full text of each prompt slot as written in the package, with the host's placeholders left literal, and its tool surface: each tool's `name`, `description`, `input_schema` and `annotations` |

An id that is not a vertical, such as a typo, a path or a directory that is not a vertical, is
refused in words: `ERROR: Unknown vertical 'x'. Known verticals: admin, bookkeeper, …`. The id must
match exactly, so nothing outside the package can be named.

### What counts as a vertical

A vertical is a sub-package of `cogno_praxis` (a directory with `__init__.py`) that ships a
`server.py`, or a `prompts/` directory with at least one `.txt`. The list is read from the disk on
every call and is never hand-written. Today that is `admin`, `bookkeeper`, `closer`, `companies`,
`coordinator`, `interviewer` and `scheduler`. `closer` and `interviewer` ship prompts and no
server, and `companies` ships only a `scope.txt`. `admin` lists itself, flagged `is_self`.

### Why the tool surface is read from the source, not from a built server

Building a vertical's FastMCP object means importing its `server.py`, and the import is where the
side effects are:
- `bookkeeper/server.py` and `coordinator/server.py` build a module-level `mcp` on import;
- the bookkeeper's reads `COGNO_BOOKKEEPER_DSN` / `COGNO_PG_DSN` and opens Postgres when one is
  set.

The scheduler has no module-level `mcp` for that reason: building it on import opened two
connections per subprocess. A reader that imported the servers inside a host process would
connect to whatever that host's environment points at.

So every vertical, `admin` included, is read with `ast`, and nothing is imported:
- a tool is a function decorated `@<x>.tool(...)` (or `@<x>.tool`), in source order;
- its name is `name=` when given, else the function's name;
- its description is `description=` when given, else the docstring, cleaned. A `description=`
  may be string literals, `+`, or names bound to them, followed into other `cogno_praxis` modules
  through `from … import`. One that cannot be resolved this way (an f-string, a call) is `null`,
  with `description_resolved: false`. It is never guessed;
- its annotations are the literal keywords of `ToolAnnotations(...)`;
- its input schema is what the signature says: the parameter names, the required ones (no
  default), the literal defaults, the annotation as written, and the JSON `type` of the four
  scalar annotations (`str`, `int`, `float`, `bool`).

**The reading is compared with the real registration.** `tests/unit/test_admin_service.py` builds
every vertical whose server can be built in-process (all five today) and compares its
`list_tools()` with the static reading. It checks the names in order, the annotations, the
descriptions, the parameter names, the required set, the defaults and the scalar types. A reader
that missed a decorator or a keyword fails there. FastMCP's own schema is richer for composite
annotations (`Optional[...]`, lists), and the static one does not claim to be.

A `server.py` that does not parse is reported with a `read_error`, never as a vertical with no
tools.

**"Nothing is imported" is tested where it could fail.**
- A planted server that imports cleanly writes a file when it is executed, and a control shows
  that it does. The reader leaves no file.
- A fresh subprocess reads every real vertical, then reports the `cogno_praxis` modules in its
  `sys.modules`: no sibling vertical, and no `server` but the admin one. A control makes the same
  probe import the scheduler's server and sees it.
- `test_admin_server.py` also reads the vertical's own source and fails on anything that does
  more than read: a write, `Path.open`, a thread, process, event loop or executor, an async
  subprocess, `exec`/`__import__`/`importlib`, the environment, a call on import, or an import
  of a sibling. It has one planted case per item and a control that only reads.

## NEO's persona (`prompts/`)

Four slots, in English like the other capability verticals' prompts (`scheduler`, `bookkeeper`,
`coordinator`, `companies`). They carry no placeholder: NEO is not a tenant's persona, and none of
the tenant or identity placeholders the host fills (`docs/HOST_INTEGRATION.md` §3) applies.

- **Scope:** reading the verticals, analysing their skills, proposing improvements to them and
  discussing those proposals, with the platform administrator only. Out of scope: changing the
  system itself, changing the admin vertical, running or merging a change.
- **Limits:**
  - NEO never changes the system itself, only proposes changes to the verticals' skills;
  - it never proposes a change to its own vertical (`admin`);
  - a large change waits for the administrator's decision;
  - it never invents a tool result, a figure, a test outcome or a reviewer's opinion.

## The size of a change (`impact.py`)

`classify(change) -> Classification(size, reasons)`. It is pure, over a typed `Change`:
- its `kind`, declared by whoever describes the change: `correction`, `improvement` or
  `evolution` (`KINDS`, closed);
- its `PathChange`s: a repo-relative path, the lines added and removed, and whether the change
  creates the path;
- four flags (`new_vertical`, `new_persona`, `new_tool`, `schema_change`) for what a path list
  cannot show.

Three questions decide the size:
1. **Does it correct or add?** Only a **correction** can be small. An improvement or an evolution
   is large whatever its diff (the owner's rule: «sobre as evoluções e melhoria, não entra
   também»). A `kind` that is missing, blank or not one of the three is large too.
2. **What does it touch?** A correction is still large when it touches one of the closed paths
   below or adds a capability.
3. **How big is it?** A correction is still large over 200 lines.

The rules are CLOSED, by the owner's decision. A change is **large** when any of these holds:

| code | rule |
|---|---|
| `kind_not_declared` | `kind` is missing, blank or not one of `KINDS` (the reason reads `kind not declared`) |
| `not_a_correction` | `kind` is `improvement` or `evolution` |
| `new_capability` | a new vertical, persona or tool, by flag or because the change creates a vertical's `__init__.py` / `server.py` or a `prompts/*.txt` |
| `scope_or_limits` | a change to a `scope.txt` or a `limits.txt` |
| `store_or_schema` | a `store.py`, anything under `stores/`, a migration, or the `schema_change` flag (`_ensure_schema` lives inside the store adapters) |
| `dependency` | `pyproject.toml` |
| `diff_size` | more than 200 lines added + removed over all paths: 200 is small, 201 is large |
| `admin_code` | any path under `cogno_praxis/admin/`, in any case, or a module beside it (`cogno_praxis/admin.py`, `Admin/`): NEO's own code |
| `doubt` | an unknown path type (`KNOWN_PATH_KINDS`), a path that does not read as a repo-relative POSIX path, a missing or unreadable line count, or no path at all |

Every path rule matches case-insensitively (`Scope.txt`, `Store.py`, `PyProject.toml`). A rule that
only raises the size reads a name the way the most permissive filesystem would.

Otherwise, and only for a declared correction, it is **small**, with no reasons. Every reason starts with one of the codes in `RULES`.

`escalate(classification, *, by="reviewer", reason)` records who raised it and why, and always
answers **large**. It takes no size, so there is no way to ask it for small. A large
classification stays large and keeps its reasons. A blank reason is refused.
`Classification` is frozen, so it cannot be lowered in place either.

## The summary (`summary.py`)

`render(ChangeReport) -> Summary`, with `Summary.text()` for the three blocks. It is
deterministic and calls no model. The labels are pt-BR, like every text this package writes for a
person.

- **Diretor**, 2 to 3 lines: what changes, its size, the gain; the third line, only for a large
  change, says it needs the administrator's decision.
- **Gerencial**, 5 lines: the size with its rules in words, impact, risk, the reviewer's opinion,
  how to revert.
- **Técnico**, at most 12 lines: the files with their counts (at most `MAX_FILES_LISTED`, then
  `… e mais N arquivo(s)`), the diff summary, the tests, the PR. The PR line is never the one that
  falls off.

Every line is one line (whitespace collapsed) of at most `MAX_LINE_CHARS` characters, cut with
`…`. A field nobody filled reads `não informado`, and a missing count reads `?`, never `0`.

## Wiring it into a host is the host's job

This package does not register the admin vertical anywhere: no host, no persona binding, no RBAC.
Like every other vertical, it is a server a host may run
(`python -m cogno_praxis.admin.server`, or `build_server(AdminService())`) and connect through
cogno-mcp. Which identity may reach it (the platform administrator, and nobody else), which
persona it is bound to, and where NEO's later steps live are the host's decisions
(`docs/HOST_INTEGRATION.md` §7).
