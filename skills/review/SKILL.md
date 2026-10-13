---
name: review
description: Independent review of one Termic work task in a fresh tab, routed by risk.
argument-hint: <task> [--risk high]
---

Load `drive`. If no run is open, start one with workflow `review`.

1. `tf report <report pad> --task <task>` for the worker's report. If it is not `pass`, log the risks and stop: re-dispatch with `--failed N --failure <its failure field>` only if the user asked for retries.
2. Pick risk: high when the diff touches security, sandboxing, process or terminal handling, persisted data or performance-critical paths, or when the packet says so. Otherwise low.
3. `tf tab <task> review --packet <packet> --report <report pad> --risk <risk> --kind <kind>`. For a re-review after fixes, add `--round N` (N above 1) and pass the previous review report as `--report`. The tab is titled `review-rN` and re-checks only the fixed findings.
4. `tf run stage review`. When the reviewer's line arrives, `tf report <pad> --task <task>`. `pass` moves the task to `ready` (`"$TERMIC_CLI" prop phase ready --task <task> --tab impl`). Anything else sets `blocked` with the first finding.

Never review in the implementer's tab.
