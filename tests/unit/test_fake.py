import json
import unittest

from tests.helpers import ROOT, FakeTermic

HELP = json.loads((ROOT / "tests" / "fake" / "help.json").read_text(encoding="utf-8"))


class FakeCoversHelp(FakeTermic):
   def test_fake_knows_every_verb_in_help_json(self):
      import subprocess

      for command in HELP["commands"]:
         argv = command["name"].split()
         run = subprocess.run([str(ROOT / "tests" / "fake" / "termic-cli"), *argv, "x", "--json"], capture_output=True, text=True, env=self.env, input="")
         self.assertNotIn("unknown verb", run.stderr, command["name"])
