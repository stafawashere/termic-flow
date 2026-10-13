# How-to

Short answers to specific questions. Commands starting with `!` are typed by you in Claude's prompt. The others are run by the agent or by you in a terminal inside Termic.

## Check that everything is connected

```sh
tf check
```

It fails when the Termic CLI is off or unreachable. Turn the CLI on in Termic's Settings and run it again from inside a Termic task.

## See the state of the project

```sh
tf snapshot
tf audit
```

`snapshot` prints tasks, tabs, groups and props as JSON. `audit` counts anything that breaks the conventions. Both only read.

## Read a worker's report

```sh
tf report <pad-id> --task <task>
```

Pads belong to the task that wrote them, so the task name is needed.

## Add a check

Add it to `checks` in `.termic-flow.json`, wrapped in `timeout` so a stuck test cannot hang a worker:

```json
{ "checks": [{ "name": "lint", "run": "timeout 300 npm run lint" }] }
```

Set `"hooks": { "require_timeout": true }` to have the hook block test runs without a `timeout`.

## Make agents read your docs first

```json
{ "read_first": ["CLAUDE.md", "docs/architecture.md", "docs/gotchas.md"] }
```

## Keep agents away from files or commands

```json
{
   "forbid": {
      "commands": ["make release", "git add .claude"],
      "paths": ["CHANGELOG.md"]
   }
}
```

The hook blocks those commands and edits to those paths.

## Share settings across projects

Put common settings in `~/.config/termic-flow/profile.json`, or create a named profile and point a project at it with `"extends"`. Layers merge in this order, with later ones winning: `profiles/default.json`, your user profile, the profile named by `extends`, then the project file. `profiles/termic-plus.json` is a full example.

## Change which model does what

```sh
tf route impl --kind perf
tf route --explain
```

Add rules in `~/.config/termic-flow/routing.json` or under `"routing"` in the project file. Your rules are checked before the defaults, and project rules before user rules:

```json
{ "routing": { "rules": [{ "id": "my-review", "roles": ["review"], "model": "opus" }] } }
```

Fable is never picked unless you set `"allow_fable": true`.

## Lay out the sidebar ahead of time

Describe groups and seed tasks in the profile:

```json
{
   "scaffold": {
      "categories": [
         {
            "name": "Billing",
            "color": "teal",
            "sections": [
               { "name": "invoices", "kind": "feat", "tabs": ["impl", "review"] },
               { "name": "refunds", "kind": "fix", "tabs": ["impl"] }
            ]
         }
      ]
   }
}
```

`tf setup --preview` shows what would be created. `tf setup --apply` only creates. Rows that would change something existing are shown as `approve` and skipped, and they belong in the restructure plan instead.

## Let the agent approve on a trusted project

```json
{ "auto_approve": true }
```

With this set, the agent may run `tf tested --auto` once a task's review has passed, and `tf approve --auto` once a work task has landed. Hubs and the agent's own task are never auto-approved, and the marker records that it was automatic. `tf accept` always stays yours.

## Override a rejected report

```sh
! tf accept <task-id> "flaky e2e on CI runner, passes locally three times"
```

The reason is logged.

## Land a change you merged by hand

```sh
tf patch <task>
```

It applies only the task's diff and records the task as landed, so cleanup can go ahead.

## Run a command the agent was not allowed to run

```sh
tf fallback path
! bash <that path>
```

## See what a session cost

```sh
tf tokens <session-id> [<session-id> ...]
```

## Upgrade

```sh
claude plugin update termic-flow@termic-flow
```

Then run `/termic-flow:update` in each project.
