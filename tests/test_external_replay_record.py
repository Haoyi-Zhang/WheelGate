"""Offline consumer of the documented-API rehearsal; no installation or network."""
import hashlib
import json
from pathlib import Path
import unittest

from wheelgate.runner import canonical_contract_digest

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "results/external-input-qualified"


@unittest.skipUnless(RECORD.is_dir(), "Artifact-only original-wheel evidence is not staged with installed API tests")
class ExternalReplayRecord(unittest.TestCase):
    def load(self, name):
        return json.loads((RECORD / name).read_text(encoding="utf-8"))

    def test_unchanged_oracle_and_exact_declaration(self):
        before, after = self.load("undeclared-contract.json"), self.load("declared-contract.json")
        item = after["contracts"][0].pop("external_inputs")
        self.assertEqual(before, after)
        self.assertEqual(len(item), 1)
        self.assertEqual(set(item[0]), {"path", "sha256", "evidence"})
        self.assertEqual(len(before["contracts"][0]["code"].splitlines()), 4)
        self.assertEqual(item[0]["sha256"], hashlib.sha256((RECORD / "upstream-data.json").read_bytes()).hexdigest())

    def test_real_receipt_decisions_and_binding(self):
        summary = self.load("summary.json")
        self.assertTrue(summary["valid"])
        self.assertEqual(self.load("ordinary.json")["status"], "PASS")
        for prefix, expected in (("undeclared", "INVALID"), ("declared", "PASS")):
            receipt = self.load(prefix + "-receipt.json")
            self.assertEqual(receipt["status"], expected)
            self.assertEqual(receipt["sha256"], summary["wheel_sha256"])
            self.assertEqual(receipt["contract_sha256"], canonical_contract_digest(self.load(prefix + "-contract.json")))
            row = receipt["contracts"][0]
            self.assertEqual(row["status"], expected)
            if prefix == "undeclared":
                self.assertEqual(row["operation_status"], "PASS")
                self.assertTrue(any(r["classification"] == "external-file" for r in row["file_footprint"]["violations"]))
            else:
                self.assertEqual(row["file_footprint"]["violations"], [])
                self.assertTrue(any(r["classification"] == "declared-external-input" for r in row["file_footprint"]["accesses"]))
                self.assertTrue(all(r["satisfied"] for r in row["external_input_preflight"]))


if __name__ == "__main__": unittest.main()
