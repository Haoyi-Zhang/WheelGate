"""Read bundle-relative evidence paths written on Windows or POSIX.

Only retained file references are normalized. Historical process argv, origins,
and absolute temporary paths remain observations, never executable replay input.
"""
from __future__ import annotations

from pathlib import Path


def relative_parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or any(c in value for c in ":\x00"):
        raise ValueError("Evidence reference must be a relative bundle path")
    parts = tuple(value.replace("\\", "/").split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Evidence reference has an absolute, empty, or traversing component")
    return parts


def resolve_relative(base: Path, value: str) -> Path:
    base = base.resolve()
    path = base.joinpath(*relative_parts(value)).resolve()
    if not path.is_relative_to(base):
        raise ValueError("Evidence reference resolves outside its bundle directory")
    return path


def resolve_result_path(root: Path, record_file: Path, value: str) -> Path:
    """Support artifact-relative `results/...` and record-directory-relative refs."""
    root = root.resolve()
    parent = record_file.resolve().parent
    if not parent.is_relative_to(root):
        raise ValueError("Evidence record must be inside the artifact bundle")
    parts = relative_parts(value)
    return resolve_relative(root if parts[0] == "results" else parent, value)
