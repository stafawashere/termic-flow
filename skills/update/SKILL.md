---
name: update
description: Bring a project's termic-flow environment up to the installed plugin version. Migrates the project profile, reports legacy skills to retire, and re-checks the hubs and sidebar against the current conventions.
---

Load `drive` and start a run with workflow `update`.

1. **plan.** Run `tf migrate` (dry run). It returns `current`, `pending` with a list of changes, or `no-project-file`; for `no-project-file`, run the `setup` workflow instead and stop here. Write the changes and any advisories into the run pad.
2. **approve.** If there are changes, reply with the pad id and the number of changes, and ask whether to apply them. These changes only touch `.termic-flow.json`, so one yes covers all of them.
3. **apply.** Run `tf migrate --apply`, then `tf migrate` again, which must report `current`. Log both results.
4. **environment.** Run `tf hubs`, and create any hubs it reports missing with `tf hubs --create`. Run `tf audit`. If any flag count is nonzero, offer the restructure phase from the `setup` skill, and do not run it unasked.
5. **advisories.** For each legacy item `tf migrate` reported, such as an old project-local termic-driver skill, give the user the exact one-line change and leave the file alone. Those files are the user's.
6. `tf run stage done`. Reply with one line: the from and to versions, the changes applied, the audit counts and the pad id.

To update the plugin itself first, the user runs `claude plugin update termic-flow@termic-flow`, or `git pull` in a `--plugin-dir` checkout. `update` then migrates each project.
