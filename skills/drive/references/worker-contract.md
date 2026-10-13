# Worker contract

`tf new` and `tf tab` render a template from `templates/` and send it signed. Every rendered prompt carries:

1. Signed header and footer with the sender's agent, task and id, and the one-line reply route (`send <orchestrator id> ... done <task> report=<pad>`).
2. Where it runs and that it must not touch the main checkout or other tasks.
3. The packet pad id to read first, plus the profile's `read_first` docs.
4. The profile's checks, each under `timeout N`, UI-only checks behind `tf lock <name>`, and build-isolation exports when the profile sets `build.isolate`.
5. The props to set (`phase`, `blocked`).
6. "Do not commit", no issues, no PRs.
7. The report schema (status, checks, changed, risks, next, failure) in a pad titled `report: <task> r<N>`, where N is the round (rule (b) below), so `tf report` reads the highest round. Every `scratchpad new` is pinned with `--task "$TERMIC_TASK_ID"` so the pad lands in the work task. The done line uses `$TERMIC_TASK` and `$TERMIC_TASK_ID` in double quotes so the worker's shell fills its own identity. A check that is expected to fail is written `red_<name>=<non-zero>` and still counts as pass; `red_<name>=0` and any other non-zero check do not.
8. Rule (a): heavy commands such as full test discovery and builds run in the background with output to a file, at most 2 heavy jobs run at once, and a targeted run with `-k` or one module is preferred. `hooks/guard.py` warns a worker that runs one in the foreground but never blocks it.
9. Rule (b): each report round writes a NEW pad titled `report: <task> r<N>` and never overwrites an earlier round's pad.

Edit a template, not a prompt, when this contract changes; `tests/unit/test_templates.py` checks every template.
