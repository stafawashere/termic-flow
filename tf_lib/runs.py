import json
import os
import re
import sys
import time

from tf_lib.core import TfError, check_text
from tf_lib.setup import scaffold_task_names
from tf_lib.safety import read_marker, state_dir

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
HEADER = re.compile(r"```json run\n(.*?)\n```", re.S)


def pad_new(cli, title, content, task=None):
   check_text(content)
   args = ["scratchpad", "new", "--title", title, "--content", "-"]

   if task:
      args += ["--task", task]

   code, out, err = cli.run(args, stdin=content)

   if code != 0:
      raise TfError(f"scratchpad new exited {code}: {err.strip()}")

   match = UUID.search(out)

   if not match:
      raise TfError(f"scratchpad new printed no pad id: {out.strip()[:80]}")

   return match.group(0)


def pad_read(cli, pad, task=None):
   args = ["scratchpad", "read", pad]

   if task:
      args += ["--task", task]

   code, out, err = cli.run(args)

   if code != 0:
      raise TfError(f"scratchpad read {pad} exited {code}: {err.strip()}")

   return out


def pad_write(cli, pad, content, append=False):
   check_text(content)
   args = ["scratchpad", "write", pad, "--content", "-"]

   if append:
      args.append("--append")

   code, _, err = cli.run(args, stdin=content)

   if code != 0:
      raise TfError(f"scratchpad write {pad} exited {code}: {err.strip()}")


def current_run_file():
   tab = os.environ.get("TERMIC_TAB_ID", "no-tab")
   return state_dir() / f"current-run-{tab}.json"


def current_run():
   path = current_run_file()

   if not path.is_file():
      raise TfError("no run is open in this tab; start one with tf run start <workflow> <slug>")

   return json.loads(path.read_text(encoding="utf-8"))


def live_spawned_tasks(cli, run):
   spawned = set(read_header(pad_read(cli, run["pad"])).get("tasks") or {})
   live = []

   for task in cli.json(["list"])["tasks"]:
      is_spawned = task["name"] in spawned
      is_landed = read_marker("landed", task["id"]) is not None

      if is_spawned and not is_landed:
         live.append(task["name"])

   return live


def run_end(cli):
   run = current_run()
   live = live_spawned_tasks(cli, run)

   if live:
      noun = "task" if len(live) == 1 else "tasks"
      print(f"run stays open: {len(live)} live {noun} ({', '.join(live)})", file=sys.stderr)
      return {**run, "open": live}

   log_line(cli, "run ended", pad=run["pad"])
   current_run_file().unlink(missing_ok=True)
   return run


def end_open_run(cli):
   if not current_run_file().is_file():
      return

   try:
      run_end(cli)
   except TfError as error:
      print(f"run stays open: {error}", file=sys.stderr)


def render_pad(header, log_lines):
   body = json.dumps(header, indent=2)
   return f"# run: {header['slug']}\n\n```json run\n{body}\n```\n\n## Log\n" + "".join(log_lines)


DEFAULT_TASK_NAME = re.compile(r"^[a-z]+-\d+$")
ORCHESTRATOR_KIND = "ops"


def orchestrator_name(profile, workflow, slug):
   if ORCHESTRATOR_KIND not in profile["kinds"]:
      return None

   return f"{ORCHESTRATOR_KIND}: {workflow} {slug}"


def rename_orchestrator(cli, profile, workflow, slug):
   task_id = os.environ.get("TERMIC_TASK_ID")
   current_name = os.environ.get("TERMIC_TASK", "")
   new_name = orchestrator_name(profile, workflow, slug)
   is_default_name = bool(DEFAULT_TASK_NAME.match(current_name))

   if not (task_id and new_name and is_default_name):
      return

   cli.run(["rename", task_id, new_name])


def run_task_flags(run):
   return ["--task", run["task"]] if run.get("task") else []


def open_run_task_flags():
   has_open_run = current_run_file().is_file()
   return run_task_flags(current_run()) if has_open_run else []


def run_start(cli, workflow, slug, profile=None, task=None):
   header = {"slug": slug, "workflow": workflow, "stage": "start", "tasks": {}, "pending": []}
   pad = pad_new(cli, f"run: {slug}", render_pad(header, []), task=task)
   run = {"pad": pad, "slug": slug, "workflow": workflow}

   if task:
      run["task"] = task

   current_run_file().write_text(json.dumps(run), encoding="utf-8")
   cli.run(["prop", "run", pad, *run_task_flags(run)])
   cli.run(["prop", "phase", workflow, *run_task_flags(run)])

   should_rename = profile is not None and not task

   if should_rename:
      rename_orchestrator(cli, profile, workflow, slug)

   return run


def read_header(text):
   match = HEADER.search(text)

   if not match:
      raise TfError("run pad has no json run header")

   return json.loads(match.group(1))


def update_header(cli, pad, **changes):
   text = pad_read(cli, pad)
   header = read_header(text)

   for key, value in changes.items():
      is_merge = isinstance(value, dict) and isinstance(header.get(key), dict)
      header[key] = {**header[key], **value} if is_merge else value

   new_text = HEADER.sub(lambda _: "```json run\n" + json.dumps(header, indent=2) + "\n```", text, count=1)
   pad_write(cli, pad, new_text)
   return header


def log_line(cli, line, pad=None):
   target = pad or current_run()["pad"]
   stamp = time.strftime("%H:%M")
   pad_write(cli, target, f"- {stamp} {line}\n", append=True)


def prop_value(task, key):
   for prop in task.get("props") or []:
      if prop.get("key") == key:
         values = prop.get("values") or [prop.get("value") or ""]
         return ",".join(values)

   return ""


def compact_task(task):
   diff = task.get("diff") or {}
   phase = prop_value(task, "phase")

   group = (task.get("group") or {}).get("name", "")
   return {
      "id": task["id"][:8],
      "name": task["name"],
      "state": task.get("work_state"),
      "main": bool(task.get("is_main_checkout")),
      "diff": f"{diff.get('files_changed', 0)}f+{diff.get('insertions', 0)}-{diff.get('deletions', 0)}",
      "dirty": diff.get("files_changed", 0) + diff.get("untracked", 0),
      "tabs": task.get("open_tabs", 0),
      "phase": phase,
      "group": group,
   }


def snapshot(cli, project=None):
   args = ["list"]

   if project:
      args += ["--project", project]

   tasks = cli.json(args)["tasks"]
   return [compact_task(task) for task in tasks]


def audit(profile, tasks):
   hubs = set(profile["hubs"])
   kinds = set(profile["kinds"])
   seeds = scaffold_task_names(profile)
   flags = {"bad_name": [], "hub_in_worktree": [], "work_on_main": [], "finished_unarchived": [], "ungrouped": [], "dirty_main": []}

   for task in tasks:
      name = task["name"]
      kind = name.split(": ", 1)[0] if ": " in name else None
      is_hub = name in hubs
      is_work = kind in kinds

      if not (is_hub or is_work):
         flags["bad_name"].append(name)

      if is_hub and not task["main"]:
         flags["hub_in_worktree"].append(name)

      if is_work and task["main"]:
         flags["work_on_main"].append(name)

      is_seed = name in seeds
      is_finished = is_work and not is_seed and task["state"] == "idle" and task["diff"].startswith("0f")

      if is_finished:
         flags["finished_unarchived"].append(name)

      if is_work and not task["group"]:
         flags["ungrouped"].append(name)

      is_dirty_main = task["main"] and task.get("dirty", 0) > 0

      if is_dirty_main:
         flags["dirty_main"].append(name)

   counts = {flag: len(names) for flag, names in flags.items()}
   return {"counts": counts, "flags": flags}


STALL_MINUTES = 10
QUIET_PHASES = ("ready",)


def activity_signature(task):
   diff = task.get("diff") or {}
   return f"{prop_value(task, 'phase')}|{diff.get('files_changed', 0)}+{diff.get('insertions', 0)}-{diff.get('deletions', 0)}"


def stall_step(entry, task, now, limit_seconds):
   signature = activity_signature(task)
   is_fresh = entry is None or entry.get("sig") != signature

   if is_fresh:
      return {"sig": signature, "seen": now, "nudged": None, "blocked": False}, None

   is_working = task.get("work_state") == "working"
   is_nudged = entry.get("nudged") is not None

   if is_working:
      return (entry, None) if is_nudged else ({**entry, "seen": now}, None)

   is_blocked = entry.get("blocked") or bool(prop_value(task, "blocked"))
   is_quiet = prop_value(task, "phase") in QUIET_PHASES

   if is_blocked or is_quiet:
      return entry, None

   silent_too_long = now - entry["seen"] > limit_seconds

   if not is_nudged:
      return ({**entry, "nudged": now}, "nudge") if silent_too_long else (entry, None)

   ignored_nudge = now - entry["nudged"] > limit_seconds
   return ({**entry, "blocked": True}, "block") if ignored_nudge else (entry, None)


def stall_check(cli, profile, nudge):
   run = current_run()
   minutes = profile.get("stall_minutes", STALL_MINUTES)
   header = read_header(pad_read(cli, run["pad"]))
   stall = header.get("stall") or {}
   live = set(live_spawned_tasks(cli, run))
   now = time.time()
   actions = []
   failure = None

   for task in cli.json(["list"])["tasks"]:
      name = task["name"]

      if name not in live:
         continue

      entry, action = stall_step(stall.get(name), task, now, minutes * 60)

      if action == "nudge":
         try:
            nudge(task)
         except TfError as error:
            failure = f"nudge for '{name}' failed: {error}"
            break

         log_line(cli, f"nudged {name}", pad=run["pad"])

      if action == "block":
         reason = f"silent past {minutes} min after nudge"
         code, _, err = cli.run(["prop", "blocked", reason, "--task", task["id"]])

         if code != 0:
            failure = f"prop blocked on '{name}' exited {code}: {err.strip()}"
            break

         log_line(cli, f"blocked {name}: {reason}", pad=run["pad"])

      stall[name] = entry

      if action:
         actions.append({"task": name, "action": action})

   update_header(cli, run["pad"], stall=stall)

   if failure:
      raise TfError(failure)

   return actions
