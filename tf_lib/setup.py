import json
import re
from pathlib import Path

from tf_lib.core import VALID_COLOURS, TfError
from tf_lib.profile import PLUGIN_ROOT, PROJECT_FILE, read_json

FORBID_LINE = re.compile(r"\b(never|do not|don't|must not|maintainer[- ]only)\b", re.I)
GUARDED_FILES = ("CHANGELOG.md", "changelog.json")
READ_FIRST_CANDIDATES = ("CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "docs/gotchas.md", "docs/ARCHITECTURE.md")


def plugin_version():
   return read_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")["version"]


def version_tuple(text):
   return tuple(int(part) for part in re.findall(r"\d+", text or "0")[:3])


def npm_checks(root):
   package_file = root / "package.json"

   if not package_file.is_file():
      return []

   scripts = json.loads(package_file.read_text(encoding="utf-8")).get("scripts", {})
   checks = []

   if "test" in scripts:
      checks.append({"name": "unit", "run": "timeout 600 npm test"})

   if "typecheck" in scripts:
      checks.append({"name": "typecheck", "run": "timeout 300 npm run typecheck"})

   if "build" in scripts:
      checks.append({"name": "build", "run": "timeout 600 npm run build"})

   return checks


def cargo_manifest(root):
   for candidate in ("Cargo.toml", "src-tauri/Cargo.toml"):
      if (root / candidate).is_file():
         return candidate

   return None


def makefile_targets(root):
   makefile = root / "Makefile"

   if not makefile.is_file():
      return set()

   pattern = re.compile(r"^([A-Za-z0-9_.-]+):", re.M)
   return set(pattern.findall(makefile.read_text(encoding="utf-8", errors="replace")))


def forbidden_paths(root):
   rules = root / "CLAUDE.md"

   if not rules.is_file():
      return []

   found = set()

   for line in rules.read_text(encoding="utf-8", errors="replace").splitlines():
      if not FORBID_LINE.search(line):
         continue

      for guarded in GUARDED_FILES:
         if guarded in line:
            found.add(guarded)

   return sorted(found)


def uses_pytest(root):
   pyproject = root / "pyproject.toml"
   configured = pyproject.is_file() and "[tool.pytest" in pyproject.read_text(encoding="utf-8", errors="replace")
   has_config_file = any((root / name).is_file() for name in ("pytest.ini", "conftest.py", "tests/conftest.py"))
   in_requirements = any(requirements_name_pytest(path) for path in root.glob("requirements*.txt"))
   return configured or has_config_file or in_requirements


def requirements_name_pytest(path):
   text = path.read_text(encoding="utf-8", errors="replace")
   return re.search(r"^\s*pytest\b", text, re.M | re.I) is not None


def python_check(root):
   if uses_pytest(root):
      return "timeout 600 python3 -m pytest -q"

   return "timeout 600 python3 -m unittest discover -s tests"


def detect(root):
   root = Path(root)
   checks = npm_checks(root)
   manifest = cargo_manifest(root)
   targets = makefile_targets(root)

   if manifest:
      suffix = "" if manifest == "Cargo.toml" else f" --manifest-path {manifest}"
      checks.append({"name": "rust", "run": f"timeout 900 cargo test{suffix}"})

   if (root / "go.mod").is_file():
      checks.append({"name": "go", "run": "timeout 600 go test ./..."})

   has_python_tests = (root / "pyproject.toml").is_file() or (root / "tests").is_dir()

   if has_python_tests and not checks:
      checks.append({"name": "python", "run": python_check(root)})

   if "e2e" in targets:
      checks.append({"name": "e2e", "run": "timeout 1800 make e2e", "when": "ui", "lock": "e2e"})

   profile = {
      "flow_version": plugin_version(),
      "checks": checks,
      "read_first": [name for name in READ_FIRST_CANDIDATES if (root / name).is_file()],
      "land": {"mode": "apply"},
      "hooks": {"require_timeout": bool(checks), "ban_dashes": True},
   }

   if manifest:
      target = "{worktree}/" + str(Path(manifest).parent / "target").lstrip("./")
      profile["build"] = {"isolate": True, "env": {"CARGO_TARGET_DIR": target.replace("/./", "/")}}

   if "e2e" in targets:
      profile["locks"] = ["e2e"]

   guarded = forbidden_paths(root)

   if guarded:
      profile["forbid"] = {"commands": [], "paths": guarded}

   return profile


def keep_local(root):
   exclude = Path(root) / ".git" / "info" / "exclude"

   if not exclude.parent.is_dir():
      return False

   current = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""

   if PROJECT_FILE in current.split():
      return True

   with open(exclude, "a", encoding="utf-8") as handle:
      prefix = "" if current.endswith("\n") or not current else "\n"
      handle.write(f"{prefix}{PROJECT_FILE}\n")

   return True


def init(root, write=False, force=False, share=False):
   root = Path(root)
   target = root / PROJECT_FILE
   proposed = detect(root)

   if target.is_file() and not force:
      raise TfError(f"{PROJECT_FILE} already exists; run tf migrate to update it, or tf init --force to replace it")

   if not write:
      return {"would_write": str(target), "profile": proposed}

   target.write_text(json.dumps(proposed, indent=3) + "\n", encoding="utf-8")
   local_only = False if share else keep_local(root)
   return {"wrote": str(target), "local_only": local_only, "profile": proposed}


def missing_hubs(profile, tasks):
   names = {task["name"] for task in tasks}
   return [hub for hub in profile["hubs"] if hub not in names]


def create_hubs(cli, profile, tasks):
   created = []

   for hub in missing_hubs(profile, tasks):
      code, _, err = cli.run(["new", hub, "--main", "--no-group", "--agent", profile.get("agent", "claude")])

      if code != 0:
         raise TfError(f"creating hub '{hub}' exited {code}: {err.strip()}")

      created.append(hub)

   return created


def scaffold_categories(profile):
   scaffold = profile.get("scaffold") or {}
   return scaffold.get("categories") or []


def required_text(entry, key, where):
   value = entry.get(key) if isinstance(entry, dict) else None

   if not isinstance(value, str) or not value:
      raise TfError(f"scaffold {where} needs a non-empty '{key}'")

   return value


def validate_scaffold(profile):
   kinds = profile.get("kinds") or {}
   seen_categories = set()
   seen_sections = set()

   for category in scaffold_categories(profile):
      name = required_text(category, "name", "category")
      colour = category.get("color")

      if name in seen_categories:
         raise TfError(f"scaffold category '{name}' appears more than once")

      if colour not in VALID_COLOURS:
         raise TfError(f"scaffold category '{name}' colour '{colour}' is not a Termic group colour: {' '.join(VALID_COLOURS)}")

      seen_categories.add(name)

      for section in category.get("sections") or []:
         section_name = required_text(section, "name", f"section in category '{name}'")
         kind = section.get("kind")

         if section_name in seen_sections:
            raise TfError(f"scaffold section '{section_name}' appears more than once")

         if kind not in kinds:
            raise TfError(f"scaffold section '{section_name}' kind '{kind}' is not one of: {' '.join(kinds)}")

         seen_sections.add(section_name)


def task_group_name(task):
   group = task.get("group")

   if isinstance(group, dict):
      return group.get("name") or ""

   return group or ""


def missing_tabs(task, wanted, adopted=False):
   """A tab count carries no titles. Setup titles a new task's seed tab with its first profile
   tab, so the count covers that many profile tabs; a hand-made task's seed tab covers none."""
   if task is None:
      return list(wanted)

   tabs = task.get("tabs")

   if isinstance(tabs, list):
      titles = {tab.get("title") for tab in tabs}
      return [title for title in wanted if title not in titles]

   untitled_seed = 0 if adopted else 1
   covered = max((tabs or 0) - untitled_seed, 0)
   return list(wanted)[covered:]


def seed_tab_untitled(task, first_title):
   tabs = task.get("tabs")

   if not isinstance(tabs, list):
      return False

   return first_title not in {tab.get("title") for tab in tabs}


def scaffold_task_names(profile):
   names = set()

   for category in scaffold_categories(profile):
      for section in category.get("sections") or []:
         names.add(f"{section.get('kind')}: {section.get('name')}")

   return names


def group_colours(tasks):
   colours = {}

   for task in tasks:
      group = task.get("group")
      has_colour = isinstance(group, dict) and group.get("name") and group.get("color")

      if has_colour:
         colours.setdefault(group["name"], group["color"])

   return colours


def scaffold_rows(profile, tasks, adopted=()):
   """Each row is {"argv", "approve", "why"}. Rows with approve set restructure something that
   already exists, so tf setup --apply never runs them. Tasks named in adopted were created by
   an earlier apply, so their group row is still a create."""
   validate_scaffold(profile)
   existing = {task["name"]: task for task in tasks}
   colours = group_colours(tasks)
   agent = profile.get("agent", "claude")
   rows = []

   def add(argv, why=""):
      rows.append({"argv": argv, "approve": bool(why), "why": why})

   for category in scaffold_categories(profile):
      group_name = category["name"]
      known_colour = colours.get(group_name)
      recolours_group = known_colour is not None and known_colour != category["color"]

      for section in category.get("sections") or []:
         name = f"{section['kind']}: {section['name']}"
         task = existing.get(name)
         is_new = task is None
         wanted_tabs = list(section.get("tabs") or [])

         if is_new:
            add(["new", name, "--agent", agent])

         needs_group = is_new or task_group_name(task) != group_name

         if needs_group:
            group_argv = ["group", name, "--name", group_name, "--color", category["color"]]

            if recolours_group:
               add(group_argv, f"group '{group_name}' already exists with colour {known_colour}")
            elif not (is_new or name in adopted):
               add(group_argv, "regroups an existing task")
            else:
               add(group_argv)

         is_adopted = name in adopted
         retitles_seed = is_new or (is_adopted and wanted_tabs and seed_tab_untitled(task, wanted_tabs[0]))

         if retitles_seed and wanted_tabs:
            add(["tab", name, "--tab", "1", "--title", wanted_tabs.pop(0)])

         for title in missing_tabs(task, wanted_tabs, is_adopted):
            add(["tab", name, "--title", title])

   return rows


def scaffold_plan(profile, tasks):
   """Rows are tf argv lists. Existing tasks may be full status rows (group dict, tabs list
   with titles) or tf snapshot rows (group name string, tabs count). A tab count carries no
   titles, so the first count tabs are assumed to be the profile's tabs in order, because a
   new task's first profile tab titles its seed tab instead of opening another."""
   return [row["argv"] for row in scaffold_rows(profile, tasks)]
