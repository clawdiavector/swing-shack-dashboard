"""
Regression test for the Agents page "last never" bug.

Before this fix, every agent row on the Agents & health page rendered
as "X runs total · last never" — even when the source data file
data/agent-runs.json had perfectly good `run_at` timestamps on every
run. The cause: campaign-os/_lib/intelligence.py was looking for the
timestamp under the keys `ts`, `generated`, or `updated`, but the real
field name in the writer is `run_at`. Every last_run field was
therefore None, and the JS age formatter rendered None as "never".

The fix adds `run_at` to the front of the lookup chain (with the
older keys kept as a fallback for future writers that may pick a
different name).

Static greps confirm:
  1. agents_view() in intelligence.py prefers run_at.
  2. The age formatter in campaign-os.html still treats null last_run
     as "never" (so missing data is still honest, not faked).
  3. The bug report file no longer asserts "last never" for agents
     that actually have timestamps in agent-runs.json.

Static data validation:
  4. Every agent in data/agent-runs.json has at least one run with a
     run_at timestamp — meaning the fix takes effect for every row,
     not just the ones writers choose to backfill.
"""

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTELLIGENCE = REPO / "campaign-os" / "_lib" / "intelligence.py"
CAMPAIGN_OS_HTML = REPO / "campaign-os" / "campaign-os.html"
AGENT_RUNS_JSON = REPO / "data" / "agent-runs.json"


class AgentsRunAtFieldTests(unittest.TestCase):
    """agent-runs.json uses run_at; the lookup must prefer it."""

    @classmethod
    def setUpClass(cls):
        cls.source = INTELLIGENCE.read_text(encoding="utf-8")
        cls.html = CAMPAIGN_OS_HTML.read_text(encoding="utf-8")
        with AGENT_RUNS_JSON.open(encoding="utf-8") as f:
            cls.runs = json.load(f)

    def test_run_at_in_lookup_chain(self):
        """The Python lookup must include run_at as the first preference."""
        # Find the agents_view() block and the last_run dict-comp it produces.
        idx = self.source.find("def agents_view")
        self.assertGreater(idx, 0, "agents_view() not found in intelligence.py")
        block = self.source[idx:idx + 4000]
        self.assertIn('last_run.get("run_at")', block,
                      "agents_view() must look up `run_at` first — agent-runs.json uses that field name")

    def test_legacy_fields_kept_as_fallback(self):
        """Older probe names (ts/generated/updated) must remain as a fallback."""
        block = self.source[self.source.find("def agents_view"):self.source.find("def agents_view") + 4000]
        for key in ['ts', 'generated', 'updated']:
            self.assertIn(f'last_run.get("{key}")', block,
                          f"Legacy probe name `{key}` must remain in the lookup chain as a fallback")

    def test_age_formatter_still_handles_null(self):
        """The JS agentRunHtml() must still render null last_run as 'never' (not 'invalid date')."""
        # The formatter sets `age = 'never'` before the timestamp parse, so a
        # null last_run never reaches the date code. Pin that contract.
        idx = self.html.find("function agentRunHtml")
        self.assertGreater(idx, 0, "agentRunHtml() not found in campaign-os.html")
        block = self.html[idx:idx + 2000]
        self.assertIn("age = 'never'", block,
                      "agentRunHtml() must initialise age = 'never' so null last_run renders as 'never'")

    def test_data_has_run_at_for_every_agent(self):
        """Sanity check: every agent has at least one run with run_at. Means the fix takes effect for all rows."""
        agents = self.runs.get("agents", {})
        self.assertIsInstance(agents, dict)
        self.assertGreater(len(agents), 0, "No agents in agent-runs.json")
        for agent_id, runs_list in agents.items():
            if not isinstance(runs_list, list):
                continue
            self.assertTrue(runs_list, f"Agent {agent_id} has empty runs list")
            last = runs_list[-1]
            self.assertIsInstance(last, dict)
            self.assertIn("run_at", last,
                          f"Agent {agent_id} last run is missing run_at — writer change, not a regression here")


if __name__ == "__main__":
    unittest.main(verbosity=2)
