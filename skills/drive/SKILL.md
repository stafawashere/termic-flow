---
name: drive
description: Core rules for orchestrating Claude agents through the Termic CLI with the tf driver, so every step shows up in the Termic app as tasks, tabs, groups, props and scratchpads. Use when running, checking, landing or cleaning up work in Termic, or when another termic-flow skill says to.
---

# Driving Termic with tf

`tf` is on your PATH while this plugin is enabled. It wraps `$TERMIC_CLI`: it validates names, routes models, signs prompts, revalidates state before every mutation and gates destructive verbs. Read the CLI directly only for reads (`list`, `status`, `diff`, `result`, `scratchpad read`).

## Start of every run

1. `tf check`. If it fails, the control plane is off: say so in one line and stop.
2. `tf run start <workflow> <slug>`. That opens the run pad and sets `run` and `phase` props on your tab. Every decision, spawn and result after this gets `tf log "<line>"`.
3. Ask the `scout` subagent for state instead of reading `list` output yourself.

## Rules

- The user reads the app, not the chat. Status goes in the run pad and props. Chat replies are one line per stage, plus the pad id.
- Reading happens in hub tabs (`plan design triage`, on the main checkout). Writing happens only in work tasks `<kind>: <subject>` created by `tf new`, each in its own worktree.
- Workers get a packet pad id (from the `packer` subagent), never pasted context. They answer `done <task> report=<pad>`; read it with `tf report <pad> --task <task>`, because pads live in the task that wrote them.
- Mutations go through `tf do <verb> <task> ...`. It re-reads the task right before acting and exits 20 when the task vanished or changed: re-snapshot and decide again, never retry blindly.
- `archive` and `tab close` need `! tf approve <task-id>` from the user, per task. `apply` needs `! tf tested <task-id> "<what they exercised>"`. You cannot run either; ask the user, one line per task.
- Exit 21 from `tf do`, or a refusal by the harness or classifier of any Bash call, means stop that step. Do not retry it more than once and do not route around it. If the Bash call itself was refused, record it with `tf fallback add -- <cli args>`; if that is refused too, append the command to the file `tf fallback path` printed at run start. Carry on with independent steps and tell the user `! bash <fallback path>` at the end.
- Never `quit`, never edit Termic data files, never touch a task in another project unless the user names it.

References, open only when needed: [conventions](references/conventions.md), [worker contract](references/worker-contract.md), [refusals](references/refusals.md), [routing](references/routing.md).
