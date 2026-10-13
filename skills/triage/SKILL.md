---
name: triage
description: Reproduce a reported bug and prove its root cause in a read-only triage tab, then hand it to dispatch.
argument-hint: "<symptom or issue>"
---

Load `drive` and start a run with workflow `triage`.

1. Ask `packer` for a packet holding the symptom from $ARGUMENTS, any error text, and the files likely involved.
2. `tf tab triage repro --packet <pad> --subject <kebab-subject>`.
3. `tf run stage repro`. When its line arrives, `tf report <pad> --task triage`. `pass` means the cause is proven: log it, then follow the `dispatch` workflow with kind `fix`, reusing the cause pad as the packet. `blocked` means no reproduction: tell the user in one line and stop.
