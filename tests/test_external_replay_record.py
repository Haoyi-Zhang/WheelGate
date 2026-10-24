"""Offline consumer of the documented-API rehearsal; no installation or network."""
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from wheelgate import contractio
from wheelgate.runner import canonical_contract_digest

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "results/external-input-qualified"


def archived_contract_digest(spec):
    """Check retained JSON identity, not admissibility on this execution host.

    Match runner.canonical_contract_digest's encoding, preserving path strings
    and code verbatim. This offline checksum neither validates nor executes an
    archived contract and must not replace the runner's validated input digest.
    """
    encoded = json.dumps(spec, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ArchivedContractIntegrity(unittest.TestCase):
    def specification(self, path):
        return {"schema": 2, "contracts": [{
            "id": "data", "kind": "script", "code": "assert True",
            "distribution": "subject", "modules": ["subject"],
            "evidence": "reviewed consumer specification",
            "external_inputs": [{"path": path, "sha256": "a" * 64,
                                 "evidence": "reviewed data"}]}]}

    def test_known_canonical_utf8_encoding_and_key_order(self):
        spec = {"z": 1.0, "path": r"C:\archive\data.json", "label": "caf\u00e9"}
        canonical = '{"label":"caf\u00e9","path":"C:\\\\archive\\\\data.json","z":1.0}'.encode("utf-8")
        expected = hashlib.sha256(canonical).hexdigest()
        self.assertEqual(archived_contract_digest(spec), expected)
        self.assertEqual(archived_contract_digest(dict(reversed(list(spec.items())))), expected)

    def test_both_archived_path_flavours_remain_literal_and_unmodified(self):
        digests = []
        for path in (r"C:\archive\data.json", "/archive/data.json"):
            spec = self.specification(path)
            before = copy.deepcopy(spec)
            with patch("wheelgate.runner.validate", side_effect=AssertionError("not an execution request")):
                digests.append(archived_contract_digest(spec))
            self.assertEqual(spec, before)
        self.assertNotEqual(*digests)

    def test_archive_encoding_matches_validated_native_contract(self):
        spec = self.specification(str((ROOT / "reviewed-data.json").resolve()))
        self.assertEqual(archived_contract_digest(spec), canonical_contract_digest(spec))

    def test_tampered_path_hash_evidence_or_oracle_changes_binding(self):
        spec = self.specification(r"C:\archive\data.json")
        expected = archived_contract_digest(spec)
        for field, value in (("path", "C:/archive/data.json"),
                             ("sha256", "b" * 64), ("evidence", "different review"),
                             ("code", "assert False")):
            altered = copy.deepcopy(spec)
            row = altered["contracts"][0]
            (row if field == "code" else row["external_inputs"][0])[field] = value
            with self.subTest(field=field):
                self.assertNotEqual(archived_contract_digest(altered), expected)

    def test_archive_encoding_rejects_nonfinite_json(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                archived_contract_digest({"value": value})


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
            # A retained Windows run is evidence, not a Linux execution request.
            digest = archived_contract_digest(self.load(prefix + "-contract.json"))
            self.assertEqual(receipt["contract_sha256"], digest)
            self.assertEqual(summary["contract_hashes"][prefix], digest)
            row = receipt["contracts"][0]
            self.assertEqual(row["status"], expected)
            if prefix == "undeclared":
                self.assertEqual(row["operation_status"], "PASS")
                self.assertTrue(any(r["classification"] == "external-file" for r in row["file_footprint"]["violations"]))
            else:
                self.assertEqual(row["file_footprint"]["violations"], [])
                self.assertTrue(any(r["classification"] == "declared-external-input" for r in row["file_footprint"]["accesses"]))
                self.assertTrue(all(r["satisfied"] for r in row["external_input_preflight"]))

    def test_windows_archive_integrity_under_posix_execution_policy(self):
        spec = self.load("declared-contract.json")
        path = spec["contracts"][0]["external_inputs"][0]["path"]
        self.assertTrue(PureWindowsPath(path).is_absolute())
        self.assertFalse(PurePosixPath(path).is_absolute())
        self.assertTrue(self.load("summary.json")["platform"].startswith("Windows-"))
        # Model only POSIX admission rules; this is not a Linux package replay.
        with patch.object(contractio, "pathlib", SimpleNamespace(Path=PurePosixPath)):
            with self.assertRaisesRegex(ValueError, "absolute on the execution host"):
                canonical_contract_digest(spec)
            self.test_real_receipt_decisions_and_binding()


if __name__ == "__main__": unittest.main()
