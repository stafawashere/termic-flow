# Conventions

Defaults come from `profiles/default.json`; a project overrides them in `.termic-flow.json` at its root (`{"extends": "termic-plus"}` pulls in a bundled or user profile).

- Hubs: `main` (orchestrator tab `orchestrate`), `plan`, `design`, `triage`. Long-lived, main checkout, read only.
- Work tasks: `<kind>: <subject>`, kebab-case subject, one worktree, one change, archived once landed.
- Kinds and group colours: feat teal, fix red, redesign purple, perf orange, docs blue, chore yellow, review green, audit green (read only, routed like review), ops pink. Termic's colours are red orange yellow green teal blue purple pink (`termic-cli help group`); there is no gray.
- Tab titles are roles: orchestrate plan spec impl review test e2e repro audit apply, optionally suffixed (`review-opus`). Retitle an open tab with `"$TERMIC_CLI" tab <task> --tab <id> --title <role>`.
- Props on each tab: `phase`, `blocked` (cleared with `""`), `issue`, `run` (run pad id).
- Group per batch, named like a PR title: `tf group "<name>" <kind>`. Tasks you `tf new` join your task's group.
- Notes, plans and reports live in scratchpads, never as `.md` files in the repo.

## Run habits

- `tf` wraps `$TERMIC_CLI`. It validates names, routes models, signs prompts, revalidates state before every mutation and gates destructive verbs. Call the CLI directly only for reads (`list`, `status`, `diff`, `result`, `scratchpad read`).
- `tf run start <workflow> <slug>` opens the run pad, sets `run` and `phase` props on your tab, and renames a default-named task (such as `claude-1`) to `ops: <workflow> <slug>`.
- Ask the `scout` subagent for state instead of reading `list` output yourself.
- The user reads the app, not the chat. Status goes in the run pad and props. Chat replies are one line per stage, plus the pad id.
- Reading happens in hub tabs. Writing happens only in work tasks created by `tf new`, each in its own worktree.
- Workers get a packet pad id from the `packer` subagent, never pasted context. They answer `done <task> report=<pad>`. Read it with `tf report <pad> --task <task>`, because pads live in the task that wrote them.
- Never edit Termic data files, and never touch a task in another project unless the user names it.
