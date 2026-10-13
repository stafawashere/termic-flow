import argparse
import json
import os
import shlex
import subprocess
import sys

from tf_lib import core, land, migrate, prompts, report, routing, runs, safety, tokens
from tf_lib import setup as project_setup
from tf_lib.core import Cli, TfError
from tf_lib.profile import load_profile

EXIT_TF_ERROR = 2
EXIT_STALE = 20
EXIT_FELL_BACK = 21


def emit(value):
   if isinstance(value, (dict, list)):
      print(json.dumps(value, separators=(",", ":")))
   else:
      print(value)


def log_quietly(cli, line):
   try:
      runs.log_line(cli, line)
   except TfError:
      pass


def route_for(profile, args, role):
   table = routing.load_routing(profile)
   return routing.route(
      table,
      role,
      kind=getattr(args, "kind", None),
      risk=args.risk,
      flags=args.flag,
      failed_attempts=args.failed,
      failure=args.failure,
   )


def cmd_check(cli, profile, args):
   help_data = cli.json(["help"])
   own_task = os.environ.get("TERMIC_TASK_ID", "none")
   return {
      "cli": cli.binary,
      "version": help_data.get("version"),
      "self": core.self_address(profile.get("agent", "claude")),
      "tab": os.environ.get("TERMIC_TAB_ID", "none"),
      "task": own_task,
      "profile": profile.get("_project_file", "default"),
      "state": str(safety.state_dir()),
   }


def cmd_new(cli, profile, args):
   name = core.task_name(profile, args.kind, args.subject)
   existing = [task["name"] for task in runs.snapshot(cli, safety.current_project(cli))]

   if name in existing:
      raise TfError(f"a task named '{name}' already exists")

   choice = route_for(profile, args, args.role)
   body = prompts.render(profile, args.template or prompts.template_for(args.role), task=name, packet=args.packet, flags=args.flag, role=args.role)
   argv = ["new", name, "--worktree", "--agent", profile.get("agent", "claude"), "--model", choice["model_id"], "-p", "-"]
   base_branch = profile.get("base") or checkout_branch()

   if base_branch:
      argv[3:3] = ["--base", base_branch]

   code, out, err = cli.run(argv, stdin=body)

   if code != 0:
      raise TfError(f"new exited {code}: {err.strip()}")

   cli.run(["tab", name, "--tab", "1", "--title", args.role])
   record_task(cli, name, args.role, choice)
   log_quietly(cli, f"spawned '{name}' role={args.role} model={choice['model']} rule={choice['rule']} packet={args.packet}")
   return {"task": name, "model": choice["model"], "rule": choice["rule"]}


def record_task(cli, name, role, choice):
   try:
      pad = runs.current_run()["pad"]
      runs.update_header(cli, pad, tasks={name: {"role": role, "model": choice["model"], "rule": choice["rule"]}})
   except TfError:
      pass


def read_report(cli, args):
   text = runs.pad_read(cli, args.pad, args.task)

   try:
      return report.parse_report(text)
   except TfError as error:
      if not args.task:
         raise

      task_id = safety.guard(cli, args.task)["id"]
      accepted = safety.read_marker("accepted", task_id)

      if accepted is None:
         raise TfError(f"{error}. If the human judges it a pass, they run  ! tf accept {task_id} \"<reason>\"")

      log_quietly(cli, f"report for {args.task} accepted by the human: {accepted['note']}")
      return {"status": "pass", "accepted": accepted["note"], "rejected_because": str(error)}


def cmd_tab(cli, profile, args):
   core.check_role(profile, args.role)
   target = safety.guard(cli, args.task)
   role_base = args.role.split("-", 1)[0]
   choice = route_for(profile, args, role_base)
   body = prompts.render(
      profile,
      args.template or prompts.template_for(args.role),
      task=target["name"],
      task_id=target["id"],
      packet=args.packet,
      report=args.report,
      subject=args.subject,
      flags=args.flag,
      role=args.role,
   )
   argv = ["tab", target["id"], "--agent", profile.get("agent", "claude"), "--model", choice["model_id"], "--title", args.role, "-p", "-"]
   code, out, err = cli.run(argv, stdin=body)

   if code != 0:
      raise TfError(f"tab exited {code}: {err.strip()}")

   log_quietly(cli, f"tab {args.role} in '{target['name']}' model={choice['model']} rule={choice['rule']}")
   return {"task": target["name"], "role": args.role, "model": choice["model"], "rule": choice["rule"]}


def cmd_send(cli, profile, args):
   target = safety.guard(cli, args.task)
   body = core.check_text(core.sign(args.text, profile.get("agent", "claude")))
   code, _, err = cli.run(["send", target["id"], "-p", "-"], stdin=body)

   if code != 0:
      raise TfError(f"send exited {code}: {err.strip()}")

   return "sent"


def cmd_group(cli, profile, args):
   colour = core.kind_colour(profile, args.kind)
   core.check_text(args.name)
   code, _, err = cli.run(["group", "--name", args.name, "--color", colour])

   if code != 0:
      raise TfError(f"group exited {code}: {err.strip()}")

   return {"group": args.name, "color": colour}


def cmd_do(cli, profile, args):
   run_slug = args.run or current_slug()
   expect = tuple(args.expect.split(",")) if args.expect else ("exists",)
   code, output, fallback = safety.run_mutation(cli, args.argv, run_slug, expect)

   if fallback:
      log_quietly(cli, f"REFUSED {' '.join(args.argv)}; queued in {fallback}")
      cli.run(["prop", "blocked", "needs-you"])
      print(f"refused; run it yourself:  ! bash {fallback}", file=sys.stderr)
      return EXIT_FELL_BACK

   log_quietly(cli, f"do {' '.join(args.argv)} -> exit {code}")
   sys.stdout.write(output)
   return code


def project_root():
   completed = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
   return completed.stdout.strip() if completed.returncode == 0 else os.getcwd()


def checkout_branch():
   completed = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True)
   return completed.stdout.strip() if completed.returncode == 0 else ""


def current_slug():
   try:
      return runs.current_run()["slug"]
   except TfError:
      return "adhoc"


def cmd_pr(cli, profile, args):
   task = safety.guard(cli, args.task, ("exists", "worktree"))

   if safety.read_marker("tested", task["id"]) is None:
      raise TfError(f"PR for '{task['name']}' needs the manual-test answer: run  ! tf tested {task['id']} \"<what you exercised>\"")

   code, path, err = cli.run(["path", task["id"]])

   if code != 0:
      raise TfError(f"path exited {code}: {err.strip()}")

   tool = "glab" if args.forge == "gitlab" else "gh"
   noun = "mr" if args.forge == "gitlab" else "pr"
   completed = subprocess.run([tool, noun, "create", *args.argv], cwd=path.strip())
   log_quietly(cli, f"{tool} {noun} create for '{task['name']}' -> exit {completed.returncode}")
   return completed.returncode


def cmd_fallback_add(cli, profile, args):
   return str(safety.add_fallback(current_slug(), args.argv, args.reason))


def cmd_run(cli, profile, args):
   if args.action == "start":
      return runs.run_start(cli, args.workflow, args.slug)

   run = runs.current_run()

   if args.action == "stage":
      runs.update_header(cli, run["pad"], stage=args.workflow)
      cli.run(["prop", "phase", args.workflow])
      runs.log_line(cli, f"stage {args.workflow}")
      return "ok"

   return run


def cmd_user_only(kind, args):
   folders = {"approve": "approvals", "tested": "tested", "accept": "accepted"}
   safety.write_marker(folders[kind], args.task_id, args.note or "")
   return f"{kind} recorded for {args.task_id}"


def cmd_auto_marker(cli, profile, kind, args):
   if profile.get("auto_approve") is not True:
      raise TfError(f"auto {kind} is off; set \"auto_approve\": true in .termic-flow.json")

   task = safety.guard(cli, args.task_id)

   if kind == "tested":
      impl_tabs = [tab for tab in task.get("tabs") or [] if tab.get("title") == "impl"]
      impl_phases = [prop.get("value") for tab in impl_tabs for prop in tab.get("props") or [] if prop.get("key") == "phase"]
      review_passed = "ready" in impl_phases

      if not review_passed:
         raise TfError(f"auto tested on '{task['name']}' needs a passed review first (impl tab phase=ready)")

   if kind == "approve":
      is_landed = safety.read_marker("landed", task["id"]) is not None
      is_hub = task["name"] in profile.get("hubs", [])
      is_own_task = task["id"] == os.environ.get("TERMIC_TASK_ID")
      is_safe_cleanup = is_landed and not is_hub and not is_own_task

      if not is_safe_cleanup:
         raise TfError(f"auto approve on '{task['name']}' needs a landed work task that is not a hub or your own task")

   folders = {"approve": "approvals", "tested": "tested"}
   safety.write_marker(folders[kind], task["id"], "auto: " + (args.note or "evidence checked by tf"))
   return f"{kind} auto-recorded for {task['id']}"


def tab_titles(cli, task):
   try:
      tabs = safety.fetch_task(cli, task["id"]).get("tabs")
   except TfError:
      return None

   return tabs if isinstance(tabs, list) else None


def scaffold_tasks(cli, project, touched=()):
   argv = ["list", "--project", project] if project else ["list"]
   tasks = []

   for task in cli.json(argv)["tasks"]:
      tabs = tab_titles(cli, task) if task["name"] in touched else None

      if tabs is None:
         tabs = task.get("open_tabs", 0)

      tasks.append({**task, "tabs": tabs})

   return tasks


def protected_names(cli, profile):
   names = set(profile.get("hubs") or [])
   own_task_id = os.environ.get("TERMIC_TASK_ID")

   if own_task_id:
      names.add(own_task_id)

      try:
         names.add(safety.fetch_task(cli, own_task_id)["name"])
      except TfError:
         pass

   return names


def new_task_argv(profile, row, project):
   name = row["argv"][1]
   argv = ["new", name, "--worktree", *row["argv"][2:], "--no-group"]
   base_branch = profile.get("base") or checkout_branch()

   if base_branch:
      argv[3:3] = ["--base", base_branch]

   if project:
      argv += ["--project", project]

   return argv


def setup_rows(cli, profile):
   project = safety.current_project(cli)
   tasks = scaffold_tasks(cli, project, project_setup.scaffold_task_names(profile))
   ids = {task["name"]: task["id"] for task in tasks}
   adopted = {task["name"] for task in tasks if safety.read_marker("scaffolded", task["id"])}
   protected = protected_names(cli, profile)
   rows = project_setup.scaffold_rows(profile, tasks, adopted)

   for row in rows:
      target = row["argv"][1]

      if row["argv"][0] == "new":
         row["argv"] = new_task_argv(profile, row, project)

      row["task_id"] = ids.get(target)
      is_protected = target in protected or row["task_id"] in protected

      if is_protected:
         row["approve"] = True
         row["why"] = "targets a hub or the calling task"

   return rows


def approval_hint(row):
   command = " ".join(shlex.quote(part) for part in row["argv"])

   if row["task_id"]:
      return f"! tf approve {row['task_id']}  then  tf do {command}"

   return f"rerun tf setup --preview once the task exists, then  ! tf approve <task-id>  and  tf do {command}"


def preview_line(row):
   command = " ".join(shlex.quote(part) for part in row["argv"])

   if not row["approve"]:
      return f"create   {command}"

   return f"approve  {command}  ({row['why']}; {approval_hint(row)})"


def apply_row(cli, row, project):
   verb, target = row["argv"][0], row["argv"][1]

   if verb == "new":
      already_there = target in {task["name"] for task in scaffold_tasks(cli, project)}

      if already_there:
         raise safety.StateChanged(f"'{target}' appeared since the plan was read")

      argv = row["argv"]
   else:
      task_id = safety.guard(cli, target)["id"]
      argv = [verb, task_id, *row["argv"][2:]]

   code, _, err = cli.run(argv)

   if code != 0:
      raise TfError(f"{verb} '{target}' exited {code}: {err.strip()}")

   if verb == "new":
      created_id = safety.guard(cli, target)["id"]
      safety.write_marker("scaffolded", created_id, target)

   return argv


def cmd_setup(cli, profile, args):
   rows = setup_rows(cli, profile)

   if not args.apply:
      return "\n".join(preview_line(row) for row in rows) or "nothing to scaffold"

   project = safety.current_project(cli)
   ran = []

   for row in rows:
      if row["approve"]:
         continue

      ran.append(apply_row(cli, row, project))

   log_quietly(cli, f"setup applied {len(ran)} scaffold rows")
   waiting = [preview_line(row) for row in rows if row["approve"]]
   return {"ran": ran, "approve": waiting}


def build_parser():
   parser = argparse.ArgumentParser(prog="tf", description="termic-flow driver for the Termic CLI")
   sub = parser.add_subparsers(dest="command", required=True)

   sub.add_parser("check")
   snap = sub.add_parser("snapshot")
   snap.add_argument("--project")
   sub.add_parser("audit").add_argument("--project")

   def add_route_flags(cmd):
      cmd.add_argument("--risk", choices=["low", "high"])
      cmd.add_argument("--flag", action="append", default=[])
      cmd.add_argument("--failed", type=int, default=0)
      cmd.add_argument("--failure", default="none", choices=["none", "reasoning", "environment"])
      cmd.add_argument("--template")

   rt = sub.add_parser("route")
   rt.add_argument("role", nargs="?")
   rt.add_argument("--kind")
   rt.add_argument("--explain", action="store_true")
   add_route_flags(rt)

   new = sub.add_parser("new")
   new.add_argument("kind")
   new.add_argument("subject")
   new.add_argument("--packet", required=True)
   new.add_argument("--role", default="impl")
   add_route_flags(new)

   tab = sub.add_parser("tab")
   tab.add_argument("task")
   tab.add_argument("role")
   tab.add_argument("--packet", required=True)
   tab.add_argument("--report")
   tab.add_argument("--subject")
   tab.add_argument("--kind")
   add_route_flags(tab)

   send = sub.add_parser("send")
   send.add_argument("task")
   send.add_argument("text")

   grp = sub.add_parser("group")
   grp.add_argument("name")
   grp.add_argument("kind")

   packet = sub.add_parser("packet")
   packet.add_argument("title")
   packet.add_argument("--task")

   rep = sub.add_parser("report")
   rep.add_argument("pad")
   rep.add_argument("--task")

   log = sub.add_parser("log")
   log.add_argument("line")
   log.add_argument("--pad")

   run = sub.add_parser("run")
   run.add_argument("action", choices=["start", "stage", "show"])
   run.add_argument("workflow", nargs="?")
   run.add_argument("slug", nargs="?")

   do = sub.add_parser("do")
   do.add_argument("--run")
   do.add_argument("--expect")
   do.add_argument("argv", nargs=argparse.REMAINDER)

   fb = sub.add_parser("fallback")
   fb.add_argument("action", choices=["path", "add"])
   fb.add_argument("--reason", default="refused by the harness")
   fb.add_argument("argv", nargs=argparse.REMAINDER)

   for kind in ("approve", "tested", "accept"):
      user = sub.add_parser(kind)
      user.add_argument("task_id")
      user.add_argument("note", nargs="?")

      if kind != "accept":
         user.add_argument("--auto", action="store_true")

   lock = sub.add_parser("lock")
   lock.add_argument("name")
   lock.add_argument("argv", nargs=argparse.REMAINDER)

   sub.add_parser("patch").add_argument("task")

   init = sub.add_parser("init")
   init.add_argument("--write", action="store_true")
   init.add_argument("--force", action="store_true")
   init.add_argument("--share", action="store_true")

   hubs = sub.add_parser("hubs")
   hubs.add_argument("--create", action="store_true")

   scaffold = sub.add_parser("setup")
   scaffold_mode = scaffold.add_mutually_exclusive_group(required=True)
   scaffold_mode.add_argument("--preview", action="store_true")
   scaffold_mode.add_argument("--apply", action="store_true")

   mig = sub.add_parser("migrate")
   mig.add_argument("--apply", action="store_true")

   pr = sub.add_parser("pr")
   pr.add_argument("task")
   pr.add_argument("--forge", choices=["github", "gitlab"], default="github")
   pr.add_argument("argv", nargs=argparse.REMAINDER)

   tok = sub.add_parser("tokens")
   tok.add_argument("sessions", nargs="+")

   return parser


def dispatch(args):
   profile = load_profile()
   offline_commands = ("route", "approve", "tested", "accept", "lock", "tokens", "fallback", "init", "migrate")
   needs_cli = args.command not in offline_commands or getattr(args, "auto", False)
   cli = Cli() if needs_cli else None
   command = args.command

   if command == "check":
      return cmd_check(cli, profile, args)

   if command == "snapshot":
      return runs.snapshot(cli, args.project or safety.current_project(cli))

   if command == "audit":
      return runs.audit(profile, runs.snapshot(cli, args.project or safety.current_project(cli)))

   if command == "route":
      if args.explain:
         return routing.explain(routing.load_routing(profile))

      return route_for(profile, args, args.role)

   handlers = {"new": cmd_new, "tab": cmd_tab, "send": cmd_send, "group": cmd_group, "do": cmd_do, "run": cmd_run, "pr": cmd_pr, "setup": cmd_setup}

   if command in handlers:
      return handlers[command](cli, profile, args)

   if command == "init":
      return project_setup.init(project_root(), write=args.write, force=args.force, share=args.share)

   if command == "migrate":
      return migrate.migrate(os.getcwd(), apply=args.apply)

   if command == "hubs":
      tasks = runs.snapshot(cli, safety.current_project(cli))

      if not args.create:
         return {"missing": project_setup.missing_hubs(profile, tasks)}

      created = project_setup.create_hubs(cli, profile, tasks)
      log_quietly(cli, f"created hubs: {', '.join(created) or 'none'}")
      return {"created": created}

   if command == "patch":
      result = land.patch_land(cli, args.task)
      log_quietly(cli, f"patch-landed '{result['task']}': {', '.join(result['landed_files'])}")
      return result

   if command == "packet":
      return runs.pad_new(cli, f"packet: {args.title}", sys.stdin.read(), task=args.task)

   if command == "report":
      return read_report(cli, args)

   if command == "log":
      runs.log_line(cli, args.line, args.pad)
      return "ok"

   if command == "fallback":
      if args.action == "path":
         return str(safety.fallback_path(current_slug()))

      return cmd_fallback_add(cli, profile, args)

   if command in ("approve", "tested", "accept"):
      if getattr(args, "auto", False):
         return cmd_auto_marker(cli, profile, command, args)

      return cmd_user_only(command, args)

   if command == "lock":
      command_argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
      return safety.with_lock(args.name, command_argv)

   if command == "tokens":
      results = {}

      for session in args.sessions:
         path = tokens.find_transcript(session) if not os.path.isfile(session) else session
         results[session] = tokens.count_tokens(path) if path else "not found"

      return results

   raise TfError(f"unknown command {command}")


def main(argv=None):
   args = build_parser().parse_args(argv)

   if getattr(args, "argv", None) and args.argv[:1] == ["--"] and args.command != "lock":
      args.argv = args.argv[1:]

   try:
      result = dispatch(args)
   except safety.Vanished as error:
      print(f"tf: stale: {error}", file=sys.stderr)
      return EXIT_STALE
   except safety.StateChanged as error:
      print(f"tf: stale: {error}", file=sys.stderr)
      return EXIT_STALE
   except TfError as error:
      print(f"tf: {error}", file=sys.stderr)
      return EXIT_TF_ERROR

   if isinstance(result, int) and not isinstance(result, bool):
      return result

   emit(result)
   return 0
