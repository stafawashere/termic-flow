import unittest
from unittest import mock

from tf_lib import safety
from tf_lib.core import TfError


class RestructureVerbs(unittest.TestCase):
   def test_rename_and_group_need_approval(self):
      for verb in ("rename", "group"):
         self.assertIn(verb, safety.DESTRUCTIVE_VERBS)
         self.assertIn(verb, safety.NEEDS_APPROVAL)

   def test_unapproved_rename_of_an_existing_task_is_refused(self):
      task = {"id": "task-1", "name": "fix: thing"}

      with mock.patch.object(safety, "read_marker", return_value=None):
         with self.assertRaisesRegex(TfError, "tf approve task-1"):
            safety.gate_destructive("rename", task)

   def test_rename_names_an_existing_task_only_with_two_positionals(self):
      self.assertTrue(safety.targets_existing_task(["rename", "fix: thing", "fix: other"], "rename"))
      self.assertFalse(safety.targets_existing_task(["rename", "fix: other"], "rename"))

   def test_group_name_value_is_not_read_as_a_task(self):
      argv = ["group", "--name", "batch", "--color", "teal"]
      self.assertFalse(safety.targets_existing_task(argv, "group"))

      with self.assertRaises(TfError):
         safety.task_of(argv, "group")

   def test_group_with_a_task_targets_that_task(self):
      argv = ["group", "fix: thing", "--name", "batch"]
      self.assertTrue(safety.targets_existing_task(argv, "group"))
      self.assertEqual(safety.task_of(argv, "group"), "fix: thing")


if __name__ == "__main__":
   unittest.main()
