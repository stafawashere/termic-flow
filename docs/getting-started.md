# Getting started on an existing project

This walks through adding termic-flow to a project you already work on in Termic. Setup writes one file, `.termic-flow.json`, and keeps it out of git. Your code is not touched.

## 1. Install the plugin

```sh
git clone https://github.com/stafawashere/termic-flow ~/dev/termic-flow
claude plugin marketplace add ~/dev/termic-flow
claude plugin install termic-flow@termic-flow
```

Turn on the CLI in Termic's Settings. Inside a Termic task, `$TERMIC_CLI` should now be set. You can check from any task with:

```sh
echo "$TERMIC_CLI"
```

## 2. Open Claude in the main checkout

Open your project in Termic and start Claude in a task on the main checkout. This tab becomes the orchestrator. It reads and plans, and it never writes code itself. Code changes happen in separate work tasks, each in its own worktree.

## 3. Run setup

```text
/termic-flow:setup
```

Setup runs in stages and writes everything it does into a scratchpad called the run pad, which opens as a tab next to the chat.

1. **detect.** `tf init` looks at the repo and proposes a profile: the test and build commands it found, the docs agents should read first (`CLAUDE.md` by default), and whether builds need their own output folder per worktree.
2. **profile.** You see the proposal as a table and answer any question it has, such as a check command that looks wrong. It then writes `.termic-flow.json` at the project root and adds it to `.git/info/exclude`, so it stays out of git. Pass `--share` if your team wants to commit it.
3. **hubs.** It creates the hub tasks that are missing: `main`, `plan`, `design` and `triage`. Hubs live on the main checkout and are only used for reading.
4. **scaffold.** Only when your profile has a `scaffold` block. See [how-to](how-to.md#lay-out-the-sidebar-ahead-of-time).
5. **restructure.** If the project already has tasks, `tf audit` counts what does not fit the conventions (task names, groups, tab titles, code written in a hub). You get a numbered plan and approve it before anything is renamed, regrouped or closed. Pass `--skip-restructure` to leave existing tasks alone.
6. **verify.** `tf check` and `tf audit` run again and the before and after counts go into the run pad.

If the project already has a `.termic-flow.json`, setup switches to `/termic-flow:update` for the profile and then carries on from the hubs step. Running either one twice is safe.

## 4. Check the profile

Open `.termic-flow.json` and look at `checks`. Every worker runs these before it reports, so they should be commands that pass on a clean checkout today.

```json
{
   "checks": [
      { "name": "unit", "run": "timeout 600 npm test" },
      { "name": "e2e", "run": "timeout 1800 make e2e", "when": "ui", "lock": "e2e" }
   ],
   "read_first": ["CLAUDE.md", "docs/architecture.md"]
}
```

A check with `"when": "ui"` only runs for changes flagged as UI work. A check with a `lock` only runs in one worktree at a time, which matters for anything that binds a port or drives a browser.

## 5. Send your first task

```text
/termic-flow:dispatch fix login-redirect "After login the app sends you to / instead of the page you came from"
```

A new task called `fix: login-redirect` appears in the sidebar with its own worktree and an `impl` tab. The worker reads a short packet, makes the change, runs your checks and writes a report pad. When it finishes, the orchestrator opens a `review` tab on the same task.

Once the review passes, land it:

```text
/termic-flow:land fix: login-redirect
```

It asks whether you tested the change yourself. Answer from your own prompt with:

```sh
! tf tested <task-id> "logged in from /settings, landed back on /settings"
```

The change is applied to your main checkout. To clean up, approve the archive:

```sh
! tf approve <task-id>
```

[workflows.md](workflows.md) covers each command in detail and [scenarios.md](scenarios.md) shows how they fit together on real kinds of work.

## What stays yours

The plugin's hook stops the agent from running `tf approve`, `tf tested` and `tf accept`, and from calling Termic's `archive`, `apply`, `tab close` or `quit` directly. Those decisions are made by you, per task, with the `!` prefix in Claude's prompt. If you want less friction on a project you trust, see [how-to](how-to.md#let-the-agent-approve-on-a-trusted-project).
