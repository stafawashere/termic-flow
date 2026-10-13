---
name: land
description: Land a reviewed Termic task after the manual-test answer, then queue its cleanup for approval.
argument-hint: <task>
---

Load `drive`. If no run is open, start one with workflow `land`.

1. Check readiness: the latest report and review both parse as `pass` with `tf report <pad> --task <task>`. If not, stop and say which.
2. Ask the user exactly: "Have you manually tested <task>? If yes, run  ! tf tested <task-id> \"<what you exercised>\"". Then stop and wait. Do not presume the answer.
3. When the marker exists, land by the profile's `land.mode`:
   - `apply`: `tf do --expect settled apply <task>`. Exit 10 means the main checkout conflicted: stop and tell the user.
   - `patch`, or `apply` refused because the main checkout has other uncommitted work: `tf patch <task>`. It applies only the task's diff with a 3-way merge, leaves everything else in the main checkout alone, and records the task as landed.
   - `pr`: push the task branch from its worktree, then `tf pr <task> -- --title "<title>" --body "<body>"` (add `--forge gitlab` for GitLab). The body carries one line on what was tested by hand.
4. Queue cleanup: log "cleanup pending" and ask for `! tf approve <task-id>`. After approval: `tf do tab close <task> --tab <role>` for finished tabs, then `tf do archive <task>`.
5. `tf run stage landed`. Reply with one line.
