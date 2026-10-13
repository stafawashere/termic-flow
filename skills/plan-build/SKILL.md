---
name: plan-build
description: Turn an idea into an approved, sliced spec and build it across parallel Termic tasks with review and landing.
argument-hint: "<idea>"
---

Load `drive` and start a run with workflow `plan-build`.

1. Ask `packer` for a packet with the idea. `tf tab plan spec --packet <pad> --subject <kebab-subject>`.
2. When the spec pad is reported, set `phase=awaiting-approval` and reply with: spec pad id, slice count, each open decision as one question. Stop until the user approves.
3. After approval, record the slices in the run header (`tf run stage building`). Dispatch every slice whose dependencies are landed. Run two slices at once only when their write areas are disjoint.
4. As each worker reports, run `review`. As each review passes, run `land`, which asks the manual-test question per task.
5. When every slice has landed, `tf run stage done` and reply with one line per slice: task, outcome.
