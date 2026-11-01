# The NEO scope lock

NEO is an admin persona. When the owner approves a change to a vertical's skills, a code agent
edits a worktree of this repository and opens a pull request from a branch named
**`neo/<request_id>`**. The rule is that NEO only improves the verticals' skills: it never changes
the system, and it never changes itself. A pull request of NEO's that breaks the rule is refused
by CI, path by path, before anyone reads it.

- **The rule:** [`scripts/neo_scope_check.py`](../scripts/neo_scope_check.py).
- **Where it runs:** [`.github/workflows/neo-scope.yml`](../.github/workflows/neo-scope.yml), on
  pull requests whose head branch starts with `neo/`, and on no other.
- **Its tests:** [`tests/unit/test_neo_scope_check.py`](../tests/unit/test_neo_scope_check.py).

## What a NEO pull request may change

A path under `cogno_praxis/`, except the admin package, of a type the package is made of.

| | Refused, with the rule the checker prints |
|---|---|
| anything outside `cogno_praxis/`: `pyproject.toml`, lock files, `.github/**`, `scripts/**` (the checker), `docs/**`, `tests/**` (see *Tests* below), `examples/**`, the README and the changelog | `outside_scope` (`hidden` for a dotted path such as `.github/`) |
| `cogno_praxis/admin/**`, or a module `cogno_praxis/admin.*`, **in any case** (`Admin/`, `ADMIN/`): on a case-insensitive filesystem they are the same package | `admin` |
| a rename or a copy with either side out of scope, in either direction. Both sides are checked: checking only the destination would let a pull request move a test, or the checker, into the package and so delete it from where it ran | the side's own rule, plus `rename_across` |
| a symlink, an executable, a submodule, or any mode change (`chmod -x` included) | `mode`, `mode_change` |
| a `.` or `..` component, an empty component, an absolute path | `traversal`, `absolute` |
| a character outside `[A-Za-z0-9._/-]`: a backslash, a space, a control character, a non-ASCII letter (a homoglyph such as a dotless `ı`) | `path_chars` |
| a dotfile inside the package. A `.gitattributes` with `-diff` would show the reviewer "Binary files differ" in place of the change | `hidden` |
| a file type the package does not hold today: only `.py`, `.txt` and `py.typed`. An extension module (`.so`) is imported BEFORE the `.py` of the same name | `file_type` |
| a head that is not LINEAR on ONE merge base: a merge commit anywhere in `<base>..<head>`, or a merge-base count other than one (a criss-cross history, or unrelated histories). See below | `merge_commit`, `merge_bases` |
| an empty diff | `empty_diff` |
| an unknown or unmerged status | `status` |

Exit codes: **0** in scope, **1** refused (one `REFUSED <path>: <rule> — <reason>` line per
offence, every one of them and not only the first), **2** the diff could not be read. Only 0
passes.

**The empty diff is refused.** A NEO pull request that changes nothing has nothing to approve, and
"no records" is also what a checker reading the wrong range would see. It fails closed.

**It reads `git diff --raw -z -M`, not `--name-status`.** `--name-status` prints a `chmod +x` as a
plain `M` and a new symlink as a plain `A`: neither can be seen there. `--raw` carries both modes
of every record, and `-z` keeps every path byte for byte.

## A NEO head is linear

The checker judges the three-dot diff, which git takes from ONE merge base. GitHub merges a pull
request over a VIRTUAL base built from ALL of them. On a criss-cross history the two disagree, and
the diff can show an in-scope prompt edit while landing the pull request REVERTS a file the diff
never showed.

Measured on a throwaway repository:
- main merged A, which hardened a file outside the scope, and B, an unrelated in-scope change;
- the head was `B + merge -s ours A + a prompt edit`;
- the diff read "ok, 1 record", and merging the head put the old file back.

So before reading a path the checker refuses, in `<base> <head>` mode:
- **`merge_bases`**: `git merge-base --all <base> <head>` does not print exactly one commit. Zero
  (unrelated histories) is refused with this rule instead of failing inside `git diff`.
- **`merge_commit`**: `git rev-list --merges <base>..<head>` is not empty.

With two or more bases the second check always fires as well, because whatever joins the bases is a
merge the base cannot reach. The first is the second wall, and the one that names unrelated
histories.

`--stdin` reads a diff and knows no history. It is for tests, and the workflow never calls it.

## Why `pull_request_target`

On `pull_request`, GitHub runs the workflow and the checkout of the pull request's own merge
commit. A pull request that edits the workflow or the checker would then be judged by its own
edited copy. On `pull_request_target` the workflow comes from the base branch, and the job checks
out the base SHA, so the checker that runs is the base's. The pull request's head is fetched as git
objects to diff against and nothing from it is executed, installed or imported, which is what makes
`pull_request_target` safe here. The token is read-only. The SHAs reach the shell through `env`,
never interpolated into a `run:` block. Both actions are pinned by commit SHA, not by tag (a tag can be moved).

## Tests: NEO never edits one; it may create new ones only behind a switch (`NEO_MAY_ADD_TESTS`)

**The owner's rule: NEO may not edit tests, but may create new ones.** It is written as one
constant in the checker, `NEO_MAY_ADD_TESTS`, and the two settings mean:

- **`False`, the default: strict.** Every path under `tests/` is refused (`outside_scope`), new
  files included. This is the rule today.
- **`True`: new test files, and nothing else.** The one test change allowed is ADDING A NEW
  FILE that meets all of these:
  - its status is `A`: the path did not exist at the merge base;
  - it is a regular, non-executable file;
  - it sits directly in `tests/unit/`;
  - it is named `test_<lowercase letters, digits, _>.py`.

  Every other test change is refused with `test_add`:
  - a modification, a deletion, a rename or a copy (from or to a test path), or a mode change;
  - a symlink;
  - a `conftest.py` or a helper (`_helpers.py`);
  - a subdirectory, or an integration test;
  - the tests of this lock or the guard that every test file runs in CI (`PROTECTED_TESTS`).

  The name is lowercase so that an "added" `test_Neo_Scope_Check.py` cannot be, on a
  case-insensitive filesystem, an edit of an existing file.

No command-line flag opens the switch. The constant lives in the BASE's copy of the checker, which a
NEO pull request cannot change, and flipping it is a person's pull request.

**Why tests matter here.** Many tests pin prompt text. Measured with the admin vertical in (25 prompt
files, six of them executor prompts): appending one neutral sentence to the six executor prompts
(`*/prompts/system.txt`) fails 22 unit tests; appending it to all 25 prompt files fails 95. (On
`232e72d`, with 21 files, the same probe fails 21 and 90.) So a prompt improvement will often need a
pinned test updated. That edit is always a person's, under either setting.

**What the switch cannot promise.** A new test cannot touch an old one by path. But it runs in the
same pytest process, so code at the top of the new module could still patch what other tests read.
A reviewer reads every new test.

## What this lock does not do

- **It does not make the check required.** That is a branch-protection setting of the repository.
  A skipped job reports success to a required check, so making it required does not block other
  pull requests.
- **It does not decide which branch a pull request comes from.** Its guarantee holds for pull
  requests named `neo/…`. That NEO's account can only push such branches is a repository setting
  too. GitHub's `startsWith` ignores case, so a `NEO/…` branch is checked as well.
- **It allows the package's root modules too** (`cogno_praxis/__init__.py`, `logsafe.py`,
  `grounding.py`, `render.py`…), because the rule is "under `cogno_praxis/`". Narrowing it to the
  vertical directories is a decision for the owner, not taken here.
- **It judges paths, not content.** Inside `cogno_praxis/`, what a change says is the reviewer's to
  read.
