# Model routing

`tf route <role> --kind K --risk low|high --flag F` prints the model and the rule that picked it; `tf new` and `tf tab` call it for you and log the rule. `tf route --explain` prints the merged table.

Defaults (`config/routing.default.json`): Haiku for mechanical roles (scout, packer, audit, status); Sonnet for the orchestrator, ordinary impl and review; Opus for planning, triage, redesign and perf work, impl flagged ambiguous or cross-component, and high-risk review.

Escalation: after a failed attempt whose report says `failure: reasoning`, retry once on the same model with the failure evidence in the packet (`--failed 1 --failure reasoning`), then step up one rung (`--failed 2`). Environment failures never escalate. Fable is the top rung only with `"allow_fable": true`.

Override in `~/.config/termic-flow/routing.json` or under `"routing"` in a project's `.termic-flow.json`. Rules you add are checked before the defaults; project rules before user rules.
