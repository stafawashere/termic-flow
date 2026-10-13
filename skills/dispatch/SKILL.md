---
name: dispatch
description: Spawn one work task in its own Termic worktree with a routed model, evidence packet and group.
argument-hint: <kind> <subject> "<goal>" [--ui] [--risk high]
---

Load the `drive` skill and follow its start of run with workflow `dispatch` and the subject as slug.

1. Ask `scout` whether a task with this name exists or a live task writes the same area. If either is true, log it and stop with one line.
2. Ask `packer` for a packet with the goal from $ARGUMENTS. Add flag `ui` when the change touches UI, `cross-component` when it spans layers.
3. `tf group "<batch name>" <kind>` if your task's group is not already this batch. An existing group keeps its colour; only a new group gets the kind colour.
4. `tf new <kind> <subject> --packet <pad> [--flag ui] [--risk high]`. Log the model and rule it printed.
5. `tf run stage dispatched`. Reply with one line: task name, model, pad id.

The worker reports back by `send`. When its line arrives, run the `review` workflow on it.
