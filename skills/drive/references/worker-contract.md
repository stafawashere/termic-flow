# Worker contract

`tf new` and `tf tab` render a template from `templates/` and send it signed. Every rendered prompt carries:

1. Signed header and footer with the sender's agent, task and id, and the one-line reply route (`send <orchestrator id> ... done <task> report=<pad>`).
2. Where it runs and that it must not touch the main checkout or other tasks.
3. The packet pad id to read first, plus the profile's `read_first` docs.
4. The profile's checks, each under `timeout N`, UI-only checks behind `tf lock <name>`, and build-isolation exports when the profile sets `build.isolate`.
5. The props to set (`phase`, `blocked`).
6. "Do not commit", no issues, no PRs.
7. The report schema (status, checks, changed, risks, next, failure) in a pad titled `report: <task>`.

Edit a template, not a prompt, when this contract changes; `tests/unit/test_templates.py` checks every template.
