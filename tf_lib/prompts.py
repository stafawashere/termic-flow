import os

from tf_lib.core import TfError, check_text, sign
from tf_lib.profile import PLUGIN_ROOT
from tf_lib.report import TEMPLATE as REPORT_TEMPLATE

WORKTREE_EXPR = "$(git rev-parse --show-toplevel)"
ROLE_TEMPLATES = {"spec": "plan"}


def render_checks(profile, flags):
   lines = []

   for check in profile.get("checks", []):
      condition = check.get("when")
      applies = condition is None or condition in flags

      if not applies:
         continue

      command = check["run"]

      if check.get("lock"):
         command = f"tf lock {check['lock']} -- {command}"

      lines.append(f"- {check['name']}: {command}")

   return "\n".join(lines) or "- discover the project's test command from its CI config, and run it under timeout N"


def render_env(profile):
   build = profile.get("build", {})

   if not build.get("isolate"):
      return ""

   exports = [
      f"export {key}=\"{value.replace('{worktree}', WORKTREE_EXPR)}\""
      for key, value in build.get("env", {}).items()
   ]
   return "Before any build, run: " + "; ".join(exports) + "\n"


def template_for(role):
   role_base = role.split("-", 1)[0]
   return ROLE_TEMPLATES.get(role_base, role_base)


def render(profile, template, **slots):
   path = PLUGIN_ROOT / "templates" / f"{template}.txt"

   if not path.is_file():
      raise TfError(f"no template '{template}'")

   flags = set(slots.pop("flags", ()))
   values = {
      "read_first": ", ".join(profile.get("read_first", [])),
      "checks": render_checks(profile, flags),
      "env_line": render_env(profile),
      "report_template": REPORT_TEMPLATE.format(task=slots.get("task", slots.get("subject", ""))),
      "task": "",
      "task_id": "",
      "packet": "",
      "report": "",
      "subject": "",
      "role": template,
      "owner": os.environ.get("TERMIC_TASK_ID", "main"),
   }
   values.update({key: value for key, value in slots.items() if value is not None})
   body = path.read_text(encoding="utf-8").format(**values)
   return check_text(sign(body.strip(), profile.get("agent", "claude")))
