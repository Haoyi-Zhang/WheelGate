"""Runtime dependency receipts for installed consumer operations.

The gate does not infer contracts from imports or file accesses.  It records
modules first loaded and non-code files first read while an already justified
consumer operation runs.  Concrete origins must belong to the selected
distribution, an explicitly declared profile prerequisite, or the Python
standard library.
"""
from __future__ import annotations

import importlib.metadata as metadata
import os
import pathlib
import re
import sys
import sysconfig
from typing import Any, Iterable

_CODE_SUFFIXES = {
    ".py",
    ".pyc",
    ".pyo",
    ".so",
    ".pyd",
    ".dll",
    ".dylib",
}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def snapshot() -> set[str]:
    return set(sys.modules)


def _resolved(value: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> pathlib.Path | None:
    try:
        return pathlib.Path(os.fsdecode(os.fspath(value))).resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _roots() -> tuple[tuple[pathlib.Path, ...], tuple[pathlib.Path, ...]]:
    paths = sysconfig.get_paths()
    site_roots: list[pathlib.Path] = []
    for key in ("purelib", "platlib"):
        root = _resolved(paths.get(key, ""))
        if root is not None and root not in site_roots:
            site_roots.append(root)
    stdlib_roots: list[pathlib.Path] = []
    for key in ("stdlib", "platstdlib"):
        root = _resolved(paths.get(key, ""))
        if root is not None and root not in stdlib_roots:
            stdlib_roots.append(root)
    # A base interpreter's third-party directory is not part of the stdlib,
    # even when a venv's sysconfig only reports its own site-packages roots.
    for root in stdlib_roots:
        for name in ('site-packages','dist-packages'):
            candidate = root / name
            if candidate not in site_roots:
                site_roots.append(candidate)
    return tuple(site_roots), tuple(stdlib_roots)


def _under(path: pathlib.Path, roots: tuple[pathlib.Path, ...]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def distribution_inventory() -> dict[pathlib.Path, dict[str, str]]:
    """Map installed RECORD paths to normalized distribution identities."""
    result: dict[pathlib.Path, dict[str, str]] = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if not name:
            continue
        identity = {"distribution": name, "version": dist.version}
        for entry in dist.files or ():
            path = _resolved(dist.locate_file(entry))
            if path is not None:
                result[path] = identity
    return result


def _classify_path(
    path: pathlib.Path,
    allowed: set[str],
    inventory: dict[pathlib.Path, dict[str, str]],
    site_roots: tuple[pathlib.Path, ...],
    stdlib_roots: tuple[pathlib.Path, ...],
    prefix: pathlib.Path,
) -> tuple[dict[str, str], bool]:
    row: dict[str, str] = {"origin": str(path)}
    owner = inventory.get(path)
    if owner is not None:
        row.update(owner)
        normalized = normalize(owner["distribution"])
        if normalized in allowed:
            row["classification"] = "declared-distribution"
            return row, False
        row["classification"] = "undeclared-distribution"
        return row, True
    if _under(path, site_roots):
        row["classification"] = "unowned-installed-file"
        return row, True
    if _under(path, stdlib_roots) and not _under(path, site_roots):
        row["classification"] = "stdlib"
        return row, False
    if (re.fullmatch(r"python\d+\.zip", path.name)
            and any(path.parent == root.parent for root in stdlib_roots)):
        row["classification"] = "stdlib-archive"
        return row, False
    if path.is_relative_to(prefix):
        # pyvenv.cfg may be consulted by the interpreter or tooling but is not
        # release-owned application data.
        if path == prefix / "pyvenv.cfg":
            row["classification"] = "environment-metadata"
            return row, False
        row["classification"] = "unowned-environment-file"
        return row, True
    row["classification"] = "external-file"
    return row, True


def _module_origin(module: Any) -> pathlib.Path | None:
    origin = getattr(module, "__file__", None)
    if not origin:
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
    if not origin or origin in {"built-in", "frozen"}:
        return None
    return _resolved(origin)


def inspect_new_modules(before: set[str], allowed_distributions: list[str]) -> dict[str, Any]:
    """Classify concrete module origins loaded after *before* was captured."""
    allowed = {normalize(name) for name in allowed_distributions}
    inventory = distribution_inventory()
    site_roots, stdlib_roots = _roots()
    prefix = pathlib.Path(sys.prefix).resolve()
    modules: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for module_name in sorted(set(sys.modules) - before):
        module = sys.modules.get(module_name)
        path = _module_origin(module)
        if path is None:
            continue
        marker = (module_name, str(path))
        if marker in seen:
            continue
        seen.add(marker)
        row, invalid = _classify_path(
            path, allowed, inventory, site_roots, stdlib_roots, prefix
        )
        row["module"] = module_name
        modules.append(row)
        if invalid:
            violations.append(dict(row))

    return {
        "allowed_distributions": sorted(allowed),
        "module_count": len(modules),
        "modules": modules,
        "violations": violations,
    }


class AccessRecorder:
    """Process-local recorder for non-code files read during one operation.

    Python audit hooks cannot be removed, so the hook is installed once and is
    active only between :meth:`start` and :meth:`stop`.  Write-only opens are
    ignored; a later read of the same path is retained.
    """

    def __init__(self) -> None:
        self.paths: set[pathlib.Path] = set()
        self.active = False
        sys.addaudithook(self._audit)

    @staticmethod
    def _is_read(mode: Any, flags: Any) -> bool:
        if isinstance(mode, str):
            return "r" in mode or "+" in mode
        if isinstance(flags, int):
            return not bool(flags & os.O_WRONLY) or bool(flags & os.O_RDWR)
        return False

    def _audit(self, event: str, args: tuple[Any, ...]) -> None:
        if not self.active or event != "open" or not args:
            return
        raw = args[0]
        if isinstance(raw, int):
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        if not self._is_read(mode, flags):
            return
        try:
            raw_text = os.fsdecode(os.fspath(raw))
        except (TypeError, ValueError):
            return
        if raw_text.startswith("<") and raw_text.endswith(">"):
            return
        path = _resolved(raw)
        if path is None or path.suffix.lower() in _CODE_SUFFIXES:
            return
        try:
            if path.is_dir():
                return
        except OSError:
            pass
        self.paths.add(path)

    def start(self) -> None:
        self.paths.clear()
        self.active = True

    def stop(self) -> None:
        self.active = False


def inspect_file_access(
    paths: Iterable[pathlib.Path], allowed_distributions: list[str]
) -> dict[str, Any]:
    """Classify non-code file reads recorded by :class:`AccessRecorder`."""
    allowed = {normalize(name) for name in allowed_distributions}
    inventory = distribution_inventory()
    site_roots, stdlib_roots = _roots()
    prefix = pathlib.Path(sys.prefix).resolve()
    accesses: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for path in sorted(set(paths), key=str):
        row, invalid = _classify_path(
            path, allowed, inventory, site_roots, stdlib_roots, prefix
        )
        accesses.append(row)
        if invalid:
            violations.append(dict(row))
    return {
        "allowed_distributions": sorted(allowed),
        "access_count": len(accesses),
        "accesses": accesses,
        "violations": violations,
    }
