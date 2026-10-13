# Scaffold and restructure

Both run inside setup, after the profile and hubs exist. Scaffold adds missing structure. Restructure changes what already exists.

## Scaffold

The profile's `scaffold` block declares the sidebar. A category is a group (its name and colour), a section is a seed task named `<kind>: <section>` inside that group, and a sub-part is a tab title on the seed task. Hubs stay profile hubs and are never scaffolded.

```json
{
   "scaffold": {
      "categories": [
         {
            "name": "Billing",
            "color": "teal",
            "sections": [
               {"name": "invoices", "kind": "feat", "tabs": ["impl", "review"]},
               {"name": "refunds", "kind": "fix", "tabs": ["impl"]}
            ]
         }
      ]
   }
}
```

The key is `color`, one of red, orange, yellow, green, teal, blue, purple, pink. `kind` must be a key of `kinds`. Category names and section names are unique. Put the block in `.termic-flow.json` to override the default, which is empty. A bad block fails with the reason, so fix the profile and rerun.

`tf setup --preview` prints one line per row and changes nothing. `tf setup --apply` runs only the create rows:

- a new task, made with `--no-group` so it never lands in a stray group
- a group on a task apply just created
- the first profile tab as tab 1 of that seed task, then any extra tabs

Rows that regroup an existing task, recolour an existing group, or touch a hub or the calling task print as `approve` rows. Apply skips them. Move them into the restructure plan below. Rerunning preview after a partial apply shows only what is still missing.

## Restructure

1. Audit: `tf audit` (pure code, counts per flag). Write its JSON and a table into the run pad.
2. Plan: one row per action, `| # | target | action | command | destructive |`, ordered hubs, renames, groups, tab titles, props, moving code-writing work out of hubs, tab closes, archives last. A tab moves by `tab <hub> --resume <session id> --title <role>` and archiving the old task.
3. `tf run stage awaiting-approval` and stop. Reply with the pad id and row count. Destructive rows need `! tf approve <task-id>` per task; blanket approval of the plan does not cover them.
4. Apply rows in order through `tf do` (renames: `tf do rename <task> "<name>"`). Log `#n ok` or `#n FAILED <text>` per row and continue past failures that later rows do not depend on.
5. Verify: rerun `tf audit`, log before and after counts, explain every nonzero flag, `tf run stage done`.

Rename, regroup, colour change, tab close and archive happen only through this plan, never through `tf setup`. Never archive your own task or `main`.
