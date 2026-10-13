import json
import os
import re
import time

from tf_lib.core import TfError, check_text
from tf_lib.setup import scaffold_task_names
from tf_lib.safety import state_dir

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


def render_pad(header, log_lines):
   body = json.dumps(header, indent=2)
   return f"# run: {header['slug']}\n\n```json run\n{body}\n```\n\n## Log\n" + "".join(log_lines)


def run_start(cli, workflow, slug):
   header = {"slug": slug, "workflow": workflow, "stage": "start", "tasks": {}, "pending": []}
   pad = pad_new(cli, f"run: {slug}", render_pad(header, []))
   run = {"pad": pad, "slug": slug, "workflow": workflow}
   current_run_file().write_text(json.dumps(run), encoding="utf-8")
   cli.run(["prop", "run", pad])
   cli.run(["prop", "phase", workflow])
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


def compact_task(task):
   diff = task.get("diff") or {}
   phase = ""

   for prop in task.get("props") or []:
      if prop.get("key") == "phase":
         phase = ",".join(prop.get("values") or [])

   group = (task.get("group") or {}).get("name", "")
   return {
      "id": task["id"][:8],
      "name": task["name"],
      "state": task.get("work_state"),
      "main": bool(task.get("is_main_checkout")),
      "diff": f"{diff.get('files_changed', 0)}f+{diff.get('insertions', 0)}-{diff.get('deletions', 0)}",
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
   flags = {"bad_name": [], "hub_in_worktree": [], "work_on_main": [], "finished_unarchived": [], "ungrouped": []}

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

   counts = {flag: len(names) for flag, names in flags.items()}
   return {"counts": counts, "flags": flags}
