import re

from tf_lib.core import TfError

STATUSES = ("pass", "fail", "blocked")
FIELDS = ("status", "checks", "changed", "risks", "next")
RED_PREFIX = "red_"
FIELD_LINE = re.compile(r"^(status|checks|changed|risks|next|failure):\s*(.*)$", re.M)
PAD_LINE = re.compile(r"^(\S+)\s{2,}(.+?)\s*$")
ROUND_SUFFIX = re.compile(r" r(\d+)$")

TEMPLATE = """# report: {task}

status: pass|fail|blocked
checks: <name>=<numeric exit code>, ... (numbers only, for example unit=0, build=0; phrase absence checks so success exits 0; an expected-fail check is written red_<name>=<non-zero>)
changed: <files changed count>
risks: <one line, or none>
next: <one line>
failure: <reasoning|environment|none>
"""


def parse_pad_list(text):
   pads = []

   for line in text.splitlines():
      match = PAD_LINE.match(line)

      if match:
         pads.append({"id": match.group(1), "title": match.group(2)})

   return pads


def report_round(title, task):
   prefix = f"report: {task}"

   if title == prefix:
      return 1

   suffix = ROUND_SUFFIX.fullmatch(title[len(prefix):]) if title.startswith(prefix) else None
   return int(suffix.group(1)) if suffix else None


def pick_latest_round(pads, task):
   rounds = [(report_round(pad["title"], task), pad["id"]) for pad in pads]
   tagged = [(number, pad_id) for number, pad_id in rounds if number is not None]

   if not tagged:
      raise TfError(f"no report pad found for task '{task}'")

   number, pad_id = max(tagged, key=lambda item: item[0])
   return {"pad": pad_id, "round": number}


def check_is_expected(name, code):
   is_expected_fail = name.startswith(RED_PREFIX)
   is_number = code.isascii() and code.isdigit()
   is_non_zero_number = is_number and int(code) != 0

   if is_expected_fail:
      return is_non_zero_number

   return code == "0"


def parse_report(text):
   found = {key: value.strip() for key, value in FIELD_LINE.findall(text)}
   missing = [field for field in FIELDS if field not in found]

   if missing:
      raise TfError(f"report is missing fields: {', '.join(missing)}")

   if found["status"] not in STATUSES:
      raise TfError(f"report status '{found['status']}' is not one of: {' '.join(STATUSES)}")

   checks = {}

   for item in filter(None, (part.strip() for part in found["checks"].split(","))):
      name, _, exit_code = item.partition("=")
      checks[name.strip()] = exit_code.strip()

   claims_pass = found["status"] == "pass"
   bad_checks = [name for name, code in checks.items() if not check_is_expected(name, code)]

   if claims_pass and bad_checks:
      raise TfError(f"report says pass but a check is not as expected: {', '.join(bad_checks)}")

   found["checks"] = checks
   found.setdefault("failure", "none")
   return found
