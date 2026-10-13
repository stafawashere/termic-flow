import json
import os
import re
import subprocess

VALID_COLOURS = ("red", "orange", "yellow", "green", "teal", "blue", "purple", "pink")
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
BANNED_DASHES = (EM_DASH, f" {EN_DASH} ")

EXIT_REFUSED = 6
EXIT_NEEDS_INPUT = 3
EXIT_TIMEOUT = 7
EXIT_UNDELIVERED = 9
EXIT_CONFLICTED = 10


class TfError(Exception):
   pass


def task_name(profile, kind, subject):
   if kind not in profile["kinds"]:
      raise TfError(f"kind '{kind}' is not one of: {' '.join(profile['kinds'])}")

   if not KEBAB.match(subject):
      raise TfError(f"subject '{subject}' must be lowercase kebab case")

   return f"{kind}: {subject}"


def kind_colour(profile, kind):
   colour = profile["kinds"].get(kind)

   if colour not in VALID_COLOURS:
      raise TfError(f"colour '{colour}' for kind '{kind}' is not a Termic group colour: {' '.join(VALID_COLOURS)}")

   return colour


def check_role(profile, role):
   role_base = role.split("-", 1)[0]

   if role_base not in profile["roles"]:
      raise TfError(f"role '{role}' must start with one of: {' '.join(profile['roles'])}")

   return role


def check_hub(profile, hub):
   if hub not in profile["hubs"]:
      raise TfError(f"hub '{hub}' is not one of: {' '.join(profile['hubs'])}")

   return hub


def check_text(text):
   for dash in BANNED_DASHES:
      if dash in text:
         raise TfError("text contains an em dash or spaced en dash; use a comma, period or 'and'")

   return text


def self_address(agent="claude"):
   name = os.environ.get("TERMIC_TASK", "outside")
   task_id = os.environ.get("TERMIC_TASK_ID", "none")
   return f"agent:{agent} task:{name} id:{task_id}"


def sign(body, agent="claude"):
   me = self_address(agent)
   own_id = os.environ.get("TERMIC_TASK_ID")
   own_tab = os.environ.get("TERMIC_TAB_ID")
   tab_flag = f" --tab {own_tab}" if own_tab else ""
   reply = ""

   if own_id:
      reply = (
         f"\nWhen done, reply with one line: \"$TERMIC_CLI\" send {own_id}{tab_flag} -p "
         f"'[message from agent:<you> task:<your task> id:<your id>] done <your task> report=<report pad id>'"
      )

   return f"[message from {me}]\n{body}{reply}\n-- {me}"


class Cli:
   def __init__(self, binary=None):
      self.binary = binary or os.environ.get("TERMIC_CLI")

      if not self.binary:
         raise TfError("TERMIC_CLI is unset, so the Termic control plane is off")

   def run(self, args, stdin=None):
      completed = subprocess.run(
         [self.binary, *args],
         input=stdin,
         capture_output=True,
         text=True,
      )
      return completed.returncode, completed.stdout, completed.stderr

   def json(self, args):
      code, out, err = self.run([*args, "--json"])

      if code != 0:
         raise TfError(f"{' '.join(args)} exited {code}: {err.strip() or out.strip()}")

      return json.loads(out)
