"""Host-independent admission rules for contract paths, not path rebasing."""
from __future__ import annotations


def resource_parts(value: str) -> tuple[str, ...]:
    """Require an explicit POSIX-relative file path on every supported host."""
    if not isinstance(value, str) or not value or any(c in value for c in "\\:\x00"):
        raise ValueError("Resource must be a POSIX package-relative file path")
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Resource must have nonempty, non-traversing file components")
    return parts


def command_basename(value: str) -> str:
    """Reject both separator styles and Windows drive/stream syntax everywhere."""
    if (not isinstance(value, str) or not value.strip() or value in {".", ".."}
            or any(c in value for c in "/\\:\x00")):
        raise ValueError("CLI must be an installed script basename")
    return value
