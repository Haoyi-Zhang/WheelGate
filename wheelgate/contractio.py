"""Strict JSON loading and validation of both accepted contract schemas.

Schema 1 remains accepted, with the same field and assertion applicability
checks as schema 2. Dependency guards use literal installed versions;
it is not a general PEP 508 resolver or an oracle inference mechanism.
"""
from __future__ import annotations

import json
import keyword
import pathlib
import re
from typing import Any

_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*\Z")
_COMMON = {"id", "kind", "distribution", "version", "modules", "evidence", "profiles", "timeout"}
_FIELDS = {
    "import": set(),
    "call": {"target", "args", "kwargs", "equals", "contains"},
    "resource": {"package", "resource", "format", "equals", "contains"},
    "entrypoint": {"group", "name", "invoke", "args", "kwargs", "equals", "contains"},
    "cli": {"command", "args", "stdin", "returncode", "equals", "contains"},
    "script": {"code"},
}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError(f"Non-finite JSON number: {value}")


def loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)


def load(path: pathlib.Path | str) -> dict[str, Any]:
    value = loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Contract document must be a JSON object")
    return value


def dotted_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and all(
        part.isidentifier() and not keyword.iskeyword(part) for part in value.split(".")
    )


def normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def validate_v2(spec: dict[str, Any]) -> None:
    """Strict validation for schemas 1 and 2, after the shared basic checks."""
    unknown = set(spec) - {"schema", "contracts", "profile_dependencies"}
    if unknown:
        raise ValueError(f"Unknown document fields: {sorted(unknown)}")
    try:
        json.dumps(spec, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("Contract values must be finite JSON values") from exc
    for contract in spec["contracts"]:
        kind = contract["kind"]
        unknown = set(contract) - _COMMON - _FIELDS[kind]
        if unknown:
            raise ValueError(f"{contract['id']}: fields not supported by {kind}: {sorted(unknown)}")
        if not contract["id"].strip():
            raise ValueError("Contract identifier cannot be whitespace")
        if not _NAME.fullmatch(contract["distribution"]):
            raise ValueError("Invalid distribution name")
        if "version" in contract and (
            not isinstance(contract["version"], str) or not _VERSION.fullmatch(contract["version"])
        ):
            raise ValueError("version must be a literal installed metadata version")
        if not all(dotted_identifier(module) for module in contract["modules"]):
            raise ValueError("Concrete anchors must be conventional dotted module identifiers")
        if len(set(contract["modules"])) != len(contract["modules"]):
            raise ValueError("Duplicate module anchor")
        if "kwargs" in contract and not all(isinstance(key, str) for key in contract["kwargs"]):
            raise ValueError("kwargs keys must be strings")
        if kind == "call":
            parts = contract["target"].split(":")
            if len(parts) != 2 or not all(dotted_identifier(part) for part in parts):
                raise ValueError("Call target must be module:attribute, with dotted identifiers")
        elif kind == "resource":
            if not dotted_identifier(contract["package"]):
                raise ValueError("Invalid resource package")
            if not isinstance(contract.get("format", "text"), str) or contract.get("format", "text") not in {"text", "json"}:
                raise ValueError("Resource format must be text or json")
            if contract["resource"] in {".", ""} or contract["resource"].endswith("/"):
                raise ValueError("A resource file path is required")
        elif kind == "entrypoint":
            if type(contract.get("invoke", False)) is not bool:
                raise ValueError("invoke must be a boolean")
            if not contract.get("invoke", False) and set(contract) & {"equals", "contains", "args", "kwargs"}:
                raise ValueError("An entrypoint return-value assertion requires invoke=true")
        elif kind == "cli":
            if any(not isinstance(arg, str) for arg in contract.get("args", [])):
                raise ValueError("CLI arguments must be strings")
            if not isinstance(contract.get("stdin", ""), str):
                raise ValueError("CLI stdin must be text")
            if type(contract.get("returncode", 0)) is not int:
                raise ValueError("CLI returncode must be an integer")
            if "equals" in contract and not isinstance(contract["equals"], str):
                raise ValueError("CLI stdout equality must compare text")
            if "contains" in contract and not isinstance(contract["contains"], str):
                raise ValueError("CLI stdout containment must compare text")
        elif kind == "script":
            try:
                compile(contract["code"], "<consumer-contract>", "exec")
            except (SyntaxError, ValueError) as exc:
                raise ValueError("Invalid consumer script syntax") from exc

    profiles = spec.get("profile_dependencies", {})
    if not isinstance(profiles, dict):
        raise ValueError("profile_dependencies must be an object")
    active_names = {p for c in spec["contracts"] for p in c.get("profiles", ["base"])}
    for profile, requirements in profiles.items():
        if not isinstance(profile, str) or not profile.strip() or profile not in active_names:
            raise ValueError("Dependency profile must activate at least one contract")
        if not isinstance(requirements, list):
            raise ValueError("Each dependency profile must be a list")
        seen: set[str] = set()
        for requirement in requirements:
            if not isinstance(requirement, dict) or set(requirement) != {"distribution", "version", "evidence"}:
                raise ValueError("Each dependency needs distribution, literal version, and evidence")
            name = requirement["distribution"]
            version = requirement["version"]
            if not isinstance(name, str) or not _NAME.fullmatch(name):
                raise ValueError("Invalid prerequisite distribution")
            if not isinstance(version, str) or not _VERSION.fullmatch(version):
                raise ValueError("Prerequisite version must be literal, not a range")
            if not isinstance(requirement["evidence"], str) or not requirement["evidence"].strip():
                raise ValueError("Prerequisite evidence is required")
            normalized = normalized_name(name)
            if normalized in seen:
                raise ValueError("Duplicate prerequisite distribution")
            seen.add(normalized)
