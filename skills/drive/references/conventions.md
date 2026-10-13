# Conventions

Defaults come from `profiles/default.json`; a project overrides them in `.termic-flow.json` at its root (`{"extends": "termic-plus"}` pulls in a bundled or user profile).

- Hubs: `main` (orchestrator tab `orchestrate`), `plan`, `design`, `triage`. Long-lived, main checkout, read only.
- Work tasks: `<kind>: <subject>`, kebab-case subject, one worktree, one change, archived once landed.
- Kinds and group colours: feat teal, fix red, redesign purple, perf orange, docs blue, chore yellow, review green, ops pink. Termic's colours are red orange yellow green teal blue purple pink (`termic-cli help group`); there is no gray.
- Tab titles are roles: orchestrate plan spec impl review test e2e repro audit apply, optionally suffixed (`review-opus`). Retitle an open tab with `"$TERMIC_CLI" tab <task> --tab <id> --title <role>`.
- Props on each tab: `phase`, `blocked` (cleared with `""`), `issue`, `run` (run pad id).
- Group per batch, named like a PR title: `tf group "<name>" <kind>`. Tasks you `tf new` join your task's group.
- Notes, plans and reports live in scratchpads, never as `.md` files in the repo.
