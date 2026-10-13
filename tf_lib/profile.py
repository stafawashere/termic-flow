import json
import os
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ".termic-flow.json"


def deep_merge(base, override):
   merged = dict(base)

   for key, value in override.items():
      both_dicts = isinstance(value, dict) and isinstance(merged.get(key), dict)

      if both_dicts:
         merged[key] = deep_merge(merged[key], value)
      else:
         merged[key] = value

   return merged


def read_json(path):
   with open(path, encoding="utf-8") as handle:
      return json.load(handle)


def user_config_dir():
   xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
   return Path(xdg) / "termic-flow"


def find_project_file(start):
   current = Path(start).resolve()

   for directory in [current, *current.parents]:
      candidate = directory / PROJECT_FILE

      if candidate.is_file():
         return candidate

   return None


def resolve_named_profile(project_data):
   name = project_data.get("extends")

   if not name:
      return {}

   bundled = PLUGIN_ROOT / "profiles" / f"{name}.json"
   user_owned = user_config_dir() / "profiles" / f"{name}.json"

   for candidate in (user_owned, bundled):
      if candidate.is_file():
         return read_json(candidate)

   raise SystemExit(f"tf: profile '{name}' named by {PROJECT_FILE} does not exist")


def load_profile(cwd=None):
   profile = read_json(PLUGIN_ROOT / "profiles" / "default.json")
   user_file = user_config_dir() / "profile.json"

   if user_file.is_file():
      profile = deep_merge(profile, read_json(user_file))

   project_file = find_project_file(cwd or os.getcwd())

   if project_file:
      project_data = read_json(project_file)
      profile = deep_merge(profile, resolve_named_profile(project_data))
      profile = deep_merge(profile, {k: v for k, v in project_data.items() if k != "extends"})
      profile["_project_file"] = str(project_file)

   return profile
