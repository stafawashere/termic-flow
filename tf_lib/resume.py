import time

from tf_lib import report
from tf_lib.core import TfError
from tf_lib.runs import STALL_MINUTES, UUID, activity_signature, pad_read, prop_value, read_header

PAD_KINDS = ("report", "review")


def list_pads(cli, task=None):
   args = ["scratchpad", "list"]

   if task:
      args += ["--task", task]

   code, out, err = cli.run(args)

   if code != 0:
      raise TfError(f"scratchpad list exited {code}: {err.strip()}")

   return report.parse_pad_list(out)


def find_run_pad(cli, ref):
   if UUID.fullmatch(ref):
      return ref

   title = f"run: {ref}"
   matches = [pad["id"] for pad in list_pads(cli) if pad["title"] == title]

   if not matches:
      raise TfError(f"no run pad titled '{title}'")

   return matches[-1]


def is_task_pad(title, name):
   for kind in PAD_KINDS:
      prefix = f"{kind}: {name}"
      has_round = report.ROUND_SUFFIX.fullmatch(title[len(prefix):]) is not None

      if title == prefix or (title.startswith(prefix) and has_round):
         return True

   return False


def unlogged_pads(cli, task, run_text):
   pads = [pad for pad in list_pads(cli, task["id"]) if is_task_pad(pad["title"], task["name"])]
   return [pad for pad in pads if pad["id"] not in run_text]


def stall_due(entry, task, limit_seconds):
   if not entry or entry.get("nudged") is not None:
      return False

   is_unchanged = entry.get("sig") == activity_signature(task)
   is_idle = task.get("work_state") != "working"
   is_silent = time.time() - entry["seen"] > limit_seconds
   return is_unchanged and is_idle and is_silent


def next_action(task, entry, pads, limit_seconds):
   blocked_reason = prop_value(task, "blocked")
   stall_blocked = bool(entry and entry.get("blocked"))

   if blocked_reason or stall_blocked:
      return f"blocked: {blocked_reason or 'silent after nudge'}"

   if any(pad["title"].startswith("review: ") for pad in pads):
      return "land"

   if pads:
      return "review"

   if stall_due(entry, task, limit_seconds):
      return "nudge"

   return "wait"


def resume(cli, profile, ref):
   pad = find_run_pad(cli, ref)
   text = pad_read(cli, pad)
   header = read_header(text)
   stall = header.get("stall") or {}
   limit_seconds = profile.get("stall_minutes", STALL_MINUTES) * 60
   tasks = {task["name"]: task for task in cli.json(["list"])["tasks"]}
   lines = []

   for name in header.get("tasks") or {}:
      task = tasks.get(name)

      if task is None:
         lines.append(f"{name} phase=gone next=wait")
         continue

      pads = unlogged_pads(cli, task, text)
      action = next_action(task, stall.get(name), pads, limit_seconds)
      line = f"{name} phase={prop_value(task, 'phase') or '-'} next={action}"

      if pads:
         line += " pads=" + ", ".join(f"{pad['id']} {pad['title']}" for pad in pads)

      lines.append(line)

   return "\n".join(lines)
