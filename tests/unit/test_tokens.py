import json
import tempfile
import unittest

from tf_lib.tokens import count_tokens


def line(kind, message_id, **usage):
   return json.dumps({"type": kind, "message": {"id": message_id, "usage": usage}})


class Tokens(unittest.TestCase):
   def test_content_blocks_of_one_message_are_counted_once(self):
      rows = [
         line("assistant", "m1", input_tokens=10, output_tokens=5, cache_read_input_tokens=100),
         line("assistant", "m1", input_tokens=10, output_tokens=5, cache_read_input_tokens=100),
         line("assistant", "m2", input_tokens=1, output_tokens=2, cache_creation_input_tokens=7),
         line("user", "u1", input_tokens=999),
         "not json",
      ]

      with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
         handle.write("\n".join(rows))

      totals = count_tokens(handle.name)
      self.assertEqual(totals["turns"], 2)
      self.assertEqual(totals["input_tokens"], 11)
      self.assertEqual(totals["cache_read_input_tokens"], 100)
      self.assertEqual(totals["billed_equivalent"], 11 + 7 + 7)
