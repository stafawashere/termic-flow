# Changelog

## 0.4.0

### Added

- `tf run stall-check` nudges a worker that has been silent past `stall_minutes` (default 10) once, then marks the task blocked if it stays silent.
- `tf run resume <slug>` prints the next action for every task in a run, including a run that has already closed, and lists report pads the run log never mentioned.
- `tf tab <task> review --round N` opens a `review-rN` tab with the re-review template. A later round needs `--report`.
- `tf report` reads the newest `report: <task> r<N>` pad and says which round it read.
- Report checks named `red_<name>` must exit non-zero, so a deliberate break run can sit in a passing report.
- `tf audit` flags uncommitted changes on the main checkout as `dirty_main`.
- `audit` is a task kind for read-only audits.
- `tf run start` renames a default-named orchestrator task to `ops: <workflow> <slug>`.
- The guard warns a worker that runs a full test suite or a build in the foreground.

### Changed

- The `drive` skill is about 60% shorter. Its run habits moved to `conventions.md` and `refusals.md`.
- Skill and agent descriptions are shorter, which lowers the cost of every session.
- A run's file is removed only when no live task from that run remains.
- Workers write a new report pad for each round instead of overwriting the last one.
- `tf group` keeps the colour a group was created with.

### Fixed

- Review pads are written to the work task, not the orchestrator's task.
- Workers sign their messages with their own task id.
- `--help` on a guarded verb is no longer blocked. Real `tf tested`, `tf approve` and `tf accept` calls are blocked as before.
