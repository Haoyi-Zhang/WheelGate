"""Bounded data exceptions: stable input identities, not code or directory grants."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wheelgate.footprint import external_input_receipt, inspect_file_access
from wheelgate.runner import canonical_contract_digest, validate
from wheelgate.worker import evaluate, _evaluate_console_child


def declaration(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "evidence": "reviewed external configuration"}


def specification(item):
    return {"schema": 2, "contracts": [{"id": "data", "kind": "script", "code": "assert True",
            "distribution": "subject", "modules": ["subject"], "evidence": "consumer specification",
            "external_inputs": [item]}]}


class ExternalInputPolicy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data.json"
        self.path.write_text('{"value": 1}', encoding="utf-8")
        self.item = declaration(self.path)

    def test_valid_declaration_changes_binding(self):
        spec = specification(self.item)
        validate(spec)
        without = copy.deepcopy(spec); del without["contracts"][0]["external_inputs"]
        self.assertNotEqual(canonical_contract_digest(spec), canonical_contract_digest(without))

    def test_schema_rejects_incomplete_relative_code_and_wildcard(self):
        for edit in ({"path": "relative.json"}, {"path": str(self.path.with_suffix('.py'))},
                     {"sha256": "bad"}, {"evidence": ""}, {"pattern": "*"}):
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                validate(specification({**self.item, **edit}))

    def test_schema_rejects_duplicate_canonical_path(self):
        spec = specification(self.item)
        spec["contracts"][0]["external_inputs"].append(dict(self.item))
        with self.assertRaises(ValueError): validate(spec)

    def test_exact_declared_file(self):
        report = inspect_file_access([self.path.resolve()], ["subject"], [self.item])
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["accesses"][0]["classification"], "declared-external-input")

    def test_equal_bytes_other_path_is_not_allowed(self):
        other = self.path.with_name("other.json"); other.write_bytes(self.path.read_bytes())
        report = inspect_file_access([other.resolve()], ["subject"], [self.item])
        self.assertEqual(len(report["violations"]), 1)

    def test_no_declaration_keeps_prior_external_policy(self):
        self.assertEqual(len(inspect_file_access([self.path.resolve()], ["subject"])["violations"]), 1)

    def test_digest_mismatch_is_not_allowed(self):
        self.path.write_text("changed")
        self.assertFalse(external_input_receipt([self.item])[0]["satisfied"])
        self.assertEqual(len(inspect_file_access([self.path.resolve()], ["subject"], [self.item])["violations"]), 1)

    def test_missing_file_and_directory_fail_preflight(self):
        self.path.unlink()
        self.assertFalse(external_input_receipt([self.item])[0]["satisfied"])
        self.path.mkdir()
        self.assertFalse(external_input_receipt([self.item])[0]["satisfied"])

    def test_cannot_override_installed_distribution(self):
        inventory = {self.path.resolve(): {"distribution": "other", "version": "1"}}
        with patch("wheelgate.footprint.distribution_inventory", return_value=inventory):
            report = inspect_file_access([self.path.resolve()], ["subject"], [self.item])
        self.assertEqual(report["accesses"][0]["classification"], "undeclared-distribution")
        self.assertEqual(len(report["violations"]), 1)

    def test_preflight_prevents_operation(self):
        self.path.write_text("changed")
        with patch("wheelgate.worker.operation") as operation:
            result = evaluate(specification(self.item)["contracts"][0])
        self.assertEqual(result["status"], "INVALID"); operation.assert_not_called()

    def test_success_with_declared_read(self):
        with patch("wheelgate.worker.operation", side_effect=lambda c: {"value": self.path.read_text()}):
            result = evaluate(specification(self.item)["contracts"][0])
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["external_input_preflight"][0]["satisfied"])

    def test_mutation_during_operation_invalidates_success(self):
        def operation(c):
            self.path.read_text(); self.path.write_text("changed"); return {"value": "correct"}
        with patch("wheelgate.worker.operation", side_effect=operation):
            result = evaluate(specification(self.item)["contracts"][0])
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["operation_status"], "PASS")

    def test_semantic_failure_remains_fail_with_context_warning(self):
        def operation(c):
            self.path.read_text(); self.path.write_text("changed"); raise AssertionError("oracle mismatch")
        with patch("wheelgate.worker.operation", side_effect=operation):
            result = evaluate(specification(self.item)["contracts"][0])
        self.assertEqual(result["status"], "FAIL"); self.assertIn("context_warning", result)

    def test_console_child_uses_same_data_policy(self):
        with patch("wheelgate.worker._console_operation", side_effect=lambda c, capture: {"value": self.path.read_text()}):
            result = _evaluate_console_child(specification(self.item)["contracts"][0])
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["external_input_preflight"][0]["satisfied"])

    def test_data_declaration_does_not_suppress_module_violation(self):
        footprint = {"modules": [], "violations": [{"module": "unowned_code"}]}
        with patch("wheelgate.worker.operation", return_value={"value": "correct"}), \
             patch("wheelgate.worker.inspect_new_modules", return_value=footprint):
            result = evaluate(specification(self.item)["contracts"][0])
        self.assertEqual(result["status"], "INVALID")


if __name__ == "__main__": unittest.main()
