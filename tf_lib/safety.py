import fcntl
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from tf_lib.core import EXIT_REFUSED, TfError

EXIT_CONNECTION_LOST = 8
DESTRUCTIVE_VERBS = ("archive", "tab close", "apply", "rename", "group")
NEEDS_APPROVAL = ("archive", "tab close", "rename", "group")
VALUE_FLAGS = ("--name", "--color", "--project")

# A restructure verb touches an existing task only when it names one. `rename` takes
# [task] <new name>, so it needs two positionals. `group --name X` with no task names
# the caller's own group, which is an additive create and stays ungated.
EXISTING_TASK_POSITIONALS = {"rename": 2, "group": 1}
NEEDS_TESTED = ("apply",)
TASK_ID_SHAPE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def state_dir():
   override = os.environ.get("TF_STATE_DIR") or os.environ.get("CLAUDE_PLUGIN_DATA")
   base = Path(override) if override else Path.home() / ".local" / "state" / "termic-flow"
   base.mkdir(parents=True, exist_ok=True)
   return base


def marker_path(kind, task_id):
   folder = state_dir() / kind
   folder.mkdir(exist_ok=True)
   return folder / task_id


class Vanished(TfError):
   pass


class StateChanged(TfError):
   pass


def is_within(path, root):
   return path == root or root in path.parents


def project_for_path(cli, path):
   checkout = Path(path).resolve()
   roots = []
   code, out, err = cli.run(["project", "list", "--json"])

   if code == 0:
      roots += [(entry["root_path"], entry["name"]) for entry in json.loads(out).get("projects", [])]

   code, out, err = cli.run(["list", "--json"])

   if code == 0:
      roots += [(task["path"], task["project"]) for task in json.loads(out).get("tasks", []) if task.get("path")]

   matches = [(Path(root).resolve(), project) for root, project in roots if is_within(checkout, Path(root).resolve())]

   if not matches:
      return None

   deepest_root, project = max(matches, key=lambda match: len(match[0].parts))
   return project


def current_project(cli):
   own_task_id = os.environ.get("TERMIC_TASK_ID")

   if not own_task_id:
      return project_for_path(cli, os.getcwd())

   code, out, err = cli.run(["status", own_task_id, "--json"])

   if code != 0:
      return None

   return json.loads(out)["task"].get("project")


def fetch_task(cli, task):
   argv = ["status", task, "--json"]
   is_bare_name = not TASK_ID_SHAPE.match(task) and "/" not in task
   project = current_project(cli) if is_bare_name else None

   if project:
      argv += ["--project", project]

   code, out, err = cli.run(argv)

   if code != 0:
      raise Vanished(f"task '{task}' is gone or unreadable (status exited {code}: {err.strip()})")

   return json.loads(out)["task"]


def is_settled(task):
   is_idle = task.get("work_state") != "working"
   has_queue = any(tab.get("queued", 0) > 0 for tab in task.get("tabs", []))
   return is_idle and not has_queue


def is_clean(task):
   diff = task.get("diff") or {}
   changed = diff.get("files_changed", 0) + diff.get("untracked", 0)
   return changed == 0


def guard(cli, task, expect=("exists",), expected_id=None):
   current = fetch_task(cli, task)
   id_moved = expected_id is not None and current["id"] != expected_id

   if id_moved:
      raise StateChanged(f"'{task}' now resolves to {current['id']}, not {expected_id}")

   checks = {
      "exists": lambda t: True,
      "settled": is_settled,
      "clean": is_clean,
      "worktree": lambda t: not t.get("is_main_checkout"),
   }

   for name in expect:
      if name not in checks:
         raise TfError(f"unknown expectation '{name}'")

      if not checks[name](current):
         raise StateChanged(f"'{task}' failed expectation '{name}' (work_state={current.get('work_state')})")

   return current


def write_marker(kind, task_id, note):
   payload = {"task_id": task_id, "note": note, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
   marker_path(kind, task_id).write_text(json.dumps(payload), encoding="utf-8")


def read_marker(kind, task_id):
   path = marker_path(kind, task_id)

   if not path.is_file():
      return None

   return json.loads(path.read_text(encoding="utf-8"))


def fallback_path(run_slug):
   folder = state_dir() / "fallback"
   folder.mkdir(exist_ok=True)
   return folder / f"{run_slug}.sh"


def add_fallback(run_slug, argv, reason, task_id=None):
   path = fallback_path(run_slug)
   is_new = not path.exists()

   with open(path, "a", encoding="utf-8") as handle:
      if is_new:
         handle.write("#!/usr/bin/env bash\n")
         handle.write("# Commands termic-flow could not run itself. Each one revalidates its task first.\n")
         handle.write("set -u\n")
         handle.write(": \"${TERMIC_CLI:=termic}\"\n\n")

      handle.write(f"# {time.strftime('%Y-%m-%d %H:%M')} {reason}\n")
      command = " ".join(shlex.quote(part) for part in argv)

      if task_id:
         handle.write(
            f"if \"$TERMIC_CLI\" status {shlex.quote(task_id)} >/dev/null 2>&1; then "
            f"\"$TERMIC_CLI\" {command}; else echo \"skip: {task_id} is gone\"; fi\n\n"
         )
      else:
         handle.write(f"\"$TERMIC_CLI\" {command}\n\n")

   path.chmod(0o755)
   return path


def verb_of(argv):
   two_words = " ".join(argv[:2])

   if two_words in DESTRUCTIVE_VERBS:
      return two_words

   return argv[0]


def positional_indexes(argv, verb):
   offset = len(verb.split())
   found = []
   skip_next = False

   for index in range(offset, len(argv)):
      part = argv[index]

      if skip_next:
         skip_next = False
         continue

      if part.startswith("-"):
         skip_next = part in VALUE_FLAGS
         continue

      found.append(index)

   return found


def positionals_of(argv, verb):
   return [argv[index] for index in positional_indexes(argv, verb)]


def targets_existing_task(argv, verb):
   needed = EXISTING_TASK_POSITIONALS.get(verb)

   if needed is None:
      return True

   return len(positionals_of(argv, verb)) >= needed


def task_of(argv, verb):
   rest = positionals_of(argv, verb)
   names_no_task = not targets_existing_task(argv, verb)

   if not rest or names_no_task:
      raise TfError(f"'{verb}' needs a task argument under tf do, so it can be revalidated")

   return rest[0]


def gate_destructive(verb, task):
   task_id = task["id"]

   if verb in NEEDS_APPROVAL and read_marker("approvals", task_id) is None:
      raise TfError(f"{verb} on '{task['name']}' needs your approval: run  ! tf approve {task_id}")

   if verb in NEEDS_TESTED and read_marker("tested", task_id) is None:
      raise TfError(
         f"apply on '{task['name']}' needs the manual-test answer: run  ! tf tested {task_id} \"<what you exercised>\""
      )

   is_archive = verb == "archive"
   unlanded = not is_clean(task) and read_marker("landed", task_id) is None

   if is_archive and unlanded:
      raise TfError(f"'{task['name']}' has unlanded changes; land it or discard them by hand first")


def run_mutation(cli, argv, run_slug, expect=("exists",)):
   """Returns (exit_code, output, fallback_path_or_None)."""
   verb = verb_of(argv)
   is_additive_group = verb == "group" and not targets_existing_task(argv, verb)

   if is_additive_group:
      code, out, err = cli.run(list(argv))
      return code, out + err, None

   task_ref = task_of(argv, verb)
   first_look = guard(cli, task_ref, expect)
   task_id = first_look["id"]

   if verb in DESTRUCTIVE_VERBS:
      gate_destructive(verb, first_look)

   guard(cli, task_id, expect, expected_id=task_id)
   ref_index = positional_indexes(argv, verb)[0]
   resolved = [*argv[:ref_index], task_id, *argv[ref_index + 1:]]

   if verb in ("archive", "apply", "tab close") and "--yes" not in resolved:
      resolved.append("--yes")

   code, out, err = cli.run(resolved)

   if code == EXIT_CONNECTION_LOST:
      guard(cli, task_id, ("exists",), expected_id=task_id)
      code, out, err = cli.run(resolved)

   if code == EXIT_REFUSED:
      path = add_fallback(run_slug, resolved, f"refused (exit 6): {err.strip()[:120]}", task_id)
      return code, err, path

   if code == 0 and verb == "apply":
      write_marker("landed", task_id, "applied by tf do")

   return code, out + err, None


def with_lock(name, command):
   folder = state_dir() / "locks"
   folder.mkdir(exist_ok=True)

   with open(folder / f"{name}.lock", "w", encoding="utf-8") as handle:
      fcntl.flock(handle, fcntl.LOCK_EX)
      handle.write(str(os.getpid()))
      handle.flush()
      return subprocess.run(command).returncode
