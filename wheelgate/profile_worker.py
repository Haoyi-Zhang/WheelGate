"""Check explicit literal-version prerequisites without importing subject code."""
from __future__ import annotations

import importlib.metadata as metadata
import json
import pathlib
import sys


def inspect(requirements: list[dict]) -> dict:
    records = []
    for requirement in requirements:
        try:
            observed = metadata.version(requirement["distribution"])
        except metadata.PackageNotFoundError:
            observed = None
        records.append({"distribution": requirement["distribution"],
                        "expected_version": requirement["version"],
                        "observed_version": observed,
                        "satisfied": observed == requirement["version"]})
    return {"status": "READY" if all(r["satisfied"] for r in records) else "BLOCKED",
            "requirements": records}


def main() -> int:
    requirements = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    result = inspect(requirements)
    print("WHEELGATE_PROFILE=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
