---
name: setup
description: Set up or repair a project's Termic agent environment for termic-flow. Writes the project profile, creates hub tasks and restructures the sidebar with approval.
argument-hint: [--share] [--skip-restructure]
---

Load `drive` and start a run with workflow `setup` and the repo folder name as slug. Each stage below is one `tf run stage <name>`.

1. **detect.** Run `tf init` (preview only). If `.termic-flow.json` already exists, it says so: switch to the `update` workflow, then come back for steps 3 to 6.
2. **profile.** Show the user the proposed profile in the run pad as a short table (checks, read_first, build isolation, locks, forbidden paths). Ask one question per value you are unsure of, such as a check command that looks wrong. Then run `tf init --write`. By default the file is added to `.git/info/exclude`, so it never reaches the repo; `--share` from $ARGUMENTS skips that for teams that commit it. If the project's CLAUDE.md conflicts with a detected value, the CLAUDE.md wins: fix the profile, not the rules.
3. **hubs.** Run `tf hubs`. Missing hubs are created on the main checkout with `tf hubs --create`. Creating a hub is not destructive, so it needs no approval.
4. **scaffold.** Skip this if the profile has no `scaffold.categories`. Otherwise run `tf setup --preview`, show the rows in the run pad and ask the user to confirm, then `tf setup --apply`. Apply only creates. Rows marked approve are never run by apply. Format and rules: [restructure](references/restructure.md#scaffold).
5. **restructure.** Skip this if $ARGUMENTS has `--skip-restructure` or the project has no tasks besides the hubs. Otherwise follow [restructure](references/restructure.md): audit, plan, approval, apply, verify. Renames, regroups, colour changes, tab closes and archives happen only here.
6. **verify.** Run `tf check` and `tf audit`, and write both into the run pad. `tf run stage done`. Reply with one line: the profile path, the hubs created, the audit counts before and after, and the pad id.

Setup never touches the hubs or the orchestrator's own task. Never edit the project's CLAUDE.md, `.claude/` or docs during setup. Report anything there that conflicts, and let the user decide.
