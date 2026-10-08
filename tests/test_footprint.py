"""Import-footprint validity checks and runner enrichment."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

from wheelgate.footprint import AccessRecorder, inspect_file_access, inspect_new_modules, normalize
from wheelgate.runner import _runtime_contract
from wheelgate.worker import evaluate


class FootprintClassification(unittest.TestCase):
    def classify(self, path, inventory, site=(), stdlib=(), allowed=("subject",)):
        name = "wheelgate_test_dynamic_module"
        before = set(sys.modules)
        sys.modules[name] = types.SimpleNamespace(__file__=str(path))
        try:
            with mock.patch("wheelgate.footprint.distribution_inventory", return_value=inventory), \
                 mock.patch("wheelgate.footprint._roots", return_value=(tuple(site), tuple(stdlib))):
                return inspect_new_modules(before, list(allowed))
        finally:
            sys.modules.pop(name, None)

    def test_declared_distribution(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "subject.py"; path.write_text("")
            report = self.classify(path, {path.resolve(): {"distribution":"Subject", "version":"1"}})
        self.assertEqual(report["modules"][0]["classification"], "declared-distribution")
        self.assertEqual(report["violations"], [])

    def test_undeclared_distribution(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "helper.py"; path.write_text("")
            report = self.classify(path, {path.resolve(): {"distribution":"Helper", "version":"1"}})
        self.assertEqual(report["modules"][0]["classification"], "undeclared-distribution")
        self.assertEqual(len(report["violations"]), 1)

    def test_stdlib(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); path = root / "standard.py"; path.write_text("")
            report = self.classify(path, {}, stdlib=(root.resolve(),))
        self.assertEqual(report["modules"][0]["classification"], "stdlib")
        self.assertEqual(report["violations"], [])

    def test_external_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "shadow.py"; path.write_text("")
            report = self.classify(path, {})
        self.assertEqual(report["modules"][0]["classification"], "external-file")
        self.assertEqual(len(report["violations"]), 1)

    def test_name_normalization(self):
        self.assertEqual(normalize("My_Package.Name"), "my-package-name")


class FileAccessClassification(unittest.TestCase):
    def classify(self, path, inventory, site=(), stdlib=(), allowed=("subject",)):
        with mock.patch("wheelgate.footprint.distribution_inventory", return_value=inventory), \
             mock.patch("wheelgate.footprint._roots", return_value=(tuple(site), tuple(stdlib))), \
             mock.patch("wheelgate.footprint.sys.prefix", "/__wheelgate_test_prefix__"):
            return inspect_file_access([pathlib.Path(path).resolve()], list(allowed))

    def test_declared_data_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "message.txt"; path.write_text("ok")
            report = self.classify(path, {path.resolve(): {"distribution":"Subject", "version":"1"}})
        self.assertEqual(report["accesses"][0]["classification"], "declared-distribution")
        self.assertEqual(report["violations"], [])

    def test_undeclared_distribution_data_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "message.txt"; path.write_text("ok")
            report = self.classify(path, {path.resolve(): {"distribution":"Helper", "version":"1"}})
        self.assertEqual(report["accesses"][0]["classification"], "undeclared-distribution")
        self.assertEqual(len(report["violations"]), 1)

    def test_unowned_site_data_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); path = root / "generated.json"; path.write_text("{}")
            report = self.classify(path, {}, site=(root.resolve(),))
        self.assertEqual(report["accesses"][0]["classification"], "unowned-installed-file")
        self.assertEqual(len(report["violations"]), 1)

    def test_external_data_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "settings.json"; path.write_text("{}")
            report = self.classify(path, {})
        self.assertEqual(report["accesses"][0]["classification"], "external-file")
        self.assertEqual(len(report["violations"]), 1)

    def test_access_recorder_ignores_writes_and_code(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            data = root / "data.json"
            code = root / "module.py"
            recorder = AccessRecorder(); recorder.start()
            data.write_text("{}", encoding="utf-8")
            code.write_text("x=1\n", encoding="utf-8")
            self.assertEqual(data.read_text(encoding="utf-8"), "{}")
            self.assertIn("x=1", code.read_text(encoding="utf-8"))
            recorder.stop()
        self.assertIn(data.resolve(), recorder.paths)
        self.assertNotIn(code.resolve(), recorder.paths)



class FootprintOutcome(unittest.TestCase):
    def test_context_violation_invalidates_success(self):
        footprint = {"allowed_distributions": ["subject"], "module_count": 1,
                     "modules": [], "violations": [{"module":"helper"}]}
        contract = {"id":"x", "distribution":"subject", "_allowed_distributions":["subject"]}
        with mock.patch("wheelgate.worker.snapshot", return_value=set()), \
             mock.patch("wheelgate.worker.operation", return_value={"value":"ok"}), \
             mock.patch("wheelgate.worker.inspect_new_modules", return_value=footprint):
            result = evaluate(contract)
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["operation_status"], "PASS")

    def test_declared_footprint_keeps_success(self):
        footprint = {"allowed_distributions": ["subject"], "module_count": 1,
                     "modules": [], "violations": []}
        contract = {"id":"x", "distribution":"subject", "_allowed_distributions":["subject"]}
        with mock.patch("wheelgate.worker.snapshot", return_value=set()), \
             mock.patch("wheelgate.worker.operation", return_value={"value":"ok"}), \
             mock.patch("wheelgate.worker.inspect_new_modules", return_value=footprint):
            result = evaluate(contract)
        self.assertEqual(result["status"], "PASS")


class RunnerEnrichment(unittest.TestCase):
    def test_target_and_profile_prerequisites_are_allowed(self):
        contract = {"distribution":"subject"}
        spec = {"profile_dependencies":{"render":[
            {"distribution":"helper", "version":"1", "evidence":"README"}
        ]}}
        enriched = _runtime_contract(contract, spec, "render", {"name":"Subject", "version":"1"})
        self.assertEqual(enriched["_allowed_distributions"], ["Subject", "helper"])
        self.assertNotIn("_allowed_distributions", contract)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class ReceiptBinding(unittest.TestCase):
    def test_canonical_contract_digest_stable(self):
        from wheelgate.runner import canonical_contract_digest
        a={"schema":1,"contracts":[{"id":"x","kind":"import","distribution":"d","modules":["m"],"evidence":"e"}]}
        b={"contracts":a["contracts"],"schema":1}
        self.assertEqual(canonical_contract_digest(a), canonical_contract_digest(b))
