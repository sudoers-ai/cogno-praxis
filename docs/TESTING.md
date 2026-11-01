# Testing standard

Every change to this repository, whether written by a person or by an automated agent, meets this
minimum before it is merged. The system is automated, so the tests are what make a change
trustworthy, and the documentation is what makes it understandable to the next reader, human
or agent.

## The four levels

Every pull request **declares all four levels in its description**, each as **RUN** (with the
result) or **N/A** (with the reason). A level left blank, or an N/A without a reason, means the
pull request is not ready to merge.

| Level | Required when | The minimum |
|---|---|---|
| **Unit** | always | A **twin** that fails before the change and passes after it (the defect, or the new behaviour), and a **control** showing that what must not change did not change. The guards are **mutated** on purpose and every mutation is caught (the count is reported as n/n). The repository's structural tests run alongside. |
| **Integration** | the change touches a store, a schema or migration, an HTTP route, a process or subprocess, an operations script, or the boundary between two packages | Run against the real component, made disposable: a throwaway database, a loopback server, a script in a sandbox with fake commands. Never against a live system. |
| **End-to-end** | the change alters what a user sees or does: a channel, a reply, a panel flow, a confirmation step | One flow end to end, in a rehearsal environment or as a page-level UI test. If it needs a paid model, its cost is written down before it runs. If it cannot run yet, the pull request names the missing flow and who runs it after deployment. |
| **Bench** | always for the deterministic benches a repository has; with a model when the change alters what a model reads or decides (a prompt, a grounding rule, routing) | The deterministic bench shows no new failures. A model bench states its configuration and its cost before it runs, and never uses shared production hardware. |

## The declaration block

The four levels are declared in the pull request description in this **fixed format**, so that an
automated merge can read them as fields. Exactly four lines, in this order, each `RUN — <result>`
or `N/A — <reason>`:

```
Unit: RUN — <result>
Integration: N/A — <reason>
E2E: RUN — <result>
Bench: RUN — <result>
```

Free text elsewhere in the description is welcome; these four lines are what gets checked.

## Always

- **Documentation is part of the change:** the changelog, the README index, the document that
  describes the feature, and docstrings that explain *why*. A pull request lists the documents it
  touched.
- **What is merged is what was measured:** the full suite runs once on the exact tree that is
  merged.
- **A reviewer checks the tests** before the change is approved.
