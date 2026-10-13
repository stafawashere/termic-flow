import json
from pathlib import Path

from tf_lib.core import VALID_COLOURS
from tf_lib.profile import find_project_file, read_json
from tf_lib.setup import detect, plugin_version, version_tuple

COLOUR_REPLACEMENTS = {"gray": "pink", "grey": "pink"}


def fix_colours(config, root):
   notes = []

   for kind, colour in dict(config.get("kinds", {})).items():
      if colour in VALID_COLOURS:
         continue

      replacement = COLOUR_REPLACEMENTS.get(colour, "blue")
      config["kinds"][kind] = replacement
      notes.append(f"kinds.{kind}: '{colour}' is not a Termic colour, now '{replacement}'")

   return notes


def wrap_checks_in_timeout(config, root):
   notes = []

   for check in config.get("checks", []):
      runs_bare = not check.get("run", "").startswith(("timeout ", "tf lock "))

      if runs_bare:
         check["run"] = f"timeout 600 {check['run']}"
         notes.append(f"checks.{check.get('name')}: wrapped in timeout 600")

   return notes


def add_new_detections(config, root):
   notes = []
   detected = detect(root)
   known = {check.get("name") for check in config.get("checks", [])}

   for check in detected["checks"]:
      if check["name"] not in known:
         config.setdefault("checks", []).append(check)
         notes.append(f"checks.{check['name']}: added ({check['run']})")

   if "build" in detected and "build" not in config:
      config["build"] = detected["build"]
      notes.append("build: per-worktree target isolation added")

   return notes


LEGACY_PATHS = (
   (".claude/skills/termic-driver", "an older termic-driver skill; replace its SKILL.md with a pointer to termic-flow so the two cannot drift"),
   (".claude/skills/termic-restructure", "an older termic-restructure skill; termic-flow setup replaces it"),
)


def advisories(root):
   return [f"{path}: {advice}" for path, advice in LEGACY_PATHS if (root / path).exists()]


MIGRATIONS = [
   ("0.2.0", "Termic has no gray group colour", fix_colours),
   ("0.2.0", "worker checks always run under a timeout", wrap_checks_in_timeout),
   ("0.2.0", "pick up checks and build isolation the detector now finds", add_new_detections),
]


def pending(config):
   current = version_tuple(config.get("flow_version", "0"))
   return [entry for entry in MIGRATIONS if version_tuple(entry[0]) > current]


def migrate(cwd, apply=False):
   project_file = find_project_file(cwd)

   if project_file is None:
      return {"status": "no-project-file", "next": "run tf init"}

   root = project_file.parent
   config = read_json(project_file)
   original_version = config.get("flow_version", "none")
   steps = pending(config)
   notes = []

   for version, reason, step in steps:
      for note in step(config, root):
         notes.append(f"{version} {reason}: {note}")

   latest = plugin_version()
   is_current = version_tuple(config.get("flow_version", "0")) >= version_tuple(latest)

   advice = advisories(root)

   if is_current and not notes:
      return {"status": "current", "version": latest, "advisories": advice}

   config["flow_version"] = latest

   if apply:
      Path(project_file).write_text(json.dumps(config, indent=3) + "\n", encoding="utf-8")

   status = "applied" if apply else "pending"
   return {"status": status, "from": original_version, "to": latest, "changes": notes, "advisories": advice, "file": str(project_file)}
