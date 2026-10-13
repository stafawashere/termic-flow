# Scenarios

Worked examples of how the workflows fit together. Task ids are shortened here, and you copy the real ones from the sidebar or the run pad.

## A small fix you already understand

You know the bug and roughly where it is.

```text
/termic-flow:dispatch fix date-parse "Dates like 2026-03-01 parse as February in the import screen" --ui
```

Wait for the review to pass, try the import screen in the worktree, then:

```text
/termic-flow:land fix: date-parse
```

```sh
! tf tested 3f2a "imported the March sample file, dates correct"
! tf approve 3f2a
```

## A bug you cannot explain yet

Start with triage, which reads and reproduces but cannot change code.

```text
/termic-flow:triage "Sync hangs after the laptop wakes from sleep, only on Wi-Fi"
```

The `repro` tab in the `triage` hub tries to reproduce it and writes a cause pad. If it proves a cause, a `fix` task is dispatched with that pad as its packet and the normal review and land steps follow. If it cannot reproduce, the run stops with what it tried, and you can add details and run it again.

## A feature with several parts

```text
/termic-flow:plan-build "CSV export for reports, with a column picker and a size limit"
```

The spec comes back with slices, for example `feat: export-endpoint`, `feat: column-picker` and `feat: export-limit`, and questions such as what the limit should be. Answer them and approve. The endpoint slice runs first, and the picker and limit slices can run side by side once it lands because they touch different files. Each one stops at the manual-test question, so you test them one at a time.

## Several independent fixes at once

Dispatch each one. They join the same batch group, so the sidebar keeps them together.

```text
/termic-flow:dispatch fix typo-settings "Typo in the settings header"
/termic-flow:dispatch fix empty-state "Empty list shows a spinner forever"
/termic-flow:dispatch chore bump-deps "Update dev dependencies, no runtime changes"
```

Use `/termic-flow:status` to see which are ready, then land them one by one.

## Landing while your main checkout has other work

You have uncommitted edits in the main checkout and a task is ready. Set `"land": { "mode": "patch" }` in `.termic-flow.json`, or just run land. When `apply` is refused because of the dirty checkout, land uses `tf patch`, which merges only that task's diff and leaves your edits alone.

## A team that reviews through pull requests

```json
{ "land": { "mode": "pr" } }
```

Land then pushes the task branch and opens a PR with a line on what you tested by hand. The task stays until you approve its cleanup.

## Two worktrees fighting over a port

Your e2e suite starts a server on a fixed port, so two workers running it at once break each other. Add a lock:

```json
{
   "locks": ["e2e"],
   "checks": [{ "name": "e2e", "run": "timeout 1800 make e2e", "when": "ui", "lock": "e2e" }]
}
```

Workers run it through `tf lock e2e`, which waits for the other worktree to finish.

## Builds that collide across worktrees

Rust, and anything else with a shared build folder, can corrupt or slow down when several worktrees build at once. Give each worktree its own output folder:

```json
{ "build": { "isolate": true, "env": { "CARGO_TARGET_DIR": "{worktree}/target" } } }
```

## A worker reported a failure

The review step stops when the report is not `pass` and logs the risks. Retries only happen when you ask for them. Tell the orchestrator to retry, and it creates the task again with the attempt count and the failure from the report:

```sh
tf new fix date-parse --packet <pad> --failed 1 --failure reasoning
```

A reasoning failure moves up one model after the first retry. An environment failure stays on the same model, so fix the environment first.

## The agent was refused

When Termic or Claude Code refuses a command, the agent stops that step, retries it at most once and writes it to a fallback script. It carries on with whatever does not depend on it and gives you the line at the end:

```sh
! bash <fallback path>
```

## Picking up an old project with messy tasks

Run `/termic-flow:setup` and let it reach the restructure stage. `tf audit` counts badly named tasks, tasks with no group, tab titles that are not roles and code written inside a hub. You get a numbered plan, and anything destructive still needs `! tf approve` per task.
