"""Paper-tool metadata regressions run in the dedicated plotting/tool test stage."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("native_encoding", ["cp936", "UTF-8"])
def test_metadata_command_uses_native_locale(monkeypatch, native_encoding):
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_paper.py"
    spec = importlib.util.spec_from_file_location("owned_paper_verifier", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(module.locale, "getencoding", lambda: native_encoding)

    def run(argv, **options):
        calls.append((argv, options))
        return SimpleNamespace(returncode=0, stdout="Pages: 12\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.command(["pdfinfo", "main.pdf"])
    assert result.returncode == 0
    assert calls[0][0] == ["pdfinfo", "main.pdf"]
    assert calls[0][1]["encoding"] == native_encoding
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
