---
name: drive
description: Core rules for driving Claude agents in Termic with tf. Use when running, checking, landing or cleaning up Termic work, or when a termic-flow skill says to.
---

# Driving Termic with tf

Each run starts with `tf check` (if it fails, say so in one line and stop), then `tf run start <workflow> <slug>`. Log every decision with `tf log`. Ask `scout` for state. `tf patch`, `tf do apply`, `tf do archive` and `tf run end` close the run once no task spawned in it is still unlanded.

- Mutate only through `tf do <verb> <task>`. Exit 20 means re-snapshot and decide again, never retry blindly.
- `archive` and `tab close` need `! tf approve <id>` from the user, and `apply` needs `! tf tested <id> "<what>"`. Ask, one line per task.
- On exit 21 or a refused Bash call, stop that step, retry at most once and never route around it. Record it with `tf fallback add -- <args>` and end by telling the user `! bash <fallback path>`.
- Run `tf run stall-check` each time you check on work: it nudges a task silent past `stall_minutes` (default 10) once, then marks it blocked. After a break, `tf run resume <slug>` prints one line per task with its next action.
- Never `quit`.

Details in [conventions](references/conventions.md), [refusals](references/refusals.md), [routing](references/routing.md), [worker contract](references/worker-contract.md).
