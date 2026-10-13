# Refusals and stale state

| Signal | Meaning | Do |
|---|---|---|
| `tf do` exit 20 | Task vanished, was renamed, or is not in the expected state | Re-snapshot, log it, decide again |
| `tf do` exit 21 | The CLI refused (exit 6); the command is queued in the fallback script | Log, continue with independent steps |
| `tf do` exit 2 with "needs your approval" | No per-task approval token | Ask the user for `! tf approve <id>` |
| Bash call refused by the harness or classifier | Not run at all | `tf fallback add -- <args>`, or append to the fallback file by hand; never retry more than once |
| `tf report` rejects a report the diff shows is fine | Never edit the report pad | Ask the user for `! tf accept <task-id> "<reason>"`, then rerun `tf report` |
| CLI exit 3 / 7 / 9 on a watched run | Needs input / timeout / never delivered | Log and check `"$TERMIC_CLI" logs <task>` |
| CLI exit 10 after apply | Main checkout conflicted | Stop; the user resolves it |

Every fallback line revalidates its task before acting, so the user can run the script late.
