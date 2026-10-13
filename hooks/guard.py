#!/usr/bin/env python3
"""PreToolUse guard for termic-flow. Exit 2 blocks the call and stderr tells the model why."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from tf_lib.core import BANNED_DASHES
from tf_lib.profile import load_profile

CLI_WORD = r"(?:termic-cli|\$\{?TERMIC_CLI\}?\"?|(?<![\w-])termic)"
RAW_DESTRUCTIVE = re.compile(CLI_WORD + r"\s+(archive|quit|apply|tab\s+close|project\s+remove|schedule\s+delete)\b")
USER_ONLY = re.compile(r"(?:^|[;&|(\n])\s*(?:\w+=\S*\s+)*tf\s+(approve|tested|accept)\b(?P<rest>[^;&|\n]*)")
AUTO_MARKERS = ("approve", "tested")
HELP_FLAGS = ("-h", "--help")
RAW_PR = re.compile(r"\b(gh|glab)\s+(pr|mr)\s+create\b")
TF_TEXT = re.compile(r"(?:^|[\s;&|(])tf\s+(log|send|group|packet)\b")
TEST_RUNNERS = re.compile(
   r"(?:^|[;&|(\n])\s*(?:\w+=\S*\s+)*(?P<timeout>timeout\s+\d+\s+)?(?:python3?\s+-m\s+|uv\s+run\s+|poetry\s+run\s+|npx\s+)?"
   r"(npm\s+(?:run\s+)?test|vitest|pytest|cargo\s+test|make\s+e2e)\b"
)
HEAVY_RUNS = re.compile(
   r"(?:^|[;&|(\n])\s*(?:\w+=\S*\s+)*(?:timeout\s+\d+\s+)?"
   r"(?P<run>python3?\s+-m\s+unittest\s+discover\b[^;&|\n]*|make\b|swift\s+build\b|npm\s+run\s+build\b)"
)
ORCHESTRATOR_PREFIX = "ops:"
CHAIN_SEPARATOR = re.compile(r"(&&|\|\||;|\n|(?<![<>])&(?!>))")


def block(reason):
   print(f"termic-flow: {reason}", file=sys.stderr)
   sys.exit(2)


def chain_links(command):
   parts = CHAIN_SEPARATOR.split(command)
   links = parts[0::2]
   separators = parts[1::2] + [""]
   return [(link, separator == "&") for link, separator in zip(links, separators)]


def warn_heavy_foreground(command, tool_input):
   task_name = os.environ.get("TERMIC_TASK", "")
   is_worker = bool(os.environ.get("TERMIC_TASK_ID")) and not task_name.startswith(ORCHESTRATOR_PREFIX)
   whole_call_backgrounded = tool_input.get("run_in_background") is True

   if not is_worker or whole_call_backgrounded:
      return

   for link, link_backgrounded in chain_links(command):
      if link_backgrounded:
         continue

      for heavy in HEAVY_RUNS.finditer(link):
         is_targeted = "-k" in heavy.group("run").split()

         if is_targeted:
            continue

         print(
            "termic-flow: heavy command in the foreground; run it in the background with output to a file, "
            "keep at most 2 heavy jobs at once, and prefer -k or one module",
            file=sys.stderr,
         )
         return


def check_bash(command, profile):
   raw = RAW_DESTRUCTIVE.search(command)

   if raw:
      block(f"run '{raw.group(1)}' through  tf do {raw.group(1)} <task>  so it is revalidated and approval-gated")

   for user_only in USER_ONLY.finditer(command):
      verb = user_only.group(1)
      help_tokens = user_only.group("rest").split()
      is_help_only = bool(help_tokens) and all(token in HELP_FLAGS for token in help_tokens)

      if is_help_only:
         continue

      asks_auto = "--auto" in user_only.group("rest").split()
      auto_allowed = profile.get("auto_approve") is True and verb in AUTO_MARKERS

      if asks_auto and auto_allowed:
         continue

      block(f"tf {verb} is the human's decision; ask them to run it with  ! tf {verb} ...")

   if RAW_PR.search(command):
      block("open PRs through the land workflow, which asks the manual-test question first")

   for forbidden in profile.get("forbid", {}).get("commands", []):
      if forbidden in command:
         block(f"'{forbidden}' is forbidden by this project's termic-flow profile")

   hook_settings = profile.get("hooks", {})
   writes_text = TF_TEXT.search(command)
   has_dash = any(dash in command for dash in BANNED_DASHES)

   if hook_settings.get("ban_dashes") and writes_text and has_dash:
      block("no em dashes or spaced en dashes in pads, logs or prompts; use a comma or 'and'")

   untimed_runs = [run for run in TEST_RUNNERS.finditer(command) if not run.group("timeout")]

   if hook_settings.get("require_timeout") and untimed_runs:
      block("test commands need a  timeout N  prefix so a hang cannot run forever")


def check_file_write(path, profile):
   for forbidden in profile.get("forbid", {}).get("paths", []):
      if os.path.basename(path) == forbidden or path.endswith("/" + forbidden):
         block(f"{forbidden} is maintainer-only per this project's termic-flow profile")


def main():
   event = json.load(sys.stdin)
   tool = event.get("tool_name", "")
   tool_input = event.get("tool_input") or {}
   profile = load_profile(event.get("cwd") or os.getcwd())

   if tool == "Bash":
      check_bash(tool_input.get("command", ""), profile)
      warn_heavy_foreground(tool_input.get("command", ""), tool_input)
   elif tool in ("Write", "Edit", "MultiEdit"):
      check_file_write(tool_input.get("file_path", ""), profile)

   sys.exit(0)


if __name__ == "__main__":
   main()
