# Workflows

Each slash command is a workflow. Every one of them starts the same way: `tf check` confirms the Termic CLI is reachable, then `tf run start` opens a run pad and sets the `run` and `phase` props on the orchestrator's tab. Decisions and results are logged there, so the sidebar and the pad tell you where things are without reading the chat.

## The pieces

| Piece | What it is |
|---|---|
| Hub | A long-lived task on the main checkout: `main`, `plan`, `design`, `triage`. Read only. |
| Work task | `<kind>: <subject>`, for example `feat: csv-export`. One worktree, one change, archived after it lands. |
| Kind | feat, fix, redesign, perf, docs, chore, review, ops. Each has a group colour. |
| Tab role | The tab title says what the tab does: orchestrate, plan, spec, impl, review, test, e2e, repro, audit, apply. |
| Packet | A scratchpad with the goal, acceptance criteria, files to read and constraints. Workers get its id instead of a long pasted prompt. |
| Report | The pad a worker writes when it is done: status, checks, changed, risks, next, failure. |
| Props | `phase` and `blocked` on each tab, so the sidebar shows progress. |

## dispatch

```text
/termic-flow:dispatch <kind> <subject> "<goal>" [--ui] [--risk high]
```

Starts one piece of work. It checks that no task with that name exists and that no live task is already writing the same area. The `packer` subagent writes the packet, `tf new` creates the task in a new worktree with a routed model, and the task joins the current batch group. Use `--ui` when the change touches the interface so UI-only checks run, and `--risk high` when a mistake would be expensive.

## review

```text
/termic-flow:review <task>
```

Runs automatically when a worker reports, and you can also run it by hand. The reviewer gets a new tab on the task, never the implementer's tab. Risk is high when the diff touches security, sandboxing, process or terminal handling, stored data or hot paths, and high-risk reviews run on Opus. A pass sets the task to `ready`. Anything else sets `blocked` with the first finding.

## land

```text
/termic-flow:land <task>
```

Needs a passing report and a passing review. It then asks whether you tested the change by hand and waits for `! tf tested`. How it lands depends on `land.mode` in your profile:

- `apply` applies the task's changes to the main checkout. If that conflicts it stops and tells you.
- `patch` applies only the task's diff with a three-way merge and leaves other uncommitted work in the main checkout alone. Land falls back to this when `apply` is refused because the main checkout is dirty.
- `pr` pushes the branch and opens a pull request with `tf pr`. Add `--forge gitlab` for GitLab.

Cleanup comes last and waits for `! tf approve <task-id>`.

## triage

```text
/termic-flow:triage "<symptom>"
```

For bugs where the cause is not obvious. A `repro` tab opens in the `triage` hub, which cannot write code. It has to reproduce the problem and prove the root cause. A proven cause becomes the packet for a `fix` dispatch. If it cannot reproduce the problem it stops and says so.

## plan-build

```text
/termic-flow:plan-build "<idea>"
```

For anything bigger than one task. A `spec` tab in the `plan` hub writes a spec split into slices, each with its own write area and acceptance commands. The run stops at `awaiting-approval` and lists open decisions as questions. After you approve, slices are dispatched as their dependencies land, and two run at once only when they write to different areas. Each slice goes through review and land, including the manual-test question.

## setup and update

`/termic-flow:setup` prepares a project, see [getting-started.md](getting-started.md). `/termic-flow:update` brings a project up to the installed plugin version: `tf migrate` previews profile changes, one yes applies them, then hubs and the sidebar are checked again. Update the plugin itself first with `claude plugin update termic-flow@termic-flow`.

## status

```text
/termic-flow:status
```

One line: tasks by phase and anything blocked, with the details in the run pad.

## Model routing

Each role is routed to a model by rules in `config/routing.default.json`:

| Role | Model |
|---|---|
| scout, packer, audit, status | Haiku |
| orchestrator, impl, review | Sonnet |
| plan, spec, repro, high-risk review | Opus |
| impl for redesign or perf, or flagged ambiguous or cross-component | Opus |

A worker that fails with `failure: reasoning` is retried once on the same model and then moved up one step. An environment failure is never escalated, because a bigger model will not fix a missing dependency. `tf route impl --kind perf` shows the choice and the rule behind it, and `tf route --explain` prints the merged table.
