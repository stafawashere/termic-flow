# Contributing

- Python 3 standard library only. Indent with 3 spaces and use double quotes.
- Every behaviour change needs a test that fails without the change. Break the code, watch the test go red, then restore it.
- Fixtures must be synthetic. Use placeholders such as `acme.com`, `alice` and `/Users/u`, and never paste real CLI output from your machine.
- `tests/fake/help.json` is the Termic CLI's own `help --json`. Refresh it when Termic adds verbs, and keep the fake in step (`tests/unit/test_fake.py` checks this).
- No em dashes in user-visible text. The plugin's hook rejects them in pads and prompts.
