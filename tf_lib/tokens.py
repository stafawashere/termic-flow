import json
from pathlib import Path

USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def find_transcript(session_id):
   matches = list((Path.home() / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
   return matches[0] if matches else None


def count_tokens(path):
   totals = dict.fromkeys(USAGE_KEYS, 0)
   seen_messages = set()

   with open(path, encoding="utf-8") as handle:
      for line in handle:
         try:
            entry = json.loads(line)
         except json.JSONDecodeError:
            continue

         message = entry.get("message") or {}
         usage = message.get("usage")
         is_assistant = entry.get("type") == "assistant" and usage
         message_id = message.get("id")

         if not is_assistant or message_id in seen_messages:
            continue

         seen_messages.add(message_id)

         for key in USAGE_KEYS:
            totals[key] += usage.get(key) or 0

   totals["turns"] = len(seen_messages)
   totals["billed_equivalent"] = (
      totals["input_tokens"]
      + totals["cache_creation_input_tokens"]
      + totals["output_tokens"]
   )
   return totals
