import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import FakeTermic, make_task
from tf_lib import migrate, setup
from tf_lib.core import TfError


def build_repo(root, claude_rules="Never edit CHANGELOG.md; the maintainer writes it.\n"):
   (root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest", "build": "vite build"}}))
   (root / "src-tauri").mkdir()
   (root / "src-tauri" / "Cargo.toml").write_text("[package]\nname = \"demo\"\n")
   (root / "Makefile").write_text("e2e:\n\techo run\n")
   (root / "CLAUDE.md").write_text(claude_rules)
   subprocess.run(["git", "init", "-q", str(root)], check=True)


class Detection(unittest.TestCase):
   def setUp(self):
      self.temp = tempfile.TemporaryDirectory()
      self.root = Path(self.temp.name)
      build_repo(self.root)

   def tearDown(self):
      self.temp.cleanup()

   def test_detects_checks_isolation_lock_and_guarded_files(self):
      profile = setup.detect(self.root)
      runs = {check["name"]: check["run"] for check in profile["checks"]}
      self.assertEqual(runs["unit"], "timeout 600 npm test")
      self.assertEqual(runs["rust"], "timeout 900 cargo test --manifest-path src-tauri/Cargo.toml")
      self.assertEqual(profile["build"]["env"]["CARGO_TARGET_DIR"], "{worktree}/src-tauri/target")
      self.assertEqual(profile["locks"], ["e2e"])
      self.assertEqual(profile["forbid"]["paths"], ["CHANGELOG.md"])
      self.assertTrue(profile["hooks"]["require_timeout"])

   def test_python_check_uses_the_runner_the_project_configures(self):
      python_only = self.root / "py"
      (python_only / "tests").mkdir(parents=True)
      plain = setup.detect(python_only)["checks"][0]["run"]
      self.assertEqual(plain, "timeout 600 python3 -m unittest discover -s tests")

      (python_only / "tests" / "conftest.py").write_text("")
      configured = setup.detect(python_only)["checks"][0]["run"]
      self.assertEqual(configured, "timeout 600 python3 -m " + "py" + "test -q")

   def test_pytest_named_in_a_requirements_file_selects_pytest(self):
      python_only = self.root / "py"
      (python_only / "tests").mkdir(parents=True)
      (python_only / "requirements-dev.txt").write_text("black==24.1\n" + "py" + "test>=8\n")
      configured = setup.detect(python_only)["checks"][0]["run"]
      self.assertEqual(configured, "timeout 600 python3 -m " + "py" + "test -q")

      (python_only / "requirements-dev.txt").write_text("black==24.1\nrequests\n")
      plain = setup.detect(python_only)["checks"][0]["run"]
      self.assertEqual(plain, "timeout 600 python3 -m unittest discover -s tests")

   def test_a_changelog_mention_without_a_prohibition_is_not_guarded(self):
      (self.root / "CLAUDE.md").write_text("See CHANGELOG.md for history.\n")
      self.assertNotIn("forbid", setup.detect(self.root))

   def test_init_previews_by_default_then_writes_and_keeps_the_file_local(self):
      preview = setup.init(self.root)
      self.assertFalse((self.root / ".termic-flow.json").exists())
      self.assertIn("would_write", preview)

      setup.init(self.root, write=True)
      setup.init(self.root, write=True, force=True)
      self.assertTrue((self.root / ".termic-flow.json").is_file())
      excluded = (self.root / ".git" / "info" / "exclude").read_text().split()
      self.assertEqual(excluded.count(".termic-flow.json"), 1)

   def test_init_refuses_to_overwrite(self):
      setup.init(self.root, write=True)

      with self.assertRaises(TfError):
         setup.init(self.root, write=True)


class Migration(unittest.TestCase):
   def setUp(self):
      self.temp = tempfile.TemporaryDirectory()
      self.root = Path(self.temp.name)
      build_repo(self.root)
      old = {"kinds": {"ops": "gray"}, "checks": [{"name": "unit", "run": "npm test"}]}
      (self.root / ".termic-flow.json").write_text(json.dumps(old))

   def tearDown(self):
      self.temp.cleanup()

   def stored(self):
      return json.loads((self.root / ".termic-flow.json").read_text())

   def test_dry_run_lists_changes_without_writing(self):
      result = migrate.migrate(self.root)
      self.assertEqual(result["status"], "pending")
      self.assertEqual(result["from"], "none")
      self.assertTrue(any("gray" in note for note in result["changes"]))
      self.assertEqual(self.stored()["kinds"]["ops"], "gray")

   def test_apply_fixes_bumps_version_and_is_idempotent(self):
      migrate.migrate(self.root, apply=True)
      stored = self.stored()
      self.assertEqual(stored["kinds"]["ops"], "pink")
      self.assertEqual(stored["checks"][0]["run"], "timeout 600 npm test")
      self.assertIn("rust", {check["name"] for check in stored["checks"]})
      self.assertEqual(stored["flow_version"], setup.plugin_version())
      self.assertEqual(migrate.migrate(self.root)["status"], "current")

   def test_legacy_project_skills_are_reported_not_touched(self):
      legacy = self.root / ".claude" / "skills" / "termic-driver"
      legacy.mkdir(parents=True)
      (legacy / "SKILL.md").write_text("old")
      result = migrate.migrate(self.root, apply=True)
      self.assertTrue(any("termic-driver" in note for note in result["advisories"]))
      self.assertEqual((legacy / "SKILL.md").read_text(), "old")


class Hubs(FakeTermic):
   def test_creates_only_missing_hubs_on_the_main_checkout(self):
      self.set_world({"tasks": [make_task("main", "00000000-0000-4000-8000-0000000000aa", is_main_checkout=True)]})
      result = json.loads(self.tf("hubs", "--create").stdout)
      self.assertEqual(result["created"], ["plan", "design", "triage"])
      created = self.calls_of("new")
      self.assertEqual(len(created), 3)
      self.assertTrue(all("--main" in call and "--no-group" in call for call in created))
