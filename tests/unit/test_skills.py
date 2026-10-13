import re
import unittest

from tf_lib.main import build_parser
from tf_lib.profile import PLUGIN_ROOT
from tf_lib.prompts import template_for

TF_TAB_CALL = re.compile(r"`tf tab \S+ ([a-z-]+)")
TF_CALL = re.compile(r"(?:`|! )tf ([a-z-]+)")
BODY_LINE_CAP = 45


def subcommands():
   parser = build_parser()
   action = next(a for a in parser._actions if a.dest == "command")
   return set(action.choices)


class Skills(unittest.TestCase):
   def docs(self):
      return list((PLUGIN_ROOT / "skills").rglob("*.md")) + list((PLUGIN_ROOT / "agents").glob("*.md"))

   def test_every_tf_subcommand_named_in_docs_exists(self):
      known = subcommands()

      for path in self.docs():
         for name in TF_CALL.findall(path.read_text(encoding="utf-8")):
            self.assertIn(name, known, f"{path.relative_to(PLUGIN_ROOT)} names tf {name}")

   def test_every_tf_tab_role_in_docs_has_a_template(self):
      for path in self.docs():
         for role in TF_TAB_CALL.findall(path.read_text(encoding="utf-8")):
            template = PLUGIN_ROOT / "templates" / f"{template_for(role)}.txt"
            self.assertTrue(template.is_file(), f"{path.relative_to(PLUGIN_ROOT)} opens a {role} tab with no template")

   def test_skill_bodies_stay_short(self):
      for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md"):
         body = path.read_text(encoding="utf-8").split("---", 2)[2]
         self.assertLessEqual(len(body.strip().splitlines()), BODY_LINE_CAP, path.parent.name)
