import os
import subprocess

from tf_lib import safety
from tf_lib.core import TfError


def git(cwd, *args, stdin=None):
   completed = subprocess.run(["git", "-C", cwd, *args], input=stdin, capture_output=True, text=True)

   if completed.returncode != 0:
      raise TfError(f"git {' '.join(args)} failed in {cwd}: {completed.stderr.strip()}")

   return completed.stdout


def holds_in_order(needed_lines, text_lines):
   remaining = iter(text_lines)
   return all(line in remaining for line in needed_lines)


def file_already_has(main_checkout, worktree, base, path):
   added_lines = [line[1:] for line in git(worktree, "diff", base, "--", path).splitlines() if line.startswith("+") and not line.startswith("+++")]
   main_file = os.path.join(main_checkout, path)

   if not os.path.isfile(main_file):
      return not added_lines

   with open(main_file, encoding="utf-8", errors="replace") as handle:
      main_lines = handle.read().splitlines()

   return holds_in_order(added_lines, main_lines)


def already_applied(main_checkout, worktree, base, patch, files):
   reverse_check = ["git", "-C", main_checkout, "apply", "--check", "--reverse"]
   completed = subprocess.run(reverse_check, input=patch, capture_output=True, text=True)

   if completed.returncode == 0:
      return True

   return all(file_already_has(main_checkout, worktree, base, path) for path in files)


def main_checkout_of(worktree):
   first_line = git(worktree, "worktree", "list", "--porcelain").splitlines()[0]
   return first_line.split(" ", 1)[1]


def patch_land(cli, task_ref):
   task = safety.guard(cli, task_ref, ("exists", "settled", "worktree"))
   task_id = task["id"]

   if safety.read_marker("tested", task_id) is None:
      raise TfError(f"landing '{task['name']}' needs the manual-test answer: run  ! tf tested {task_id} \"<what you exercised>\"")

   code, out, err = cli.run(["path", task_id])

   if code != 0:
      raise TfError(f"path exited {code}: {err.strip()}")

   worktree = out.strip()
   main_checkout = main_checkout_of(worktree)
   main_head = git(main_checkout, "rev-parse", "HEAD").strip()
   base = git(worktree, "merge-base", "HEAD", main_head).strip()
   git(worktree, "add", "--intent-to-add", "--all")
   patch = git(worktree, "diff", "--binary", base)

   if not patch.strip():
      raise TfError(f"'{task['name']}' has nothing to land")

   safety.guard(cli, task_id, ("exists", "settled"), expected_id=task_id)
   files = git(worktree, "diff", "--name-only", base).split()

   if already_applied(main_checkout, worktree, base, patch, files):
      safety.write_marker("landed", task_id, f"already in {main_checkout}, {len(files)} files merged by hand")
      return {"task": task["name"], "landed_files": files, "into": main_checkout, "note": "already merged, nothing applied"}

   git(main_checkout, "apply", "--check", "--3way", stdin=patch)
   git(main_checkout, "apply", "--3way", stdin=patch)
   safety.write_marker("landed", task_id, f"patch-landed {len(files)} files into {main_checkout}")
   return {"task": task["name"], "landed_files": files, "into": main_checkout}
